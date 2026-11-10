import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Flag, LayoutGrid, ChevronLeft, Highlighter, FileText, CheckCircle2, X } from 'lucide-react';
import { useLang } from '../../i18n/LangContext';
import { Tests as TestsApi } from '../../lib/api';
import AutoGrow from '../../components/AutoGrow';
import { useAnswerQueue, type SavePayload } from '../../lib/useAnswerQueue';
import { revealOnFocus, useIsNarrow, useKeyboardOpen, useVisualViewport } from '../../lib/useVisualViewport';
import CefrResultSummary, { type CefrSummary } from './CefrResultSummary';
import IeltsResultSummary, { type IeltsSummary } from './IeltsResultSummary';

/* ------------------------------------------------------------------ types */

interface CdChoice { id: number; text: string; position: number }
interface CdQuestion {
  id: number;
  text: string;
  question_type: string;
  section_id: number | null;
  group_id: number | null;
  config: {
    number?: number;
    min_words?: number;
    max_words?: number;
    target_words?: number;
    prep_seconds?: number;
    answer_seconds?: number;
    for?: string[];
    against?: string[];
  };
  choices: CdChoice[];
  selected_choice_ids?: number[];
  text_answer?: string;
  written_text?: string;
}
interface CdGroup {
  id: number;
  title: string;
  instructions: string;
  answer_rule: string;
  passage_id: number | null;
  image_url: string;
  options_label: string;
  each_option_once: boolean;
}
interface CdPart { id: number; number: string; title: string; instructions: string; audio_url: string; groups: CdGroup[] }
interface CdSection { section_id: number; code: string; name: string; duration_minutes: number; parts: CdPart[] }
export interface CdAttempt {
  id: number;
  test_title: string;
  is_preview?: boolean;
  is_trial?: boolean;
  remaining_seconds: number | null;
  structure: CdSection[];
  questions: CdQuestion[];
  passages?: { id: number; title: string; content: string }[];
}

interface Answer { choice?: number; text?: string; written?: string }

const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const SELECT_TYPES = new Set(['MATCHING', 'MAP_LABELING', 'HEADING_MATCHING']);
const GAP_RE = /\(\d+\)\s*_{2,}/;
const FONT_SIZES = [16, 18, 20];

const isAnswered = (a?: Answer) =>
  !!a && (a.choice != null || !!a.text?.trim() || !!a.written?.trim());

const wordCount = (text = '') => text.trim().split(/\s+/).filter(Boolean).length;

const fmt = (secs: number) => {
  const s = Math.max(0, Math.floor(secs));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

const read = (store: Storage, key: string): string | null => {
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
};
const write = (store: Storage, key: string, value: string) => {
  try {
    store.setItem(key, value);
  } catch {
    /* private mode / quota: the feature degrades, the exam still works */
  }
};

/** Section deadline survives reloads: first visit fixes it in sessionStorage. */
function sectionDeadline(attemptId: number, section: CdSection): number | null {
  if (!section.duration_minutes) return null;
  const key = `cd-exam:${attemptId}:${section.section_id}`;
  const saved = Number(read(sessionStorage, key));
  if (saved) return saved;
  const deadline = Date.now() + section.duration_minutes * 60_000;
  write(sessionStorage, key, String(deadline));
  return deadline;
}

/* -------------------------------------------------------------- component */

/**
 * Computer-delivered exam driven entirely by the attempt API:
 * section → part → group → question. Answer keys never reach the client;
 * every change is saved to the backend, which does all checking.
 *
 * Mobile first: compact header with an always-visible timer, a scrollable
 * section/part picker, one pane at a time (text | questions) on phones, a sticky
 * bottom bar (previous / question palette / next) and answers that are queued and
 * retried when the connection drops.
 */
export default function CdExamInterface({ attempt }: { attempt: CdAttempt }) {
  const { t } = useLang();
  const navigate = useNavigate();
  const attemptId = String(attempt.id);
  const narrow = useIsNarrow();
  const keyboardOpen = useKeyboardOpen();
  useVisualViewport(true);

  const send = useCallback((payload: SavePayload) => TestsApi.saveAnswer(attemptId, payload), [attemptId]);
  const queue = useAnswerQueue(attemptId, send);

  const [answers, setAnswers] = useState<Record<number, Answer>>(() => {
    const init: Record<number, Answer> = {};
    for (const q of attempt.questions) {
      init[q.id] = {
        choice: q.selected_choice_ids?.[0],
        text: q.text_answer || '',
        written: q.written_text || '',
      };
    }
    // Answers that never reached the server before a reload.
    for (const p of Object.values(queue.initial)) {
      const prev = init[p.question_id];
      if (!prev) continue;
      if (p.choice_ids?.length) prev.choice = p.choice_ids[0];
      else if (p.written_text !== undefined) prev.written = p.written_text;
      else if (p.text_answer !== undefined) prev.text = p.text_answer;
    }
    return init;
  });

  const sections = attempt.structure;
  const [pos, setPos] = useState<{ s: number; p: number }>(() => {
    const saved = (read(sessionStorage, `cd-pos:${attemptId}`) || '').split(',').map(Number);
    const s = saved[0] >= 0 && saved[0] < sections.length ? saved[0] : 0;
    const p = saved[1] >= 0 && saved[1] < (sections[s]?.parts.length ?? 0) ? saved[1] : 0;
    return { s, p };
  });
  const [now, setNow] = useState(() => Date.now());
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<CefrSummary | null | 'done'>(null);
  const [ielts, setIelts] = useState<IeltsSummary | null>(null);
  const [resultId, setResultId] = useState<number | null>(null);
  const [showNotice, setShowNotice] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [pane, setPane] = useState<'text' | 'questions'>('text');
  const [fontStep] = useState(() => Math.min(2, Math.max(0, Number(read(localStorage, 'cd-font')) || 0)));
  const [flagged, setFlagged] = useState<Set<number>>(
    () => new Set((read(sessionStorage, `cd-flags:${attemptId}`) || '').split(',').filter(Boolean).map(Number)),
  );
  const textTimers = useRef<Record<number, number>>({});
  const submittedRef = useRef(false);
  const scrollTo = useRef<number | null>(null);

  // Zen highlight & note tools
  const [highlightColor, setHighlightColor] = useState<'yellow' | 'green'>('yellow');
  const [highlightActive, setHighlightActive] = useState(false);
  const [selectedText, setSelectedText] = useState('');
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteContent, setNoteContent] = useState('');
  const [notes, setNotes] = useState<Record<number, string[]>>({});
  const [highlights, setHighlights] = useState<Record<number, { text: string; color: string }[]>>(() => {
    try {
      const saved = sessionStorage.getItem(`cd-highlights:${attemptId}`);
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  const saveHighlights = useCallback((newH: Record<number, { text: string; color: string }[]>) => {
    setHighlights(newH);
    try {
      sessionStorage.setItem(`cd-highlights:${attemptId}`, JSON.stringify(newH));
    } catch {
      // storage quota
    }
  }, [attemptId]);

  const addHighlight = useCallback((passageId: number, colorToUse?: 'yellow' | 'green', textToUse?: string) => {
    const txt = (textToUse || selectedText).trim();
    if (!txt || txt.length < 2) return;
    const color = colorToUse || highlightColor;
    const current = highlights[passageId] || [];
    if (!current.some((h) => h.text.toLowerCase() === txt.toLowerCase())) {
      const next = { ...highlights, [passageId]: [...current, { text: txt, color }] };
      saveHighlights(next);
    }
    setSelectedText('');
  }, [selectedText, highlightColor, highlights, saveHighlights]);

  const clearPassageHighlights = useCallback((passageId: number) => {
    const next = { ...highlights };
    delete next[passageId];
    saveHighlights(next);
    setSelectedText('');
  }, [highlights, saveHighlights]);

  const section = sections[pos.s];
  const part = section.parts[pos.p];

  const questionsByGroup = useMemo(() => {
    const map: Record<number, CdQuestion[]> = {};
    for (const q of attempt.questions) if (q.group_id != null) (map[q.group_id] ??= []).push(q);
    return map;
  }, [attempt.questions]);
  const passages = useMemo(
    () => Object.fromEntries((attempt.passages || []).map((p) => [p.id, p])),
    [attempt.passages],
  );
  const partQuestions = useCallback(
    (p: CdPart) => p.groups.flatMap((g) => questionsByGroup[g.id] || []),
    [questionsByGroup],
  );
  const sectionQuestions = useCallback(
    (s: CdSection) => s.parts.flatMap(partQuestions),
    [partQuestions],
  );

  // Flat order of every part: what "previous" and "next" walk through.
  const order = useMemo(() => sections.flatMap((s, si) => s.parts.map((_, pi) => ({ s: si, p: pi }))), [sections]);
  const at = order.findIndex((o) => o.s === pos.s && o.p === pos.p);
  const isLast = at === order.length - 1;

  const deadline = useMemo(() => sectionDeadline(attempt.id, section), [attempt.id, section]);
  const sectionLeft = deadline ? (deadline - now) / 1000 : null;
  const locked = sectionLeft != null && sectionLeft <= 0;
  const [examEndsAt] = useState(() =>
    attempt.remaining_seconds != null ? Date.now() + attempt.remaining_seconds * 1000 : null,
  );

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  // Position, flags and text size survive a reload.
  useEffect(() => {
    write(sessionStorage, `cd-pos:${attemptId}`, `${pos.s},${pos.p}`);
  }, [attemptId, pos]);
  useEffect(() => {
    write(sessionStorage, `cd-flags:${attemptId}`, [...flagged].join(','));
  }, [attemptId, flagged]);
  useEffect(() => {
    write(localStorage, 'cd-font', String(fontStep));
  }, [fontStep]);

  const goTo = useCallback((s: number, p: number, questionId?: number) => {
    setPos({ s, p });
    setPane('questions');
    scrollTo.current = questionId ?? null;
    if (questionId == null) window.scrollTo({ top: 0 });
  }, []);

  // Jump to a question after the part around it has rendered.
  useEffect(() => {
    if (scrollTo.current == null) return;
    const el = document.getElementById(`cdq-${scrollTo.current}`);
    scrollTo.current = null;
    el?.scrollIntoView({ block: 'center' });
    el?.querySelector<HTMLElement>('input, select, textarea')?.focus({ preventScroll: true });
  });

  /* ---------------------------------------------------- leave protection */
  const active = !result;
  useEffect(() => {
    if (!active) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [active]);

  useEffect(() => {
    if (!active) return;
    // One extra history entry: the browser's back button (and the Telegram in-app back button)
    // asks before leaving instead of dropping the exam.
    window.history.pushState({ cdExam: true }, '');
    const onPop = () => {
      window.history.pushState({ cdExam: true }, '');
      setLeaveOpen(true);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, [active]);

  /* ----------------------------------------------------------- submitting */
  const submit = useCallback(async () => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    setSubmitting(true);
    setSubmitError(null);
    try {
      // Every answer must reach the server before the attempt is closed.
      const ok = await queue.flush();
      if (!ok) {
        submittedRef.current = false;
        setSubmitError(t('cd_unsent'));
        return;
      }
      const submitted = (await TestsApi.submit(attemptId)) as unknown as {
        result?: { correct_answers?: number; total_questions?: number; result_id?: number | null };
      };
      setResultId(submitted?.result?.result_id ?? null);
      if (attempt.is_trial) {
        setResult('done');
        return;
      }
      try {
        const card = (await TestsApi.certificateCard(attemptId)) as unknown as CefrSummary & {
          exam_type?: string;
          overall_band?: number | null;
          show_estimate_notice?: boolean;
        };
        setShowNotice(Boolean(card.show_estimate_notice));
        if (card.scale === 'cefr_multilevel') {
          setResult(card);
        } else if (/ielts/i.test(card.exam_type ?? '') && submitted?.result?.total_questions) {
          setIelts({
            correct: Number(submitted.result.correct_answers ?? 0),
            total: Number(submitted.result.total_questions),
            band: typeof card.overall_band === 'number' ? card.overall_band : null,
          });
          setResult('done');
        } else {
          setResult('done');
        }
      } catch {
        setResult('done');
      }
    } catch (e) {
      submittedRef.current = false;
      setSubmitError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
      setConfirming(false);
    }
  }, [attemptId, attempt.is_trial, queue, t]);

  // Whole-exam time limit (enforced by the backend too).
  useEffect(() => {
    if (examEndsAt && now >= examEndsAt) void submit();
  }, [now, examEndsAt, submit]);

  const save = useCallback(
    (q: CdQuestion, a: Answer) => {
      const payload: SavePayload =
        q.question_type === 'written'
          ? { question_id: q.id, written_text: a.written || '' }
          : a.choice != null
            ? { question_id: q.id, choice_ids: [a.choice] }
            : { question_id: q.id, text_answer: a.text || '' };
      queue.enqueue(payload);
    },
    [queue],
  );

  const update = (q: CdQuestion, patch: Answer, debounce = false) => {
    if (locked) return;
    const next = { ...answers[q.id], ...patch };
    setAnswers((prev) => ({ ...prev, [q.id]: next }));
    window.clearTimeout(textTimers.current[q.id]);
    if (debounce) textTimers.current[q.id] = window.setTimeout(() => save(q, next), 500);
    else save(q, next);
  };

  const toggleFlag = (id: number) =>
    setFlagged((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const evaluableQuestions = attempt.questions.filter((q) => q.question_type !== 'SPEAKING_PROMPT');
  const answeredCount = evaluableQuestions.filter((q) => isAnswered(answers[q.id])).length;
  const unanswered = evaluableQuestions.length - answeredCount;
  const flaggedCount = flagged.size;

  /* ---------------------------------------------------------- result view */
  if (result) {
    if (attempt.is_trial && resultId) return <Navigate to={`/results/${resultId}`} replace />;
    return (
      <div className="cefr-result-page">
        <h1>{attempt.test_title}</h1>
        {attempt.is_trial ? (
          <p className="cd-preview-badge">{t('cd_trial_badge')}</p>
        ) : (
          attempt.is_preview && <p className="cd-preview-badge">{t('cd_preview_badge')}</p>
        )}
        {result !== 'done' ? (
          <CefrResultSummary data={result} showEstimateNotice={showNotice} />
        ) : ielts ? (
          <IeltsResultSummary data={ielts} showEstimateNotice={showNotice} />
        ) : (
          <div className="card">{t(attempt.is_trial ? 'cd_trial_done' : 'cd_submitted')}</div>
        )}
        <div className="error-boundary-actions">
          {resultId && (
            <Link to={`/results/${resultId}`} className="btn primary">{t('cd_view_review')}</Link>
          )}
          <Link to="/results" className="btn">{t('my_results')}</Link>
          <Link to="/tests" className="btn">{t('error_boundary_back')}</Link>
        </div>
      </div>
    );
  }

  /* ------------------------------------------------------------ renderers */
  const flagButton = (q: CdQuestion) => (
    <button
      type="button"
      className={`cd-flag${flagged.has(q.id) ? ' on' : ''}`}
      aria-pressed={flagged.has(q.id)}
      aria-label={t(flagged.has(q.id) ? 'cd_unflag' : 'cd_flag')}
      onClick={() => toggleFlag(q.id)}
    >
      <Flag size={16} aria-hidden="true" />
    </button>
  );

  const focusNextGap = (from: HTMLElement) => {
    const gaps = [...document.querySelectorAll<HTMLElement>('.cd-gap')];
    const following = gaps[gaps.indexOf(from) + 1];
    if (following) following.focus();
    else from.blur();
  };

  const renderQuestion = (q: CdQuestion, group: CdGroup, siblings: CdQuestion[]) => {
    const a = answers[q.id] || {};
    const num = q.config.number;
    const choices = [...q.choices].sort((x, y) => x.position - y.position);

    if (q.question_type === 'SPEAKING_PROMPT') return <SpeakingPrompt key={q.id} q={q} />;

    if (q.question_type === 'written') {
      const words = wordCount(a.written);
      const { min_words: min, max_words: max, target_words: target } = q.config;
      const range = target ? `~${target}` : min && max ? `${min}–${max}` : '';
      const outside = (min && words < min) || (max && words > max);
      return (
        <div key={q.id} id={`cdq-${q.id}`} className="cd-question cd-written">
          <p className="cd-prompt">{q.text}</p>
          {range && <p className="cd-range">{t('cd_word_target').replace('{range}', range)}</p>}
          <AutoGrow
            value={a.written || ''}
            disabled={locked}
            onChange={(e) => update(q, { written: e.target.value }, true)}
            onFocus={revealOnFocus}
            rows={8}
            aria-label={t('cd_writing_area')}
            autoCapitalize="sentences"
            spellCheck
          />
          <p className={`cd-word-count${outside ? ' warn' : ''}`} aria-live="polite">
            {words} {t('cd_words')}
            {range && ` · ${range}`}
          </p>
        </div>
      );
    }

    if (q.question_type === 'INLINE_GAP_FILL') {
      const input = (
        <input
          className="cd-gap"
          type="text"
          value={a.text || ''}
          disabled={locked}
          onChange={(e) => update(q, { text: e.target.value }, true)}
          onFocus={revealOnFocus}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              focusNextGap(e.currentTarget);
            }
          }}
          aria-label={`${t('cd_question')} ${num}`}
          autoComplete="off"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          enterKeyHint="next"
        />
      );
      const [before, after] = q.text.split(GAP_RE);
      return (
        <div key={q.id} id={`cdq-${q.id}`} className="cd-question cd-inline">
          <span className="cd-num">{num}</span>
          {after !== undefined ? (
            <p>{before}{input}{after}</p>
          ) : (
            <p>{q.text} {input}</p>
          )}
          {flagButton(q)}
        </div>
      );
    }

    if (SELECT_TYPES.has(q.question_type)) {
      const taken = group.each_option_once
        ? new Set(siblings.filter((s) => s.id !== q.id).map((s) => answers[s.id]?.choice))
        : new Set<number | undefined>();
      return (
        <div key={q.id} id={`cdq-${q.id}`} className="cd-question cd-select">
          <span className="cd-num">{num}</span>
          <label className="cd-select-text" htmlFor={`cds-${q.id}`}>{q.text}</label>
          <select
            id={`cds-${q.id}`}
            value={a.choice ?? ''}
            disabled={locked}
            onChange={(e) => update(q, { choice: e.target.value ? Number(e.target.value) : undefined, text: '' })}
          >
            <option value="">{t('cd_choose')}</option>
            {choices.map((c, i) => (
              <option key={c.id} value={c.id} disabled={taken.has(c.id)}>
                {LETTERS[i]}. {c.text.length > 70 ? `${c.text.slice(0, 68)}…` : c.text}
              </option>
            ))}
          </select>
          {flagButton(q)}
        </div>
      );
    }

    // MULTIPLE_CHOICE / TRUE_FALSE_NOT_GIVEN
    const tfng = q.question_type === 'TRUE_FALSE_NOT_GIVEN';
    return (
      <fieldset key={q.id} id={`cdq-${q.id}`} className="cd-question cd-choice">
        <legend>
          <span className="cd-num">{num}</span> {q.text}
        </legend>
        <div className={tfng ? 'cd-options inline' : 'cd-options'}>
          {choices.map((c, i) => (
            <label key={c.id} className={a.choice === c.id ? 'cd-option selected' : 'cd-option'}>
              <input
                type="radio"
                name={`q-${q.id}`}
                checked={a.choice === c.id}
                disabled={locked}
                onChange={() => update(q, { choice: c.id, text: '' })}
              />
              <span>{!tfng && <b>{LETTERS[i]}</b>} {c.text}</span>
            </label>
          ))}
        </div>
        <div className="cd-question__tools">{flagButton(q)}</div>
      </fieldset>
    );
  };

  const renderGroup = (group: CdGroup) => {
    const qs = questionsByGroup[group.id] || [];
    const shared = group.options_label && qs[0]?.choices.some((c) => c.text.length > 1) ? qs[0].choices : [];
    return (
      <section key={group.id} className="cd-group">
        {group.title && <h3>{group.title}</h3>}
        {group.instructions && <p className="cd-instructions">{group.instructions}</p>}
        {group.answer_rule && (
          <p className="cd-rule">
            {t('cd_answer_rule')}: <strong>{group.answer_rule}</strong>
          </p>
        )}
        {group.image_url && <img className="cd-image" src={group.image_url} alt={group.title || t('cd_picture')} />}
        {shared.length > 0 && (
          <div className="cd-shared-options">
            <p className="cd-options-label">{group.options_label}</p>
            <ol>
              {[...shared].sort((x, y) => x.position - y.position).map((c, i) => (
                <li key={c.id}><b>{LETTERS[i]}</b> {c.text}</li>
              ))}
            </ol>
          </div>
        )}
        <div className="cd-questions">{qs.map((q) => renderQuestion(q, group, qs))}</div>
      </section>
    );
  };

  const partPassages = [...new Set(part.groups.map((g) => g.passage_id).filter((id): id is number => id != null))]
    .map((id) => passages[id])
    .filter(Boolean);
  const hasText = partPassages.length > 0;
  const showText = hasText && (!narrow || pane === 'text');
  const showQuestions = !hasText || !narrow || pane === 'questions';
  const prev = at > 0 ? order[at - 1] : null;
  const next = at < order.length - 1 ? order[at + 1] : null;
  const partObjective = partQuestions(part).filter((q) => q.question_type !== 'SPEAKING_PROMPT');
  const partAnswered = partObjective.filter((q) => isAnswered(answers[q.id])).length;

  const saveLabel =
    queue.state === 'saved'
      ? t('cd_saved')
      : queue.state === 'saving'
        ? t('cd_saving')
        : queue.state === 'offline'
          ? t('cd_offline_short')
          : t('cd_save_failed_short');

  const currentPartQs = partObjective;
  const firstQNum = currentPartQs[0]?.config?.number ?? 1;
  const lastQNum = currentPartQs[currentPartQs.length - 1]?.config?.number ?? (currentPartQs.length || 1);

  const renderPassageWithHighlights = (p: { id: number; content: string }) => {
    const list = highlights[p.id] || [];
    if (!list.length) return p.content;

    const sorted = [...list].sort((a, b) => b.text.length - a.text.length);
    const escaped = sorted.map((h) => h.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
    const regex = new RegExp(`(${escaped})`, 'gi');
    const parts = p.content.split(regex);

    return parts.map((part, idx) => {
      const hit = sorted.find((h) => h.text.toLowerCase() === part.toLowerCase());
      if (hit) {
        const bg = hit.color === 'green' ? 'rgba(16, 185, 129, 0.28)' : 'rgba(251, 191, 36, 0.28)';
        const border = hit.color === 'green' ? '#10B981' : '#F59E0B';
        return (
          <mark
            key={idx}
            style={{
              background: bg,
              borderRadius: 4,
              padding: '2px 4px',
              borderBottom: `2px solid ${border}`,
              color: 'inherit',
            }}
          >
            {part}
          </mark>
        );
      }
      return part;
    });
  };

  /* -------------------------------------------------------------- layout */
  return (
    <div className={`cd-exam${keyboardOpen ? ' kb-open' : ''}`} style={{ ['--cd-font' as string]: `${FONT_SIZES[fontStep]}px` }}>
      {/* Zen Imtihon Yuqori Paneli */}
      <header
        className="cd-header"
        style={{
          minHeight: 56,
          padding: '0 16px',
          background: 'var(--bg-surface, #fff)',
          borderBottom: '1px solid var(--border-subtle, #e2e8f0)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 10,
        }}
      >
        {/* Chapda: Chiqish + Fan va Passage */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="button"
            className="bento-btn"
            onClick={() => setLeaveOpen(true)}
            style={{
              height: 36,
              padding: '0 12px',
              fontSize: 13,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-primary)',
              borderRadius: 10,
              cursor: 'pointer',
              fontWeight: 700,
            }}
          >
            <ChevronLeft size={16} /> Chiqish
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              className="pill-badge"
              style={{
                background: 'rgba(59, 130, 246, 0.12)',
                color: '#3B82F6',
                fontWeight: 800,
                fontSize: 12,
              }}
            >
              {section.name || 'Reading'}
            </span>
            <span style={{ fontWeight: 800, fontSize: 14, color: 'var(--text-primary)' }}>
              Passage {part.number || pos.p + 1}
            </span>
          </div>
        </div>

        {/* Markazda: Highlight va Izoh tugmalari */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              background: 'var(--bg-elevated)',
              padding: '3px 8px',
              borderRadius: 10,
              border: '1px solid var(--border-subtle)',
            }}
          >
            <button
              type="button"
              onClick={() => {
                setHighlightActive(!highlightActive);
                if (selectedText && partPassages[0]?.id) {
                  addHighlight(partPassages[0].id, highlightColor);
                }
              }}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 5,
                background: highlightActive ? 'rgba(245, 158, 11, 0.2)' : 'transparent',
                border: highlightActive ? '1px solid #F59E0B' : '1px solid transparent',
                borderRadius: 8,
                padding: '4px 8px',
                color: highlightActive ? '#D97706' : 'var(--text-primary)',
                fontWeight: 700,
                fontSize: 12.5,
                cursor: 'pointer',
              }}
            >
              <Highlighter size={14} /> Highlight
            </button>
            <button
              type="button"
              onClick={() => setHighlightColor('yellow')}
              title="Sariq belgilash"
              style={{
                width: 18,
                height: 18,
                borderRadius: '50%',
                background: '#FBBF24',
                border: highlightColor === 'yellow' ? '2px solid #fff' : 'none',
                outline: highlightColor === 'yellow' ? '2px solid #FBBF24' : 'none',
                cursor: 'pointer',
              }}
            />
            <button
              type="button"
              onClick={() => setHighlightColor('green')}
              title="Yashil belgilash"
              style={{
                width: 18,
                height: 18,
                borderRadius: '50%',
                background: '#10B981',
                border: highlightColor === 'green' ? '2px solid #fff' : 'none',
                outline: highlightColor === 'green' ? '2px solid #10B981' : 'none',
                cursor: 'pointer',
              }}
            />
          </div>

          <button
            type="button"
            onClick={() => setNoteOpen(true)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              padding: '6px 12px',
              borderRadius: 10,
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-primary)',
              fontWeight: 700,
              fontSize: 12.5,
              cursor: 'pointer',
            }}
          >
            <FileText size={14} /> Izoh
          </button>
        </div>

        {/* O'ngda: Taymer va Oltin Topshirish tugmasi */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {sectionLeft != null && (
            <span
              style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontWeight: 800,
                fontSize: 16,
                padding: '4px 12px',
                borderRadius: 999,
                background: sectionLeft < 300 ? 'rgba(239, 68, 68, 0.15)' : 'var(--bg-elevated)',
                border: sectionLeft < 300 ? '1px solid #EF4444' : '1px solid var(--border-subtle)',
                color: sectionLeft < 300 ? '#EF4444' : 'var(--text-primary)',
                letterSpacing: '0.04em',
              }}
            >
              ⏱ {fmt(sectionLeft)}
            </span>
          )}

          <button
            type="button"
            disabled={submitting}
            onClick={() => setConfirming(true)}
            className="bento-btn bento-btn-gold"
            style={{
              height: 38,
              padding: '0 16px',
              fontSize: 13,
              fontWeight: 800,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              boxShadow: '0 2px 10px rgba(245, 158, 11, 0.35)',
            }}
          >
            <CheckCircle2 size={16} /> Topshirish
          </button>
        </div>
      </header>

      <nav className="cd-picker" aria-label={t('cd_sections')}>
        <div className="cd-picker__row">
          {sections.map((s, i) => {
            const qs = sectionQuestions(s).filter((q) => q.question_type !== 'SPEAKING_PROMPT');
            const done = qs.filter((q) => isAnswered(answers[q.id])).length;
            return (
              <button
                key={s.section_id}
                type="button"
                className={i === pos.s ? 'active' : ''}
                aria-current={i === pos.s}
                onClick={() => goTo(i, 0)}
              >
                {s.name}
                {qs.length > 0 && <small> {done}/{qs.length}</small>}
              </button>
            );
          })}
        </div>
        {section.parts.length > 1 && (
          <div className="cd-picker__row" aria-label={t('cd_parts')}>
            {section.parts.map((p, i) => (
              <button
                key={p.id}
                type="button"
                className={p.id === part.id ? 'active' : ''}
                aria-current={p.id === part.id}
                onClick={() => goTo(pos.s, i)}
              >
                {t('cd_part')} {p.number}
              </button>
            ))}
          </div>
        )}
      </nav>

      {!queue.online && <p className="cd-alert" role="alert">{t('cd_offline_banner')}</p>}
      {queue.online && queue.justRestored && <p className="cd-alert ok" role="status">{t('cd_online_back')}</p>}
      {queue.online && queue.state === 'error' && <p className="cd-alert" role="alert">{t('cd_save_error')}</p>}
      {submitError && <p className="cd-alert" role="alert">{submitError}</p>}
      {locked && <p className="cd-alert" role="status">{t('cd_time_up')}</p>}

      {hasText && narrow && (
        <div className="cd-tabs" role="tablist" style={{ padding: '8px 12px', display: 'flex', gap: 8 }}>
          <button
            type="button"
            role="tab"
            aria-selected={pane === 'text'}
            className={pane === 'text' ? 'active' : ''}
            onClick={() => setPane('text')}
            style={{ flex: 1, borderRadius: 10, height: 42, fontWeight: 800 }}
          >
            📖 Matn
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={pane === 'questions'}
            className={pane === 'questions' ? 'active' : ''}
            onClick={() => setPane('questions')}
            style={{ flex: 1, borderRadius: 10, height: 42, fontWeight: 800 }}
          >
            ❓ Savollar ({firstQNum}-{lastQNum})
          </button>
        </div>
      )}

      {section.code === 'LISTENING' && part.audio_url && (
        <div className="cd-audio-bar">
          <audio className="cd-audio" controls preload="metadata" src={part.audio_url} />
        </div>
      )}

      <main className={hasText && !narrow ? 'cd-body with-passage' : 'cd-body'}>
        {showText && (
          <article
            className="cd-passage"
            onMouseUp={() => {
              const sel = window.getSelection()?.toString().trim();
              if (sel && sel.length >= 2 && sel.length <= 500) {
                setSelectedText(sel);
                if (highlightActive && partPassages[0]?.id) {
                  addHighlight(partPassages[0].id, highlightColor, sel);
                }
              }
            }}
          >
            {/* Highlight quick bar when selection is made */}
            {selectedText && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '6px 12px',
                  borderRadius: 8,
                  background: 'var(--bg-elevated)',
                  border: '1px solid #F59E0B',
                  marginBottom: 12,
                  gap: 8,
                }}
              >
                <span style={{ fontSize: 12, color: '#D97706', fontWeight: 600 }}>
                  Tanlangan: &quot;{selectedText.length > 30 ? selectedText.slice(0, 30) + '…' : selectedText}&quot;
                </span>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    type="button"
                    onClick={() => partPassages[0]?.id && addHighlight(partPassages[0].id, 'yellow')}
                    className="bento-btn"
                    style={{ height: 28, padding: '0 8px', fontSize: 11, background: '#FBBF24', color: '#000', fontWeight: 800 }}
                  >
                    Sariq
                  </button>
                  <button
                    type="button"
                    onClick={() => partPassages[0]?.id && addHighlight(partPassages[0].id, 'green')}
                    className="bento-btn"
                    style={{ height: 28, padding: '0 8px', fontSize: 11, background: '#10B981', color: '#fff', fontWeight: 800 }}
                  >
                    Yashil
                  </button>
                </div>
              </div>
            )}

            {partPassages.map((p) => (
              <div key={p.id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  {p.title && <h2 style={{ margin: 0 }}>{p.title}</h2>}
                  {(highlights[p.id]?.length ?? 0) > 0 && (
                    <button
                      type="button"
                      onClick={() => clearPassageHighlights(p.id)}
                      style={{
                        fontSize: 11,
                        padding: '2px 8px',
                        background: 'transparent',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 6,
                        color: 'var(--text-secondary)',
                        cursor: 'pointer',
                      }}
                    >
                      Tozalash ({highlights[p.id]?.length})
                    </button>
                  )}
                </div>
                <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>{renderPassageWithHighlights(p)}</p>
                {(notes[p.id] || []).length > 0 && (
                  <div style={{ marginTop: 12, padding: '8px 12px', background: 'var(--bg-elevated)', borderRadius: 10, border: '1px solid var(--border-subtle)' }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: '#D97706' }}>📝 Yozilgan izohlar:</span>
                    <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 13, color: 'var(--text-secondary)' }}>
                      {(notes[p.id] || []).map((n, ni) => (
                        <li key={ni}>{n}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </article>
        )}
        {showQuestions && (
          <div className="cd-part">
            {part.title && <h2>{part.title}</h2>}
            {part.instructions && <p className="cd-instructions">{part.instructions}</p>}
            {section.code === 'LISTENING' && !part.audio_url && <p className="cd-notice">{t('cd_audio_missing')}</p>}
            {section.code === 'SPEAKING' && <p className="cd-notice">{t('cd_speaking_note')}</p>}
            {part.groups.map(renderGroup)}
          </div>
        )}
      </main>

      <footer className="cd-bar">
        <button type="button" className="cd-bar__nav" disabled={!prev} onClick={() => prev && goTo(prev.s, prev.p)}>
          {t('cd_prev')}
        </button>
        <button type="button" className="cd-bar__center" onClick={() => setPaletteOpen(true)} aria-haspopup="dialog">
          <LayoutGrid size={18} aria-hidden="true" />
          <span className="cd-bar__count">{partAnswered}/{partObjective.length}</span>
          <span className={`cd-bar__save ${queue.state}`} role="status">{saveLabel}</span>
        </button>
        {isLast ? (
          <button type="button" className="cd-bar__nav primary" disabled={submitting} onClick={() => setConfirming(true)}>
            {t('cd_finish_short')}
          </button>
        ) : (
          <button type="button" className="cd-bar__nav primary" onClick={() => next && goTo(next.s, next.p)}>
            {t('cd_next')}
          </button>
        )}
      </footer>

      {paletteOpen && (
        <div className="sheet-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setPaletteOpen(false)}>
          <div className="sheet cd-palette" role="dialog" aria-modal="true" aria-label={t('cd_palette')}>
            <div className="sheet__grip" aria-hidden="true" />
            <h2 className="sheet__title">{t('cd_palette')}</h2>
            <ul className="cd-legend">
              <li><i className="dot answered" /> {t('cd_legend_answered')}</li>
              <li><i className="dot" /> {t('cd_legend_empty')}</li>
              <li><i className="dot flagged" /> {t('cd_legend_flagged')}</li>
            </ul>
            {sections.map((s, si) => (
              <div key={s.section_id} className="cd-palette__section">
                <h3>{s.name}</h3>
                {s.parts.map((p, pi) => {
                  const qs = partQuestions(p).filter((q) => q.question_type !== 'SPEAKING_PROMPT');
                  if (qs.length === 0) return null;
                  return (
                    <div key={p.id} className="cd-palette__part">
                      <button type="button" className="cd-palette__partname" onClick={() => { goTo(si, pi); setPaletteOpen(false); }}>
                        {t('cd_part')} {p.number}
                      </button>
                      <div className="cd-grid">
                        {qs.map((q) => (
                          <button
                            key={q.id}
                            type="button"
                            className={`cd-cell${isAnswered(answers[q.id]) ? ' answered' : ''}${flagged.has(q.id) ? ' flagged' : ''}${si === pos.s && pi === pos.p ? ' here' : ''}`}
                            aria-label={`${t('cd_question')} ${q.config.number}`}
                            onClick={() => { goTo(si, pi, q.id); setPaletteOpen(false); }}
                          >
                            {q.config.number}
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
            <div className="sheet__actions">
              <button type="button" className="ui-btn" onClick={() => setPaletteOpen(false)}>{t('cd_cancel')}</button>
            </div>
          </div>
        </div>
      )}

      {confirming && (
        <div className="cd-modal" role="dialog" aria-modal="true">
          <div className="card" style={{ maxWidth: 480, padding: 24, borderRadius: 16 }}>
            <h3 style={{ margin: '0 0 16px 0', fontSize: '1.2rem', fontWeight: 800 }}>
              🏁 Imtihonni yakunlashni tasdiqlaysizmi?
            </h3>

            {/* 3-Column Summary Cards */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 10,
                marginBottom: 16,
              }}
            >
              <div
                style={{
                  padding: '12px 10px',
                  borderRadius: 12,
                  background: 'rgba(16, 185, 129, 0.1)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  textAlign: 'center',
                }}
              >
                <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#10b981' }}>{answeredCount}</div>
                <div style={{ fontSize: '0.75rem', color: '#10b981', fontWeight: 600 }}>Javob berilgan</div>
              </div>

              <div
                style={{
                  padding: '12px 10px',
                  borderRadius: 12,
                  background: unanswered === 0 ? 'rgba(255, 255, 255, 0.04)' : 'rgba(239, 68, 68, 0.1)',
                  border: unanswered === 0 ? '1px solid rgba(255, 255, 255, 0.1)' : '1px solid rgba(239, 68, 68, 0.3)',
                  textAlign: 'center',
                }}
              >
                <div style={{ fontSize: '1.3rem', fontWeight: 800, color: unanswered === 0 ? 'var(--text-secondary)' : '#ef4444' }}>
                  {unanswered}
                </div>
                <div style={{ fontSize: '0.75rem', color: unanswered === 0 ? 'var(--text-secondary)' : '#ef4444', fontWeight: 600 }}>
                  Javobsiz qolgan
                </div>
              </div>

              <div
                style={{
                  padding: '12px 10px',
                  borderRadius: 12,
                  background: flaggedCount > 0 ? 'rgba(245, 158, 11, 0.12)' : 'rgba(255, 255, 255, 0.04)',
                  border: flaggedCount > 0 ? '1px solid rgba(245, 158, 11, 0.4)' : '1px solid rgba(255, 255, 255, 0.1)',
                  textAlign: 'center',
                }}
              >
                <div style={{ fontSize: '1.3rem', fontWeight: 800, color: flaggedCount > 0 ? '#f59e0b' : 'var(--text-secondary)' }}>
                  {flaggedCount}
                </div>
                <div style={{ fontSize: '0.75rem', color: flaggedCount > 0 ? '#f59e0b' : 'var(--text-secondary)', fontWeight: 600 }}>
                  Belgilangan
                </div>
              </div>
            </div>

            {unanswered > 0 && (
              <p style={{ fontSize: 13, color: '#f59e0b', margin: '0 0 16px' }}>
                ⚠️ Diqqat: {unanswered} ta savolga hali javob belgilanmagan.
              </p>
            )}

            <div className="error-boundary-actions" style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button type="button" className="btn" onClick={() => setConfirming(false)} disabled={submitting}>
                {t('cd_cancel')}
              </button>
              <button type="button" className="btn primary" onClick={() => void submit()} disabled={submitting}>
                {submitting ? t('cd_submitting') : t('cd_finish_yes')}
              </button>
            </div>
          </div>
        </div>
      )}

      {leaveOpen && (
        <div className="cd-modal" role="alertdialog" aria-modal="true">
          <div className="card">
            <h2>{t('cd_leave_title')}</h2>
            <p>{t('cd_leave_text')}</p>
            <div className="error-boundary-actions">
              <button type="button" className="btn primary" onClick={() => setLeaveOpen(false)}>{t('cd_leave_stay')}</button>
              <button type="button" className="btn" onClick={() => navigate('/tests')}>{t('cd_leave_exit')}</button>
            </div>
          </div>
        </div>
      )}

      {noteOpen && (
        <div className="cd-modal" role="dialog" aria-modal="true">
          <div className="card" style={{ maxWidth: 440, textAlign: 'left' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800 }}>
                📝 Matnga izoh yozish
              </h3>
              <button
                type="button"
                onClick={() => setNoteOpen(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}
              >
                <X size={18} />
              </button>
            </div>
            {selectedText && (
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', background: 'var(--bg-elevated)', padding: '6px 10px', borderRadius: 8, margin: '0 0 10px' }}>
                &quot;{selectedText.length > 60 ? selectedText.slice(0, 60) + '…' : selectedText}&quot;
              </p>
            )}
            <textarea
              value={noteContent}
              onChange={(e) => setNoteContent(e.target.value)}
              placeholder="Fikr yoki eslatmangizni kiriting..."
              rows={4}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: 10,
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-elevated)',
                color: 'var(--text-primary)',
                fontSize: 14,
                marginBottom: 12,
                outline: 'none',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                type="button"
                className="bento-btn"
                onClick={() => {
                  setNoteOpen(false);
                  setNoteContent('');
                }}
                style={{ height: 36, padding: '0 12px', fontSize: 13 }}
              >
                Bekor qilish
              </button>
              <button
                type="button"
                className="bento-btn bento-btn-gold"
                onClick={() => {
                  if (noteContent.trim() && partPassages[0]?.id) {
                    const pId = partPassages[0].id;
                    setNotes((prev) => ({
                      ...prev,
                      [pId]: [...(prev[pId] || []), noteContent.trim()],
                    }));
                  }
                  setNoteOpen(false);
                  setNoteContent('');
                }}
                style={{ height: 36, padding: '0 14px', fontSize: 13 }}
              >
                Saqlash
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Speaking task: prompt, optional For/Against table and prep/answer timers. */
function SpeakingPrompt({ q }: { q: CdQuestion }) {
  const { t } = useLang();
  const [phase, setPhase] = useState<'idle' | 'prep' | 'speak' | 'done'>('idle');
  const [left, setLeft] = useState(0);
  const prep = q.config.prep_seconds || 0;
  const speak = q.config.answer_seconds || 0;

  useEffect(() => {
    if (phase !== 'prep' && phase !== 'speak') return;
    if (left <= 0) {
      if (phase === 'prep') {
        setPhase('speak');
        setLeft(speak);
      } else setPhase('done');
      return;
    }
    const id = window.setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(id);
  }, [phase, left, speak]);

  const start = () => {
    if (prep) {
      setPhase('prep');
      setLeft(prep);
    } else {
      setPhase('speak');
      setLeft(speak);
    }
  };

  return (
    <div className="cd-question cd-speaking">
      <p className="cd-prompt">
        <span className="cd-num">{q.config.number}</span> {q.text}
      </p>
      {(q.config.for || q.config.against) && (
        <div className="cd-for-against">
          <div>
            <b>{t('cd_for')}</b>
            <ul>{q.config.for?.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
          <div>
            <b>{t('cd_against')}</b>
            <ul>{q.config.against?.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
        </div>
      )}
      <div className="cd-speaking-timer">
        <span className="muted small">
          {prep ? `${t('cd_prep')}: ${fmt(prep)} · ` : ''}
          {t('cd_speak')}: {fmt(speak)}
        </span>
        {phase === 'idle' || phase === 'done' ? (
          <button type="button" className="btn sm" onClick={start}>
            {t('cd_start_timer')}
          </button>
        ) : (
          <strong>
            {phase === 'prep' ? t('cd_prep') : t('cd_speak')}: {fmt(left)}
          </strong>
        )}
      </div>
    </div>
  );
}
