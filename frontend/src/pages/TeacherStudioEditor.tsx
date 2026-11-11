import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, CheckCircle2, ClipboardPaste, KeyRound, Layers, Send, Save, Share2 } from 'lucide-react';
import { useLang } from '../i18n/LangContext';
import { apiErrorBody } from '../lib/api';
import BlockCard from '../components/studio/BlockCard';
import AnswerMatrix from '../components/studio/AnswerMatrix';
import StudentPreview from '../components/studio/StudentPreview';
import AssignDialog from '../components/studio/AssignDialog';
import {
  BLOCK_TYPES,
  STUDIO_SUBJECTS,
  StudioApi,
  emptyBlock,
  nextNumber,
  withKeys,
  type BlockType,
  type StudioBlock,
  type StudioDetail,
  type StudioIssue,
  type ParseResult,
} from '../lib/studio';

type Tab = 'blocks' | 'paste' | 'key';

interface Meta {
  title: string;
  subject: string;
  time_limit_minutes: number;
}

const errText = (e: unknown, t: (k: string, fallback?: string) => string) => {
  const fallback = e instanceof Error ? e.message : t('err_retry_js');
  const code = (e as { code?: string })?.code;
  return code ? t(`studio_err_${code}`, fallback) : fallback;
};

/**
 * Teacher Studio editor: blocks (left) + live student preview (right).
 * Ctrl/Cmd+S saves, Alt+1…5 adds a block of each type, Enter in the last
 * question adds the next one. Publishing is refused while any issue remains.
 */
export default function TeacherStudioEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useLang();

  const [meta, setMeta] = useState<Meta>({ title: '', subject: 'english', time_limit_minutes: 30 });
  const [blocks, setBlocks] = useState<StudioBlock[]>([]);
  const [detail, setDetail] = useState<StudioDetail | null>(null);
  const [issues, setIssues] = useState<StudioIssue[]>([]);
  const [tab, setTab] = useState<Tab>(id ? 'blocks' : 'paste');
  const [paste, setPaste] = useState('');
  const [parseInfo, setParseInfo] = useState<ParseResult['warnings'] | null>(null);
  const [loading, setLoading] = useState(Boolean(id));
  const [busy, setBusy] = useState<'save' | 'publish' | 'parse' | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [pane, setPane] = useState<'edit' | 'preview'>('edit');
  const validateTimer = useRef<number | null>(null);

  const applyDetail = useCallback((d: StudioDetail) => {
    setDetail(d);
    setMeta({ title: d.test.title, subject: d.test.subject, time_limit_minutes: d.test.time_limit_minutes });
    setBlocks(withKeys(d.blocks));
    setIssues(d.issues);
    setDirty(false);
  }, []);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    StudioApi.detail(id)
      .then((d) => {
        if (!cancelled) applyDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setErr(errText(e, t));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, applyDetail, t]);

  // Live validation (server rules are the single source of truth).
  useEffect(() => {
    if (!dirty) return;
    if (validateTimer.current) window.clearTimeout(validateTimer.current);
    validateTimer.current = window.setTimeout(() => {
      StudioApi.validate(blocks)
        .then((r) => setIssues(r.issues))
        .catch(() => {
          /* offline: keep the last known issues */
        });
    }, 600);
    return () => {
      if (validateTimer.current) window.clearTimeout(validateTimer.current);
    };
  }, [blocks, dirty]);

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  const editBlocks = (next: StudioBlock[]) => {
    setBlocks(next);
    setDirty(true);
    setNotice(null);
  };
  const editMeta = (patch: Partial<Meta>) => {
    setMeta((m) => ({ ...m, ...patch }));
    setDirty(true);
  };

  const addBlock = useCallback(
    (type: BlockType) => {
      setBlocks((prev) => {
        const section = prev.at(-1)?.section ?? (meta.subject === 'english' ? 'READING' : 'GENERAL');
        return [...prev, emptyBlock(type, nextNumber(prev), section)];
      });
      setDirty(true);
      setTab('blocks');
      requestAnimationFrame(() => {
        const cards = document.querySelectorAll('.studio-block');
        cards[cards.length - 1]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    },
    [meta.subject],
  );

  const save = useCallback(async (): Promise<StudioDetail | null> => {
    if (!meta.title.trim()) {
      setErr(t('studio_err_title_required'));
      return null;
    }
    setBusy('save');
    setErr(null);
    try {
      const payload = { ...meta, title: meta.title.trim(), blocks };
      const d = id ? await StudioApi.update(id, payload) : await StudioApi.create(payload);
      applyDetail(d);
      setNotice(t('studio_saved'));
      if (!id) navigate(`/teacher/studio/${d.test.id}/edit`, { replace: true });
      return d;
    } catch (e) {
      setErr(errText(e, t));
      return null;
    } finally {
      setBusy(null);
    }
  }, [id, meta, blocks, applyDetail, navigate, t]);

  const publish = async () => {
    const saved = dirty || !detail ? await save() : detail;
    if (!saved) return;
    setBusy('publish');
    setErr(null);
    try {
      const d = await StudioApi.publish(saved.test.id);
      applyDetail(d);
      setNotice(t('studio_published'));
      setAssignOpen(true);
    } catch (e) {
      if ((e as { code?: string }).code === 'invalid') {
        const body = apiErrorBody(e);
        if (Array.isArray(body?.issues)) setIssues(body.issues as StudioIssue[]);
        setErr(t('studio_publish_blocked'));
        setTab('blocks');
      } else {
        setErr(errText(e, t));
      }
    } finally {
      setBusy(null);
    }
  };

  // Keyboard shortcuts.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        void save();
      } else if (e.altKey && /^[1-5]$/.test(e.key)) {
        e.preventDefault();
        addBlock(BLOCK_TYPES[Number(e.key) - 1]);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [save, addBlock]);

  const runParse = async (mode: 'replace' | 'append') => {
    if (!paste.trim()) return;
    setBusy('parse');
    setErr(null);
    try {
      const res = await StudioApi.parse(paste, meta.subject === 'english' ? 'READING' : 'GENERAL');
      setParseInfo(res.warnings);
      if (!res.blocks.length) {
        setErr(t('studio_parse_nothing'));
        return;
      }
      const parsed = withKeys(res.blocks);
      editBlocks(mode === 'replace' ? parsed : [...blocks, ...parsed]);
      setNotice(t('studio_parse_done').replace('{n}', String(parsed.reduce((a, b) => a + (b.type === 'gap' ? (b.gap_text.match(/\[\d+/g) ?? []).length : b.questions.length), 0))));
      setTab('blocks');
    } catch (e) {
      setErr(errText(e, t));
    } finally {
      setBusy(null);
    }
  };

  const issuesByBlock = useMemo(() => {
    const map = new Map<number, StudioIssue[]>();
    for (const i of issues) map.set(i.block, [...(map.get(i.block) ?? []), i]);
    return map;
  }, [issues]);

  const questionCount = blocks.reduce((a, b) => a + (b.type === 'gap' ? (b.gap_text.match(/\[\d+/g) ?? []).length : b.questions.length), 0);
  const published = detail?.test.status === 'published';
  const locked = detail ? !detail.test.editable : false;

  if (loading) {
    return (
      <div className="studio-page" role="status">
        <div className="studio-skeleton" />
        <p className="muted">{t('loading')}</p>
      </div>
    );
  }

  return (
    <div className="studio-page">
      <header className="studio-top">
        <div className="studio-top__crumbs">
          <Link to="/teacher/studio" className="studio-back">
            <ArrowLeft size={16} aria-hidden="true" /> {t('studio_title')}
          </Link>
          {detail && (
            <span className={`studio-status is-${detail.test.status}`}>{t(`studio_status_${detail.test.status}`)}</span>
          )}
          {dirty && <span className="studio-status is-dirty">{t('studio_unsaved')}</span>}
        </div>
        <div className="studio-top__meta">
          <input
            className="studio-top__title"
            aria-label={t('studio_test_title')}
            placeholder={t('studio_test_title_ph')}
            value={meta.title}
            maxLength={255}
            disabled={locked}
            onChange={(e) => editMeta({ title: e.target.value })}
          />
          <select
            aria-label={t('studio_subject')}
            value={meta.subject}
            disabled={locked}
            onChange={(e) => editMeta({ subject: e.target.value })}
          >
            {STUDIO_SUBJECTS.map((s) => (
              <option key={s} value={s}>
                {t(`studio_subject_${s}`)}
              </option>
            ))}
          </select>
          <label className="studio-top__time">
            <span>{t('studio_minutes')}</span>
            <input
              type="number"
              min={0}
              max={600}
              value={meta.time_limit_minutes}
              disabled={locked}
              onChange={(e) => editMeta({ time_limit_minutes: Math.max(0, Math.min(600, Number(e.target.value) || 0)) })}
            />
          </label>
        </div>
        <div className="studio-top__actions">
          {!locked && (
            <button type="button" className="btn" onClick={() => void save()} disabled={busy !== null} title="Ctrl+S">
              <Save size={16} aria-hidden="true" /> {busy === 'save' ? t('studio_saving') : t('studio_save_draft')}
            </button>
          )}
          {!locked && (
            <button
              type="button"
              className="btn primary"
              onClick={() => void publish()}
              disabled={busy !== null || issues.length > 0 || blocks.length === 0}
              aria-describedby="studio-issue-summary"
            >
              <Send size={16} aria-hidden="true" />{' '}
              {busy === 'publish' ? t('studio_publishing') : published ? t('studio_republish') : t('studio_publish')}
            </button>
          )}
          {published && detail && (
            <button type="button" className="btn" onClick={() => setAssignOpen(true)}>
              <Share2 size={16} aria-hidden="true" /> {t('studio_assign')}
            </button>
          )}
        </div>
      </header>

      {locked && (
        <div className="studio-alert is-warn" role="status">
          <AlertTriangle size={18} aria-hidden="true" />{' '}
          {detail && !detail.test.is_studio ? t('studio_not_studio') : t('studio_locked')}
        </div>
      )}
      {err && (
        <div className="studio-alert is-bad" role="alert">
          <AlertTriangle size={18} aria-hidden="true" /> {err}
        </div>
      )}
      {notice && !err && (
        <div className="studio-alert is-ok" role="status">
          <CheckCircle2 size={18} aria-hidden="true" /> {notice}
        </div>
      )}

      <div id="studio-issue-summary" className={`studio-issues${issues.length ? ' has-issues' : ''}`} aria-live="polite">
        {issues.length === 0 ? (
          blocks.length > 0 && (
            <span className="studio-issues__ok">
              <CheckCircle2 size={16} aria-hidden="true" /> {t('studio_ready').replace('{n}', String(questionCount))}
            </span>
          )
        ) : (
          <>
            <strong>{t('studio_issues_count').replace('{n}', String(issues.length))}</strong>
            <ul>
              {issues.slice(0, 8).map((i, k) => (
                <li key={k}>
                  <button
                    type="button"
                    onClick={() => {
                      setTab('blocks');
                      setPane('edit');
                      requestAnimationFrame(() =>
                        document.getElementById(`studio-block-${i.block}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }),
                      );
                    }}
                  >
                    {i.block >= 0 && `${t('studio_block')} ${i.block + 1}`}
                    {i.number != null && ` · ${t('cd_question')} ${i.number}`}: {t(`studio_issue_${i.code}`)}
                  </button>
                </li>
              ))}
              {issues.length > 8 && <li className="muted">+{issues.length - 8}</li>}
            </ul>
          </>
        )}
      </div>

      <div className="studio-pane-switch" role="tablist" aria-label={t('studio_view')}>
        <button type="button" role="tab" aria-selected={pane === 'edit'} className={pane === 'edit' ? 'is-on' : ''} onClick={() => setPane('edit')}>
          {t('studio_edit')}
        </button>
        <button type="button" role="tab" aria-selected={pane === 'preview'} className={pane === 'preview' ? 'is-on' : ''} onClick={() => setPane('preview')}>
          {t('studio_preview')}
        </button>
      </div>

      <div className={`studio-split is-${pane}`}>
        <div className="studio-split__edit">
          <div className="studio-tabs" role="tablist">
            {(
              [
                ['paste', ClipboardPaste, 'studio_tab_paste'],
                ['blocks', Layers, 'studio_tab_blocks'],
                ['key', KeyRound, 'studio_tab_key'],
              ] as const
            ).map(([key, Icon, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                className={tab === key ? 'is-on' : ''}
                onClick={() => setTab(key)}
              >
                <Icon size={15} aria-hidden="true" /> {t(label)}
              </button>
            ))}
          </div>

          {tab === 'paste' && (
            <div className="studio-paste">
              <p className="studio-hint">{t('studio_paste_help')}</p>
              <textarea
                className="studio-mono"
                rows={16}
                value={paste}
                disabled={locked}
                aria-label={t('studio_tab_paste')}
                placeholder={t('studio_paste_ph')}
                onChange={(e) => setPaste(e.target.value)}
              />
              <div className="studio-row">
                <button
                  type="button"
                  className="btn primary"
                  disabled={!paste.trim() || busy !== null || locked}
                  onClick={() => void runParse(blocks.length ? 'append' : 'replace')}
                >
                  {busy === 'parse' ? t('studio_parsing') : blocks.length ? t('studio_parse_append') : t('studio_parse')}
                </button>
                {blocks.length > 0 && (
                  <button type="button" className="btn" disabled={!paste.trim() || busy !== null || locked} onClick={() => void runParse('replace')}>
                    {t('studio_parse_replace')}
                  </button>
                )}
              </div>
              {parseInfo && parseInfo.length > 0 && (
                <ul className="studio-warnings">
                  {parseInfo.map((w, i) => (
                    <li key={i}>
                      {t(`studio_warn_${w.code}`)}
                      {w.number != null && ` (${w.number})`}
                      {w.line != null && ` · ${t('studio_line')} ${w.line}`}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {tab === 'blocks' && (
            <>
              {!locked && (
                <div className="studio-quickadd" aria-label={t('studio_quick_add')}>
                  {BLOCK_TYPES.map((bt, i) => (
                    <button key={bt} type="button" className="btn sm" onClick={() => addBlock(bt)} title={`Alt+${i + 1}`}>
                      + {t(`studio_type_${bt}`)}
                    </button>
                  ))}
                </div>
              )}
              {blocks.length === 0 ? (
                <div className="studio-empty">
                  <p>{t('studio_no_blocks')}</p>
                  <button type="button" className="btn primary" onClick={() => setTab('paste')}>
                    {t('studio_tab_paste')}
                  </button>
                </div>
              ) : (
                <fieldset className="studio-blocks" disabled={locked}>
                  {blocks.map((b, i) => (
                    <BlockCard
                      key={b.key}
                      block={b}
                      index={i}
                      count={blocks.length}
                      issues={issuesByBlock.get(i) ?? []}
                      nextNumber={nextNumber(blocks)}
                      onChange={(nb) => editBlocks(blocks.map((x, k) => (k === i ? nb : x)))}
                      onRemove={() => {
                        if (window.confirm(t('studio_confirm_remove'))) editBlocks(blocks.filter((_, k) => k !== i));
                      }}
                      onMove={(dir) => {
                        const j = i + dir;
                        if (j < 0 || j >= blocks.length) return;
                        const next = [...blocks];
                        [next[i], next[j]] = [next[j], next[i]];
                        editBlocks(next);
                      }}
                    />
                  ))}
                </fieldset>
              )}
            </>
          )}

          {tab === 'key' && <AnswerMatrix blocks={blocks} issues={issues} onChange={editBlocks} />}
        </div>

        <aside className="studio-split__preview" aria-label={t('studio_preview')}>
          <StudentPreview title={meta.title} blocks={blocks} />
        </aside>
      </div>

      {assignOpen && detail && (
        <AssignDialog
          testId={detail.test.id}
          testTitle={detail.test.title}
          links={detail.links}
          assignments={detail.assignments}
          onClose={() => setAssignOpen(false)}
          onAssigned={(a) => setDetail((d) => (d ? { ...d, assignments: [...d.assignments.filter((x) => x.group_id !== a.group_id), a] } : d))}
        />
      )}
    </div>
  );
}
