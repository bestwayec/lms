import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardPaste,
  FileSpreadsheet,
  KeyRound,
  Layers,
  Save,
  Send,
  Share2,
  Sparkles,
  Upload,
} from 'lucide-react';
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
  type FileImportResult,
  type StudioBlock,
  type StudioDetail,
  type StudioIssue,
  type ParseResult,
} from '../lib/studio';

type Tab = 'blocks' | 'paste' | 'import' | 'key';

interface Meta {
  title: string;
  subject: string;
  time_limit_minutes: number;
  description?: string;
}

const errText = (e: unknown, t: (k: string, fallback?: string) => string) => {
  const fallback = e instanceof Error ? e.message : t('err_retry_js');
  const code = (e as { code?: string })?.code;
  return code ? t(`studio_err_${code}`, fallback) : fallback;
};

const TEMPLATE_MCQ_10 = `Q1. Dunyodagi eng katta okean qaysi?
A) Atlantika okeani
B) Tinch okeani
C) Hind okeani
D) Shimoliy muz okeani
ANSWER: B

Q2. O'zbekiston Respublikasi poytaxti qaysi shahar?
A) Samarqand
B) Buxoro
C) Toshkent
D) Xiva
ANSWER: C

Q3. H2O nimaning kimyoviy formulasi?
A) Oksigen
B) Suv
C) Vodorod
D) Osh tuzi
ANSWER: B

Q4. Quyosh qaysi tomondan chiqadi?
A) Sharqdan
B) G'arbdan
C) Shimoldan
D) Janubdan
ANSWER: A

Q5. 1 metr necha santimetrga teng?
A) 10 sm
B) 100 sm
C) 1000 sm
D) 50 sm
ANSWER: B
`;

/**
 * Teacher Test Builder 3.0: 3-step wizard workflow:
 * STEP 1: Test Ma'lumotlari (Title, Subject, Duration, Description)
 * STEP 2: Savollar (Manual Builder, Bulk Smart Paste, File Import CSV/XLSX, Answer Key)
 * STEP 3: Tekshirish, Nashr qilish va Biriktirish
 */
export default function TeacherStudioEditor() {
  const { id } = useParams<{ id: string }>();
  return <TeacherStudioEditorBody key={id ?? 'new'} id={id} />;
}

function TeacherStudioEditorBody({ id }: { id?: string }) {
  const navigate = useNavigate();
  const { t } = useLang();

  const [wizardStep, setWizardStep] = useState<1 | 2 | 3>(id ? 2 : 1);
  const [meta, setMeta] = useState<Meta>({ title: '', subject: 'english', time_limit_minutes: 30, description: '' });
  const [blocks, setBlocks] = useState<StudioBlock[]>([]);
  const [detail, setDetail] = useState<StudioDetail | null>(null);
  const [issues, setIssues] = useState<StudioIssue[]>([]);
  const [tab, setTab] = useState<Tab>(id ? 'blocks' : 'paste');
  const [paste, setPaste] = useState('');
  const [parseInfo, setParseInfo] = useState<ParseResult['warnings'] | null>(null);
  const [fileImportPreview, setFileImportPreview] = useState<FileImportResult | null>(null);
  const [fileImportError, setFileImportError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(id));
  const [busy, setBusy] = useState<'save' | 'publish' | 'parse' | 'import' | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [pane, setPane] = useState<'edit' | 'preview'>('edit');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const validateTimer = useRef<number | null>(null);

  const applyDetail = useCallback((d: StudioDetail) => {
    setDetail(d);
    setMeta({
      title: d.test.title,
      subject: d.test.subject,
      time_limit_minutes: d.test.time_limit_minutes,
      description: d.test.description || '',
    });
    setBlocks(withKeys(d.blocks));
    setIssues(d.issues);
    setDirty(false);
  }, []);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
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

  // Live validation
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
      setErr(t('studio_err_title_required', 'Test nomini kiritish majburiy!'));
      setWizardStep(1);
      return null;
    }
    setBusy('save');
    setErr(null);
    try {
      const payload = { ...meta, title: meta.title.trim(), blocks };
      const d = id ? await StudioApi.update(id, payload) : await StudioApi.create(payload);
      applyDetail(d);
      setNotice(t('studio_saved', 'O‘zgarishlar saqlandi!'));
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
      setNotice(t('studio_published', 'Test muvaffaqiyatli nashr qilindi!'));
      setAssignOpen(true);
    } catch (e) {
      if ((e as { code?: string }).code === 'invalid') {
        const body = apiErrorBody(e);
        if (Array.isArray(body?.issues)) setIssues(body.issues as StudioIssue[]);
        setErr(t('studio_publish_blocked', 'Testda hal qilinmagan xatoliklar mavjud'));
        setWizardStep(3);
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
        setErr(t('studio_parse_nothing', 'Matnda savollar topilmadi'));
        return;
      }
      const parsed = withKeys(res.blocks);
      editBlocks(mode === 'replace' ? parsed : [...blocks, ...parsed]);
      setNotice(
        t('studio_parse_done', '{n} ta savol muvaffaqiyatli import qilindi').replace(
          '{n}',
          String(
            parsed.reduce(
              (a, b) =>
                a + (b.type === 'gap' ? (b.gap_text.match(/\[\d+/g) ?? []).length : b.questions.length),
              0,
            ),
          ),
        ),
      );
      setTab('blocks');
    } catch (e) {
      setErr(errText(e, t));
    } finally {
      setBusy(null);
    }
  };

  const handleFileUpload = async (file: File | undefined) => {
    if (!file) return;
    setBusy('import');
    setFileImportError(null);
    try {
      const res = await StudioApi.importFile(file, meta.subject === 'english' ? 'READING' : 'GENERAL');
      setFileImportPreview(res);
      setNotice(t('studio_file_scanned', 'Fayl skanerlandi! Savollarni tekshirib kiritishni tasdiqlang'));
    } catch (e) {
      setFileImportError(errText(e, t));
    } finally {
      setBusy(null);
    }
  };

  const applyFileImport = (mode: 'replace' | 'append') => {
    if (!fileImportPreview || !fileImportPreview.blocks.length) return;
    const parsed = withKeys(fileImportPreview.blocks);
    editBlocks(mode === 'replace' ? parsed : [...blocks, ...parsed]);
    setFileImportPreview(null);
    setNotice(t('studio_file_imported', 'Fayldan savollar tahrirlagichga yuklandi!'));
    setTab('blocks');
  };

  const issuesByBlock = useMemo(() => {
    const map = new Map<number, StudioIssue[]>();
    for (const i of issues) map.set(i.block, [...(map.get(i.block) ?? []), i]);
    return map;
  }, [issues]);

  const questionCount = blocks.reduce(
    (a, b) => a + (b.type === 'gap' ? (b.gap_text.match(/\[\d+/g) ?? []).length : b.questions.length),
    0,
  );
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
      <header className="studio-top" style={{ flexWrap: 'wrap', gap: 12 }}>
        <div className="studio-top__crumbs">
          <Link to="/teacher/studio" className="studio-back">
            <ArrowLeft size={16} aria-hidden="true" /> {t('studio_title', 'Test Banki')}
          </Link>
          {detail && (
            <span className={`studio-status is-${detail.test.status}`}>
              {t(`studio_status_${detail.test.status}`, detail.test.status)}
            </span>
          )}
          {dirty && <span className="studio-status is-dirty">{t('studio_unsaved', 'Saqlanmagan')}</span>}
        </div>

        <div className="studio-top__actions" style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {!locked && (
            <button type="button" className="btn sm" onClick={() => void save()} disabled={busy !== null} title="Ctrl+S">
              <Save size={15} aria-hidden="true" /> {busy === 'save' ? t('studio_saving', 'Saqlanmoqda...') : t('studio_save_draft', 'Saqlash')}
            </button>
          )}
          {!locked && (
            <button
              type="button"
              className="btn sm primary"
              onClick={() => void publish()}
              disabled={busy !== null || issues.length > 0 || blocks.length === 0}
              aria-describedby="studio-issue-summary"
            >
              <Send size={15} aria-hidden="true" />{' '}
              {busy === 'publish' ? t('studio_publishing') : published ? t('studio_republish', 'Qayta nashr qilish') : t('studio_publish', 'Nashr qilish')}
            </button>
          )}
          {published && detail && (
            <button type="button" className="btn sm" onClick={() => setAssignOpen(true)}>
              <Share2 size={15} aria-hidden="true" /> {t('studio_assign', 'Biriktirish')}
            </button>
          )}
        </div>
      </header>

      {/* 3-Step Wizard Stepper Navigation */}
      <nav
        className="studio-stepper card"
        aria-label="Wizard Steps"
        style={{
          display: 'flex',
          gap: 8,
          margin: '12px 0 16px',
          padding: '8px 12px',
          overflowX: 'auto',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', alignItems: 'center' }}>
          {[
            { step: 1, label: t('studio_step_info', '1. Asosiy ma‘lumotlar'), icon: '📋' },
            { step: 2, label: t('studio_step_questions', '2. Savollar tuzish'), icon: '✍️' },
            { step: 3, label: t('studio_step_publish', '3. Tekshirish & Nashr'), icon: '🚀' },
          ].map((s) => (
            <button
              key={s.step}
              type="button"
              className={`btn sm ${wizardStep === s.step ? 'primary' : 'ghost'}`}
              style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}
              onClick={() => setWizardStep(s.step as 1 | 2 | 3)}
            >
              <span>{s.icon}</span>
              <span>{s.label}</span>
              {s.step === 2 && questionCount > 0 && (
                <span
                  style={{
                    background: wizardStep === 2 ? 'rgba(255,255,255,0.3)' : 'var(--code-bg, #e5e7eb)',
                    color: wizardStep === 2 ? '#fff' : 'inherit',
                    padding: '1px 6px',
                    borderRadius: 10,
                    fontSize: '0.75rem',
                  }}
                >
                  {questionCount}
                </span>
              )}
              {s.step === 3 && issues.length > 0 && (
                <span
                  style={{
                    background: '#ef4444',
                    color: '#fff',
                    padding: '1px 6px',
                    borderRadius: 10,
                    fontSize: '0.75rem',
                  }}
                >
                  {issues.length}
                </span>
              )}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {wizardStep > 1 && (
            <button
              type="button"
              className="btn sm ghost"
              onClick={() => setWizardStep((prev) => (prev - 1) as 1 | 2 | 3)}
            >
              <ChevronLeft size={14} aria-hidden="true" /> {t('back', 'Ortga')}
            </button>
          )}
          {wizardStep < 3 && (
            <button
              type="button"
              className="btn sm secondary"
              onClick={() => {
                if (wizardStep === 1 && !meta.title.trim()) {
                  setErr(t('studio_err_title_required', 'Test nomini kiritish majburiy!'));
                  return;
                }
                setWizardStep((prev) => (prev + 1) as 1 | 2 | 3);
              }}
            >
              {t('next', 'Oldinga')} <ChevronRight size={14} aria-hidden="true" />
            </button>
          )}
        </div>
      </nav>

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

      {/* STEP 1: TEST METADATA */}
      {wizardStep === 1 && (
        <section className="card studio-step-card" style={{ maxWidth: 700, margin: '0 auto', padding: 24 }}>
          <h2 style={{ fontSize: '1.25rem', marginBottom: 16 }}>📋 {t('studio_step_info', 'Testning asosiy ma‘lumotlari')}</h2>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <label className="studio-field">
              <span style={{ fontWeight: 600 }}>{t('studio_test_title', 'Test nomi')} *</span>
              <input
                className="studio-top__title"
                style={{ width: '100%', padding: '8px 12px', fontSize: '1rem', borderRadius: 6, border: '1px solid var(--border)' }}
                placeholder={t('studio_test_title_ph', 'Masalan: 9-sinf Fizika 1-chorak')}
                value={meta.title}
                maxLength={255}
                disabled={locked}
                onChange={(e) => editMeta({ title: e.target.value })}
              />
            </label>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
              <label className="studio-field">
                <span style={{ fontWeight: 600 }}>{t('studio_subject', 'Fan')}</span>
                <select
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border)' }}
                  value={meta.subject}
                  disabled={locked}
                  onChange={(e) => editMeta({ subject: e.target.value })}
                >
                  {STUDIO_SUBJECTS.map((s) => (
                    <option key={s} value={s}>
                      {t(`studio_subject_${s}`, s)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="studio-field">
                <span style={{ fontWeight: 600 }}>{t('studio_minutes', 'Vaqt limiti (daqiqa)')}</span>
                <input
                  type="number"
                  min={0}
                  max={600}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border)' }}
                  value={meta.time_limit_minutes}
                  disabled={locked}
                  onChange={(e) => editMeta({ time_limit_minutes: Math.max(0, Math.min(600, Number(e.target.value) || 0)) })}
                />
              </label>
            </div>

            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              <span className="muted small">{t('studio_time_presets', 'Tezkor vaqt')}:</span>
              {[15, 20, 30, 45, 60, 90].map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`btn sm ${meta.time_limit_minutes === m ? 'primary' : 'ghost'}`}
                  onClick={() => editMeta({ time_limit_minutes: m })}
                >
                  {m} {t('minutes_short', 'daq')}
                </button>
              ))}
            </div>

            <label className="studio-field">
              <span style={{ fontWeight: 600 }}>{t('studio_description', 'Tavsif yoki o‘quvchilar uchun yo‘riqnoma (ixtiyoriy)')}</span>
              <textarea
                rows={3}
                style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border)' }}
                placeholder={t('studio_description_ph', 'Ushbu test bo‘yicha qo‘shimcha yo‘riqnomalar...')}
                value={meta.description || ''}
                disabled={locked}
                onChange={(e) => editMeta({ description: e.target.value })}
              />
            </label>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
              <button
                type="button"
                className="btn primary"
                disabled={!meta.title.trim()}
                onClick={() => setWizardStep(2)}
              >
                {t('studio_goto_questions', 'Keyingisi: Savollar qo‘shish')} →
              </button>
            </div>
          </div>
        </section>
      )}

      {/* STEP 2: QUESTIONS & 3 CREATION MODES */}
      {wizardStep === 2 && (
        <>
          <div className="studio-pane-switch" role="tablist" aria-label={t('studio_view')}>
            <button
              type="button"
              role="tab"
              aria-selected={pane === 'edit'}
              className={pane === 'edit' ? 'is-on' : ''}
              onClick={() => setPane('edit')}
            >
              ✍️ {t('studio_edit', 'Tahrirlash')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={pane === 'preview'}
              className={pane === 'preview' ? 'is-on' : ''}
              onClick={() => setPane('preview')}
            >
              👁️ {t('studio_preview', 'O‘quvchi ko‘rinishi')}
            </button>
          </div>

          <div className={`studio-split is-${pane}`}>
            <div className="studio-split__edit">
              <div className="studio-tabs" role="tablist" style={{ flexWrap: 'wrap' }}>
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === 'blocks'}
                  className={tab === 'blocks' ? 'is-on' : ''}
                  onClick={() => setTab('blocks')}
                >
                  <Layers size={15} aria-hidden="true" /> {t('studio_tab_blocks', 'Qo‘lda tuzish')}
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === 'paste'}
                  className={tab === 'paste' ? 'is-on' : ''}
                  onClick={() => setTab('paste')}
                >
                  <ClipboardPaste size={15} aria-hidden="true" /> {t('studio_tab_paste', 'Tezkor matn nusxalash')}
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === 'import'}
                  className={tab === 'import' ? 'is-on' : ''}
                  onClick={() => setTab('import')}
                >
                  <FileSpreadsheet size={15} aria-hidden="true" /> {t('studio_tab_file', 'Fayldan import (CSV)')}
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === 'key'}
                  className={tab === 'key' ? 'is-on' : ''}
                  onClick={() => setTab('key')}
                >
                  <KeyRound size={15} aria-hidden="true" /> {t('studio_tab_key', 'Javoblar jadvali')}
                </button>
              </div>

              {/* MODE 1: MANUAL BUILDER */}
              {tab === 'blocks' && (
                <>
                  {!locked && (
                    <div className="studio-quickadd card" style={{ padding: 10, margin: '10px 0', display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                      <span className="muted small">{t('studio_add_type', '+ Savol qo‘shish')}:</span>
                      {BLOCK_TYPES.map((bt, i) => (
                        <button key={bt} type="button" className="btn sm" onClick={() => addBlock(bt)} title={`Alt+${i + 1}`}>
                          + {t(`studio_type_${bt}`, bt)}
                        </button>
                      ))}
                    </div>
                  )}

                  {blocks.length === 0 ? (
                    <div className="studio-empty">
                      <p>{t('studio_no_blocks', 'Hozircha savollar qo‘shilmagan')}</p>
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 12 }}>
                        <button type="button" className="btn primary" onClick={() => addBlock('mcq')}>
                          + {t('studio_type_mcq', 'Variantli savol qo‘shish')}
                        </button>
                        <button type="button" className="btn secondary" onClick={() => setTab('paste')}>
                          <ClipboardPaste size={14} aria-hidden="true" /> {t('studio_tab_paste', 'Matndan import')}
                        </button>
                      </div>
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
                            if (window.confirm(t('studio_confirm_remove', 'Ushbu savol guruhini o‘chirmoqchimisiz?'))) {
                              editBlocks(blocks.filter((_, k) => k !== i));
                            }
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

              {/* MODE 2: SMART PASTE */}
              {tab === 'paste' && (
                <div className="studio-paste">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                    <p className="studio-hint" style={{ margin: 0 }}>
                      {t('studio_paste_help', 'Savollar, variantlar va javoblarni matn shaklida qo‘ying. Q1. ... A) ... ANSWER: B formatini taniydi.')}
                    </p>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        type="button"
                        className="btn sm ghost"
                        onClick={() => setPaste(TEMPLATE_MCQ_10)}
                      >
                        <Sparkles size={13} aria-hidden="true" /> {t('studio_template_10', 'Namuna shablon')}
                      </button>
                    </div>
                  </div>

                  <textarea
                    className="studio-mono"
                    rows={16}
                    value={paste}
                    disabled={locked}
                    aria-label={t('studio_tab_paste')}
                    placeholder={t('studio_paste_ph', 'Q1. Savol matni\nA) Variant 1\nB) Variant 2\nC) Variant 3\nD) Variant 4\nANSWER: B')}
                    onChange={(e) => setPaste(e.target.value)}
                  />

                  <div className="studio-row" style={{ marginTop: 12 }}>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={!paste.trim() || busy !== null || locked}
                      onClick={() => void runParse(blocks.length ? 'append' : 'replace')}
                    >
                      {busy === 'parse'
                        ? t('studio_parsing', 'Tahlil qilinmoqda...')
                        : blocks.length
                        ? t('studio_parse_append', 'Savollar oxiriga qo‘shish')
                        : t('studio_parse', 'Savollarni import qilish')}
                    </button>
                    {blocks.length > 0 && (
                      <button
                        type="button"
                        className="btn"
                        disabled={!paste.trim() || busy !== null || locked}
                        onClick={() => void runParse('replace')}
                      >
                        {t('studio_parse_replace', 'Barchasini almashtirish')}
                      </button>
                    )}
                  </div>

                  {parseInfo && parseInfo.length > 0 && (
                    <ul className="studio-warnings">
                      {parseInfo.map((w, i) => (
                        <li key={i}>
                          {t(`studio_warn_${w.code}`, w.code)}
                          {w.number != null && ` (${w.number})`}
                          {w.line != null && ` · ${t('studio_line', 'Qator')} ${w.line}`}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {/* MODE 3: FILE IMPORT (CSV/XLSX) */}
              {tab === 'import' && (
                <div className="card studio-file-import" style={{ padding: 20 }}>
                  <h3 style={{ fontSize: '1.1rem', marginBottom: 8 }}>
                    <FileSpreadsheet size={18} style={{ verticalAlign: 'middle', marginRight: 6 }} />
                    {t('studio_file_import_title', 'CSV fayldan test savollarini yuklash')}
                  </h3>
                  <p className="muted small" style={{ marginBottom: 16 }}>
                    {t(
                      'studio_file_import_desc',
                      'Faylda question, choice_a, choice_b, choice_c, choice_d, correct, points, explanation ustunlari bo‘lishi lozim.',
                    )}
                  </p>

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,text/csv,text/plain"
                    hidden
                    onChange={(e) => {
                      void handleFileUpload(e.target.files?.[0]);
                      e.target.value = '';
                    }}
                  />

                  <div
                    style={{
                      border: '2px dashed var(--border)',
                      borderRadius: 8,
                      padding: 32,
                      textAlign: 'center',
                      background: 'var(--card-hover, #f9fafb)',
                      cursor: 'pointer',
                    }}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload size={32} style={{ margin: '0 auto 12px', color: 'var(--primary)' }} />
                    <p style={{ fontWeight: 600, marginBottom: 4 }}>
                      {busy === 'import' ? t('loading', 'Yuklanmoqda...') : t('studio_upload_csv_btn', 'CSV faylni tanlang yoki shu yerga tashlang')}
                    </p>
                    <span className="muted small">.csv format (UTF-8)</span>
                  </div>

                  {fileImportError && (
                    <div className="studio-alert is-bad" style={{ marginTop: 16 }} role="alert">
                      {fileImportError}
                    </div>
                  )}

                  {fileImportPreview && (
                    <div style={{ marginTop: 20, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <div>
                          <strong>{t('studio_detected_qs', 'Aniqlangan savollar')}: {fileImportPreview.questions_count} ta</strong>
                          <span className="muted small" style={{ marginLeft: 8 }}>
                            ({fileImportPreview.detected_answers} ta to‘g‘ri javob kaliti bilan)
                          </span>
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button
                            type="button"
                            className="btn primary sm"
                            onClick={() => applyFileImport(blocks.length ? 'append' : 'replace')}
                          >
                            {blocks.length ? t('studio_parse_append', 'Oxiriga qo‘shish') : t('confirm', 'Tasdiqlash')}
                          </button>
                          {blocks.length > 0 && (
                            <button
                              type="button"
                              className="btn sm"
                              onClick={() => applyFileImport('replace')}
                            >
                              {t('studio_parse_replace', 'Barchasini almashtirish')}
                            </button>
                          )}
                        </div>
                      </div>

                      {fileImportPreview.warnings.length > 0 && (
                        <div className="studio-alert is-warn" style={{ marginBottom: 12 }}>
                          <span>⚠️ {fileImportPreview.warnings.length} ta ogohlantirish aniqlandi:</span>
                          <ul style={{ margin: '4px 0 0 16px', fontSize: '0.85rem' }}>
                            {fileImportPreview.warnings.slice(0, 5).map((w, idx) => (
                              <li key={idx}>
                                {w.row && `${w.row}-qator: `}{t(`studio_warn_${w.code}`, w.code)}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <div className="table-wrap" style={{ maxHeight: 240, overflowY: 'auto' }}>
                        <table className="data" style={{ fontSize: '0.85rem' }}>
                          <thead>
                            <tr>
                              <th>№</th>
                              <th>{t('question', 'Savol')}</th>
                              <th>{t('choices', 'Variantlar')}</th>
                              <th>{t('answer', 'Kalit')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {fileImportPreview.blocks[0]?.questions.slice(0, 10).map((q) => (
                              <tr key={q.number}>
                                <td>{q.number}</td>
                                <td>{q.text}</td>
                                <td>{q.options.join(' | ')}</td>
                                <td><strong>{q.answer || '—'}</strong></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* MODE 4: ANSWER KEY MATRIX */}
              {tab === 'key' && <AnswerMatrix blocks={blocks} issues={issues} onChange={editBlocks} />}

              {/* Step 2 Bottom Actions */}
              <div className="studio-sticky-bar">
                <button type="button" className="btn ghost" onClick={() => setWizardStep(1)}>
                  <ChevronLeft size={14} aria-hidden="true" /> {t('studio_step_info', '1. Asosiy ma‘lumotlar')}
                </button>
                <button
                  type="button"
                  className="btn primary"
                  disabled={questionCount === 0}
                  onClick={() => setWizardStep(3)}
                >
                  {t('studio_goto_step3', 'Keyingisi: Tekshirish & Nashr')} →
                </button>
              </div>
            </div>

            <aside className="studio-split__preview" aria-label={t('studio_preview')}>
              <StudentPreview title={meta.title} blocks={blocks} />
            </aside>
          </div>
        </>
      )}

      {/* STEP 3: REVIEW, PUBLISH & ASSIGN */}
      {wizardStep === 3 && (
        <section className="card studio-step-card" style={{ maxWidth: 800, margin: '0 auto', padding: 24 }}>
          <h2 style={{ fontSize: '1.25rem', marginBottom: 16 }}>🚀 {t('studio_step_publish', 'Testni tekshirish va nashr qilish')}</h2>

          {/* Test Summary Box */}
          <div style={{ background: 'var(--card-hover, #f9fafb)', borderRadius: 8, padding: 16, marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
              <div>
                <h3 style={{ margin: '0 0 6px', fontSize: '1.15rem' }}>{meta.title}</h3>
                <div className="muted small" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <span>{t(`studio_subject_${meta.subject}`, meta.subject)}</span>
                  <span>·</span>
                  <span>{meta.time_limit_minutes} {t('minutes_short', 'daq')}</span>
                  <span>·</span>
                  <span>{t('studio_n_questions', '{n} ta savol').replace('{n}', String(questionCount))}</span>
                </div>
              </div>
              <button type="button" className="btn sm ghost" onClick={() => setWizardStep(1)}>
                {t('edit', 'Tahrirlash')}
              </button>
            </div>
            {meta.description && <p style={{ margin: '12px 0 0', fontSize: '0.9rem' }}>{meta.description}</p>}
          </div>

          {/* Validation Checklist */}
          <div style={{ marginBottom: 24 }}>
            <h4 style={{ fontSize: '1rem', marginBottom: 10 }}>{t('studio_checklist', 'Tekshiruv xulosasi')}:</h4>
            {issues.length === 0 ? (
              <div
                style={{
                  background: 'var(--green-bg, #ecfdf5)',
                  color: 'var(--green-text, #065f46)',
                  border: '1px solid var(--green-border, #a7f3d0)',
                  borderRadius: 6,
                  padding: '12px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                }}
              >
                <CheckCircle2 size={20} aria-hidden="true" />
                <div>
                  <strong>{t('studio_ready_title', 'Barcha savollar to‘g‘ri shakllantirilgan!')}</strong>
                  <p style={{ margin: 0, fontSize: '0.85rem' }}>
                    {t('studio_ready', '{n} ta savol nashr qilishga tayyor').replace('{n}', String(questionCount))}
                  </p>
                </div>
              </div>
            ) : (
              <div
                style={{
                  background: '#fef2f2',
                  color: '#991b1b',
                  border: '1px solid #fecaca',
                  borderRadius: 6,
                  padding: '12px 16px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <AlertTriangle size={18} aria-hidden="true" />
                  <strong>
                    {t('studio_issues_count', '{n} ta muammoni to‘g‘rilash lozim').replace('{n}', String(issues.length))}
                  </strong>
                </div>
                <ul style={{ margin: 0, paddingLeft: 20, fontSize: '0.85rem' }}>
                  {issues.map((i, k) => (
                    <li key={k} style={{ marginBottom: 4 }}>
                      <button
                        type="button"
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#b91c1c',
                          textDecoration: 'underline',
                          cursor: 'pointer',
                          padding: 0,
                          textAlign: 'left',
                        }}
                        onClick={() => {
                          setWizardStep(2);
                          setTab('blocks');
                          requestAnimationFrame(() =>
                            document.getElementById(`studio-block-${i.block}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }),
                          );
                        }}
                      >
                        {i.block >= 0 && `${t('studio_block', 'Guruh')} ${i.block + 1}`}
                        {i.number != null && ` · ${t('cd_question', 'Savol')} ${i.number}`}: {t(`studio_issue_${i.code}`, i.code)}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Actions Bar */}
          <div className="studio-sticky-bar">
            <button type="button" className="btn ghost" onClick={() => setWizardStep(2)}>
              <ChevronLeft size={14} aria-hidden="true" /> {t('studio_step_questions', '2. Savollar')}
            </button>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn"
                disabled={busy !== null || locked}
                onClick={() => void save()}
              >
                <Save size={15} aria-hidden="true" /> {t('studio_save_draft', 'Qoralama sifatida saqlash')}
              </button>

              <button
                type="button"
                className="btn primary"
                disabled={busy !== null || issues.length > 0 || blocks.length === 0 || locked}
                onClick={() => void publish()}
              >
                <Send size={15} aria-hidden="true" />{' '}
                {published ? t('studio_republish', 'Qayta nashr qilish') : t('studio_publish', 'Nashr qilish')}
              </button>

              {published && detail && (
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() => setAssignOpen(true)}
                >
                  <Share2 size={15} aria-hidden="true" /> {t('studio_assign', 'Guruhga biriktirish')}
                </button>
              )}
            </div>
          </div>
        </section>
      )}

      {assignOpen && detail && (
        <AssignDialog
          testId={detail.test.id}
          testTitle={detail.test.title}
          links={detail.links}
          assignments={detail.assignments}
          onClose={() => setAssignOpen(false)}
          onAssigned={(a) =>
            setDetail((d) => (d ? { ...d, assignments: [...d.assignments.filter((x) => x.group_id !== a.group_id), a] } : d))
          }
        />
      )}
    </div>
  );
}
