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
  ASSESSMENT_CATEGORIES,
  BLOCK_TYPES,
  STUDIO_AUDIENCES,
  STUDIO_SUBJECTS,
  StudioApi,
  blankMcqBlock,
  emptyBlock,
  nextNumber,
  withKeys,
  type AssessmentCategory,
  type BlockType,
  type FileImportResult,
  type StudioBlock,
  type StudioDetail,
  type StudioIssue,
  type ParseResult,
  type StudioAudience,
} from '../lib/studio';

type Tab = 'blocks' | 'paste' | 'import' | 'key';

interface Meta {
  title: string;
  subject: string;
  assessment_category: AssessmentCategory;
  time_limit_minutes: number;
  available_from?: string | null;
  available_until?: string | null;
  description?: string;
  audience: StudioAudience;
}

const errText = (e: unknown, t: (k: string, fallback?: string) => string) => {
  const fallback = e instanceof Error ? e.message : t('err_retry_js');
  const code = (e as { code?: string })?.code;
  return code ? t(`studio_err_${code}`, fallback) : fallback;
};

function generateMcqTemplate(count: number): string {
  const sampleQuestions = [
    { q: "Dunyodagi eng katta okean qaysi?", a: "Atlantika okeani", b: "Tinch okeani", c: "Hind okeani", d: "Shimoliy muz okeani", ans: "B" },
    { q: "O'zbekiston Respublikasi poytaxti qaysi shahar?", a: "Samarqand", b: "Buxoro", c: "Toshkent", d: "Xiva", ans: "C" },
    { q: "H2O nimaning kimyoviy formulasi?", a: "Oksigen", b: "Suv", c: "Vodorod", d: "Osh tuzi", ans: "B" },
    { q: "Quyosh qaysi tomondan chiqadi?", a: "Sharqdan", b: "G'arbdan", c: "Shimoldan", d: "Janubdan", ans: "A" },
    { q: "1 metr necha santimetrga teng?", a: "10 sm", b: "100 sm", c: "1000 sm", d: "50 sm", ans: "B" },
  ];
  let res = '';
  for (let i = 1; i <= count; i++) {
    const s = sampleQuestions[(i - 1) % sampleQuestions.length];
    res += `Q${i}. ${s.q}\nA) ${s.a}\nB) ${s.b}\nC) ${s.c}\nD) ${s.d}\nANSWER: ${s.ans}\n\n`;
  }
  return res.trim();
}

const TEMPLATE_MCQ_10 = generateMcqTemplate(10);
const TEMPLATE_MCQ_20 = generateMcqTemplate(20);
const TEMPLATE_MCQ_30 = generateMcqTemplate(30);

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
  const [meta, setMeta] = useState<Meta>({
    title: '',
    subject: 'uzbek',
    assessment_category: 'classroom_quiz',
    time_limit_minutes: 30,
    available_from: null,
    available_until: null,
    description: '',
    audience: 'GROUP_ONLY',
  });
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

  const draftKey = `studio_draft_${id ?? 'new'}`;
  const [recoverableDraft, setRecoverableDraft] = useState<{
    meta?: Meta;
    blocks?: StudioBlock[];
    wizardStep?: 1 | 2 | 3;
    tab?: Tab;
    paste?: string;
    timestamp: number;
  } | null>(() => {
    try {
      const raw = localStorage.getItem(draftKey);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (parsed && (parsed.blocks?.length > 0 || parsed.meta?.title?.trim() || parsed.paste?.trim())) {
        if (Date.now() - (parsed.timestamp || 0) < 7 * 86400 * 1000) {
          return parsed;
        }
      }
    } catch {
      /* ignore storage failure */
    }
    return null;
  });

  // Auto-save local draft
  useEffect(() => {
    if (!dirty) return;
    const timer = window.setTimeout(() => {
      try {
        const draft = {
          meta,
          blocks,
          wizardStep,
          tab,
          paste,
          timestamp: Date.now(),
        };
        localStorage.setItem(draftKey, JSON.stringify(draft));
      } catch {
        /* storage full */
      }
    }, 800);
    return () => window.clearTimeout(timer);
  }, [dirty, meta, blocks, wizardStep, tab, paste, draftKey]);

  const restoreDraft = () => {
    if (!recoverableDraft) return;
    if (recoverableDraft.meta) setMeta(recoverableDraft.meta);
    if (recoverableDraft.blocks) setBlocks(withKeys(recoverableDraft.blocks));
    if (recoverableDraft.wizardStep) setWizardStep(recoverableDraft.wizardStep);
    if (recoverableDraft.tab) setTab(recoverableDraft.tab);
    if (recoverableDraft.paste) setPaste(recoverableDraft.paste);
    setDirty(true);
    setNotice(t('studio_draft_restored', 'Qoralama muvaffaqiyatli tiklandi!'));
    setRecoverableDraft(null);
  };

  const discardDraft = () => {
    try {
      localStorage.removeItem(draftKey);
    } catch {
      /* ignore */
    }
    setRecoverableDraft(null);
  };

  const applyDetail = useCallback((d: StudioDetail) => {
    setDetail(d);
    setMeta({
      title: d.test.title,
      subject: d.test.subject,
      assessment_category: d.test.assessment_category ?? 'classroom_quiz',
      time_limit_minutes: d.test.time_limit_minutes,
      available_from: d.test.available_from ? d.test.available_from.slice(0, 16) : null,
      available_until: d.test.available_until ? d.test.available_until.slice(0, 16) : null,
      description: d.test.description || '',
      audience: d.test.audience ?? 'GROUP_ONLY',
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
      try {
        localStorage.removeItem(draftKey);
        setRecoverableDraft(null);
      } catch {
        /* ignore */
      }
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
  }, [id, meta, blocks, applyDetail, navigate, t, draftKey]);

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

      {recoverableDraft && (
        <aside
          className="studio-alert"
          style={{
            background: 'linear-gradient(135deg, rgba(200, 146, 42, 0.15), rgba(59, 130, 246, 0.12))',
            borderColor: 'var(--primary, #C8922A)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 12,
            marginBottom: 16,
          }}
          role="status"
          aria-label={t('studio_draft_found', 'Saqlanmagan qoralama topildi!')}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 20 }}>💾</span>
            <div>
              <strong>{t('studio_draft_found', 'Saqlanmagan qoralama topildi!')}</strong>
              <div className="muted small">
                {recoverableDraft.meta?.title ? `"${recoverableDraft.meta.title}" · ` : ''}
                {recoverableDraft.blocks?.length ? `${recoverableDraft.blocks.length} ta guruh · ` : ''}
                {new Date(recoverableDraft.timestamp).toLocaleTimeString()}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="btn sm primary" onClick={restoreDraft}>
              {t('studio_draft_restore_btn', 'Qoralamani tiklash')}
            </button>
            <button type="button" className="btn sm ghost" onClick={discardDraft}>
              {t('studio_draft_discard_btn', 'Rad etish')}
            </button>
          </div>
        </aside>
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
                <span style={{ fontWeight: 600 }}>{t('studio_category', 'Kategoriya')}</span>
                <select
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border)' }}
                  value={meta.assessment_category}
                  disabled={locked}
                  onChange={(e) => editMeta({ assessment_category: e.target.value as AssessmentCategory })}
                >
                  {ASSESSMENT_CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {t(`studio_category_${cat}`, cat)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="studio-field">
                <span style={{ fontWeight: 600 }}>{t('studio_audience', 'Kim topshira oladi')}</span>
                <select
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border)' }}
                  value={meta.audience}
                  disabled={locked}
                  onChange={(e) => editMeta({ audience: e.target.value as StudioAudience })}
                  aria-describedby="studio-audience-help"
                >
                  {STUDIO_AUDIENCES.map((a) => (
                    <option key={a} value={a}>
                      {t(`studio_audience_${a}`, a)}
                    </option>
                  ))}
                </select>
                <small id="studio-audience-help" className="muted">
                  {t(`studio_audience_help_${meta.audience}`, '')}
                </small>
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
              {[0, 15, 20, 30, 45, 60, 90].map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`btn sm ${meta.time_limit_minutes === m ? 'primary' : 'ghost'}`}
                  onClick={() => editMeta({ time_limit_minutes: m })}
                >
                  {m === 0 ? t('studio_time_untimed', 'Cheklovsiz') : `${m} ${t('minutes_short', 'daq')}`}
                </button>
              ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
              <label className="studio-field">
                <span style={{ fontWeight: 600 }}>{t('studio_available_from', 'Boshlanish sanasi (ixtiyoriy)')}</span>
                <input
                  type="datetime-local"
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border)' }}
                  value={meta.available_from ?? ''}
                  disabled={locked}
                  onChange={(e) => editMeta({ available_from: e.target.value || null })}
                />
              </label>
              <label className="studio-field">
                <span style={{ fontWeight: 600 }}>{t('studio_available_until', 'Tugash muddati (ixtiyoriy)')}</span>
                <input
                  type="datetime-local"
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border)' }}
                  value={meta.available_until ?? ''}
                  disabled={locked}
                  onChange={(e) => editMeta({ available_until: e.target.value || null })}
                />
              </label>
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
                    <>
                    <div className="studio-quickadd card" style={{ padding: 10, margin: '10px 0', display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                      <span className="muted small">{t('studio_blank_test', 'Bo‘sh test')}:</span>
                      {[10, 20, 30, 40].map((n) => (
                        <button
                          key={`blank-${n}`}
                          type="button"
                          className="btn sm"
                          onClick={() => {
                            const section = blocks.at(-1)?.section ?? (meta.subject === 'english' ? 'READING' : 'GENERAL');
                            editBlocks([...blocks, blankMcqBlock(n, nextNumber(blocks), section)]);
                          }}
                        >
                          {t('studio_blank_n', '{n} ta savol').replace('{n}', String(n))}
                        </button>
                      ))}
                    </div>
                    <div className="studio-quickadd card" style={{ padding: 10, margin: '10px 0', display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                      <span className="muted small">{t('studio_add_type', '+ Savol qo‘shish')}:</span>
                      {BLOCK_TYPES.map((bt, i) => (
                        <button key={bt} type="button" className="btn sm" onClick={() => addBlock(bt)} title={`Alt+${i + 1}`}>
                          + {t(`studio_type_${bt}`, bt)}
                        </button>
                      ))}
                    </div>
                    </>
                  )}

                  {blocks.length === 0 ? (
                    <div className="studio-empty">
                      <p>{t('studio_no_blocks', 'Hozircha savollar qo‘shilmagan')}</p>
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 12, flexWrap: 'wrap' }}>
                        <button type="button" className="btn primary" onClick={() => addBlock('mcq')}>
                          + {t('studio_type_mcq', 'Variantli savol qo‘shish')}
                        </button>
                        <button type="button" className="btn secondary" onClick={() => setTab('paste')}>
                          <ClipboardPaste size={14} aria-hidden="true" /> {t('studio_tab_paste', 'Matndan import')}
                        </button>
                      </div>
                      <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px dashed var(--border)' }}>
                        <span className="muted small" style={{ display: 'block', marginBottom: 8 }}>
                          ⚡ {t('studio_quick_starters', 'Tezkor to‘plam')}:
                        </span>
                        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
                          {[10, 20, 30, 40].map((n) => (
                            <button
                              key={n}
                              type="button"
                              className="btn sm ghost"
                              onClick={() => editBlocks([...blocks, withKeys([blankMcqBlock(n, nextNumber(blocks))])[0]])}
                            >
                              + {t(`studio_starter_${n}`, `${n} ta savol`)}
                            </button>
                          ))}
                        </div>
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
                          subject={meta.subject}
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
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className="btn sm ghost"
                        onClick={() => setPaste(TEMPLATE_MCQ_10)}
                      >
                        <Sparkles size={13} aria-hidden="true" /> {t('studio_starter_10', '10 ta savol')}
                      </button>
                      <button
                        type="button"
                        className="btn sm ghost"
                        onClick={() => setPaste(TEMPLATE_MCQ_20)}
                      >
                        <Sparkles size={13} aria-hidden="true" /> {t('studio_starter_20', '20 ta savol')}
                      </button>
                      <button
                        type="button"
                        className="btn sm ghost"
                        onClick={() => setPaste(TEMPLATE_MCQ_30)}
                      >
                        <Sparkles size={13} aria-hidden="true" /> {t('studio_starter_30', '30 ta savol')}
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
                    {t('studio_smart_import_title', 'Fayldan import (Word, Excel, PDF, CSV)')}
                  </h3>
                  <p className="muted small" style={{ marginBottom: 16 }}>
                    {t(
                      'studio_smart_import_desc',
                      'Word yoki PDF: “1. Savol”, “A) … D)” va “Javob: B” ko‘rinishida. Excel/CSV: Savol, A, B, C, D, Javob ustunlari. Hech narsa avtomatik saqlanmaydi — avval tekshirasiz.',
                    )}
                  </p>

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".docx,.pptx,.xlsx,.pdf,.csv,.txt,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/pdf,text/csv,text/plain"
                    aria-label={t('studio_smart_import_title', 'Fayldan import (Word, Excel, PDF, CSV)')}
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
                    role="button"
                    tabIndex={0}
                    onClick={() => fileInputRef.current?.click()}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        fileInputRef.current?.click();
                      }
                    }}
                  >
                    <Upload size={32} style={{ margin: '0 auto 12px', color: 'var(--primary)' }} />
                    <p style={{ fontWeight: 600, marginBottom: 4 }}>
                      {busy === 'import' ? t('loading', 'Yuklanmoqda...') : t('studio_upload_file_btn', 'Faylni tanlang')}
                    </p>
                    <span className="muted small">.docx · .pptx · .xlsx · .pdf · .csv · .txt</span>
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
                          <strong>{t('studio_detected_qs', 'Aniqlangan savollar')}: {fileImportPreview.questions_count}</strong>
                          {fileImportPreview.report && (
                            <ul className="small studio-import-report" aria-label={t('studio_import_report', 'Import hisoboti')} style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                              <li>{t('studio_report_valid', 'To‘liq savollar')}: {fileImportPreview.report.valid_questions}</li>
                              <li style={{ color: fileImportPreview.report.missing_answers ? 'var(--danger, #DC2626)' : undefined }}>
                                {t('studio_report_missing', 'Javob kaliti yo‘q')}: {fileImportPreview.report.missing_answers}
                              </li>
                              {fileImportPreview.report.duplicate_options > 0 && (
                                <li>{t('studio_report_dup_options', 'Takror variantli savollar')}: {fileImportPreview.report.duplicate_options}</li>
                              )}
                              {fileImportPreview.report.duplicate_numbers.length > 0 && (
                                <li>{t('studio_report_dup_numbers', 'Takror raqamlar')}: {fileImportPreview.report.duplicate_numbers.join(', ')}</li>
                              )}
                            </ul>
                          )}
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
                          <span>⚠️ {t('studio_import_warnings', 'Ogohlantirishlar')}: {fileImportPreview.warnings.length}</span>
                          <ul style={{ margin: '4px 0 0 16px', fontSize: '0.85rem' }}>
                            {fileImportPreview.warnings.slice(0, 20).map((w, idx) => (
                              <li key={idx}>
                                {w.row ? `${t('studio_row', 'Qator')} ${w.row}: ` : ''}
                                {w.slide ? `${t('studio_slide', 'Slayd')} ${w.slide}: ` : ''}
                                {t(`studio_warn_${w.code}`, w.code)}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <div className="table-wrap" style={{ maxHeight: 360, overflowY: 'auto' }}>
                        <table className="data" style={{ fontSize: '0.85rem' }} aria-label={t('studio_detected_qs', 'Aniqlangan savollar')}>
                          <thead>
                            <tr>
                              <th>№</th>
                              {fileImportPreview.source?.kind === 'pptx' && <th>{t('studio_slide', 'Slayd')}</th>}
                              <th>{t('question', 'Savol')}</th>
                              <th>{t('choices', 'Variantlar')}</th>
                              <th>{t('answer', 'Kalit')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {/* Every detected question from every block — nothing hidden from review. */}
                            {fileImportPreview.blocks.flatMap((b, bi) =>
                              b.questions.map((q) => (
                                <tr key={`${bi}-${q.number}`} className={q.answer ? undefined : 'is-invalid'}>
                                  <td>{q.number}</td>
                                  {fileImportPreview.source?.kind === 'pptx' && <td>{q.slide ?? '—'}</td>}
                                  <td>{q.text}</td>
                                  <td>{(q.options.length ? q.options : b.options).join(' | ')}</td>
                                  <td>
                                    <strong style={{ color: q.answer ? undefined : 'var(--danger, #DC2626)' }}>
                                      {q.answer || t('studio_report_missing', 'Javob kaliti yo‘q')}
                                    </strong>
                                  </td>
                                </tr>
                              )),
                            )}
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
                  <span>{t(`studio_category_${meta.assessment_category}`, meta.assessment_category)}</span>
                  <span>·</span>
                  <span>{meta.time_limit_minutes > 0 ? `${meta.time_limit_minutes} ${t('minutes_short', 'daq')}` : t('studio_time_untimed', 'Vaqt cheklovisiz')}</span>
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
