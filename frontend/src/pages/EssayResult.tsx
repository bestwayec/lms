import { formatDisplayName } from '../lib/displayName';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useLang } from '../i18n/LangContext';
import { essayStatus } from '../lib/essays';
import { useAuth } from '../auth/AuthContext';
import { Essays } from '../lib/api';
import ScoreCardModal from '../components/ScoreCardModal';
import InlineEssayHighlighter, { type HighlightError } from '../components/InlineEssayHighlighter';
import {
  countEssayWords,
  isEssayDone,
  isEssayTerminal,
  requestTeacherReview,
} from '../lib/essays-arena';

/**
 * Essay result — GET /tma/api/essays/<id>/result/ (JWT), polled while the
 * status is non-terminal.
 *
 * Layout uses progressive disclosure so a student sees the essentials first:
 *   1. Hero: score (BMB grade or IELTS band + CEFR), words, time spent,
 *      and the top 3 next steps.
 *   2. Tabs: criteria (grouped accordions) · corrections (before → after
 *      cards) · the essay with inline fixes · the AI model answer.
 * Everything shown comes from the API; nothing is invented when a field is
 * missing — the block is simply hidden.
 */

interface SpellingError {
  word: string;
  correction: string;
  explanation: string;
}

interface Criterion {
  id: number;
  name: string;
  score: number;
  max_score?: number;
  reason: string;
  errors?: string[];
}

interface Result {
  status: string;
  grading_source?: 'ai' | 'cache' | 'mock' | string;
  cached?: boolean;
  total_score: number | null;
  max_score: number;
  converted_score: number | null;
  score_percentage?: number;
  final_score: number | null;
  summary: string;
  word_count: number;
  is_off_topic: boolean;
  is_completely_off_topic?: boolean;
  topic_status?: string;
  topic_match_reason?: string;
  topic_title: string;
  topic_id?: number | null;
  essay_text?: string;
  can_retry?: boolean;
  criteria: Criterion[];
  spelling_errors?: SpellingError[];
  strengths?: string[];
  weaknesses?: string[];
  teacher_recommendation?: string;
  improved_text?: string;
  graded_at?: string | null;
  poll_after?: number;
  error?: string | null;
  subject?: string;
  rubric_type?: string;
  overall_band?: number | null;
  cefr_level?: string | null;
  time_spent_seconds?: number | null;
}

type Tab = 'criteria' | 'corrections' | 'essay' | 'improved';

/** BMB 12 criteria grouped by what the student has to work on. */
const BMB_GROUPS: Array<{ key: string; ids: number[] }> = [
  { key: 'er_group_content', ids: [1, 3, 10, 12] },
  { key: 'er_group_structure', ids: [2, 9, 11] },
  { key: 'er_group_language', ids: [4, 5] },
  { key: 'er_group_accuracy', ids: [6, 7, 8] },
];

const fmt = (s: string, vars: Record<string, string | number>) =>
  Object.entries(vars).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(String(v)), s);

const num = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));

const escapeRe = (w: string) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** "quoted original → rewrite" evidence (as the grading prompt asks for). */
function splitEvidence(raw: string): { before: string; after: string | null } {
  const clean = (s: string) => s.trim().replace(/^["“«']+|["”»']+$/g, '').trim();
  const parts = String(raw ?? '').split(/\s*(?:→|->|➔|=>)\s*/);
  if (parts.length >= 2 && parts[0].trim() && parts.slice(1).join(' ').trim()) {
    return { before: clean(parts[0]), after: clean(parts.slice(1).join(' → ')) };
  }
  return { before: clean(String(raw ?? '')), after: null };
}

/** Split a "1) … 2) … 3) …" recommendation into steps (else no steps). */
function numberedSteps(text?: string): string[] {
  if (!text) return [];
  const parts = text
    .split(/(?:^|\s)(?:\d{1,2}[).]|[-•])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  return parts.length >= 2 ? parts : [];
}

function gradeFor(score: number | null, max: number): { grade: string; tone: string; key: string } | null {
  if (score === null || score === undefined || !max) return null;
  const pct = score / max;
  if (pct >= 0.9) return { grade: 'A+', tone: 'good', key: 'er_grade_aplus' };
  if (pct >= 0.8) return { grade: 'A', tone: 'good', key: 'er_grade_a' };
  if (pct >= 0.7) return { grade: 'B+', tone: 'info', key: 'er_grade_bplus' };
  if (pct >= 0.6) return { grade: 'B', tone: 'info', key: 'er_grade_b' };
  if (pct >= 0.5) return { grade: 'C+', tone: 'warn', key: 'er_grade_cplus' };
  if (pct >= 0.4) return { grade: 'C', tone: 'warn', key: 'er_grade_c' };
  return { grade: 'F', tone: 'bad', key: 'er_grade_f' };
}

function tone(score: number, max: number): string {
  const r = max ? score / max : 0;
  return r >= 1 ? 'good' : r >= 0.7 ? 'warn' : 'bad';
}

function Skeleton() {
  return (
    <div className="er" aria-busy="true">
      <div className="dsh-skeleton-line" style={{ height: 28, width: '60%' }} />
      <div className="dsh-skeleton" style={{ height: 180 }} />
      <div className="dsh-skeleton-line" style={{ height: 44 }} />
      <div className="dsh-skeleton" style={{ height: 260 }} />
    </div>
  );
}

export default function EssayResult() {
  const { id = '' } = useParams();
  const { t } = useLang();
  const { user } = useAuth();
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showScoreCard, setShowScoreCard] = useState(false);
  const [tab, setTab] = useState<Tab>('essay');
  const [openCrit, setOpenCrit] = useState<Set<number>>(new Set());

  const [improved, setImproved] = useState<string | null>(null);
  const [improvedBusy, setImprovedBusy] = useState(false);
  const [improvedErr, setImprovedErr] = useState<string | null>(null);
  const [improvedView, setImprovedView] = useState<'diff' | 'after' | 'before'>('diff');
  const [copied, setCopied] = useState<string | null>(null);

  const [reason, setReason] = useState('');
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewSent, setReviewSent] = useState(false);
  const [reviewErr, setReviewErr] = useState<string | null>(null);

  const [retryBusy, setRetryBusy] = useState(false);
  const [retryErr, setRetryErr] = useState<string | null>(null);
  const [pollNonce, setPollNonce] = useState(0);

  const [workingText, setWorkingText] = useState('');
  const [_activeError, setActiveError] = useState<SpellingError | null>(null);
  const [fixed, setFixed] = useState<Record<string, string>>({});

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const r = (await Essays.result(id)) as unknown as Result;
        if (stop) return;
        setRes({ ...r, criteria: Array.isArray(r.criteria) ? r.criteria : [] });
        if (r.improved_text) setImproved(r.improved_text);
        if (!isEssayTerminal(r.status)) {
          timer = setTimeout(poll, (r.poll_after ?? 3) * 1000);
        }
      } catch (e) {
        if (!stop) setErr(e instanceof Error ? e.message : t('essay_js_error'));
      }
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [id, pollNonce, t]);

  useEffect(() => {
    if (res?.essay_text && !workingText) setWorkingText(res.essay_text);
  }, [res?.essay_text, workingText]);

  const isEnglish = Boolean(
    res &&
      (res.subject === 'english' ||
        res.rubric_type?.startsWith('ielts') ||
        (res.overall_band !== null && res.overall_band !== undefined)),
  );

  const criteria = useMemo(() => res?.criteria ?? [], [res?.criteria]);
  const spelling = useMemo(
    () => (res?.spelling_errors ?? []).filter((e) => e && typeof e.word === 'string' && e.word.trim()),
    [res?.spelling_errors],
  );

  const allHighlightErrors = useMemo<HighlightError[]>(() => {
    const list: HighlightError[] = [];
    const seen = new Set<string>();

    for (const e of spelling) {
      const w = e.word.trim();
      if (w && !seen.has(w.toLowerCase())) {
        seen.add(w.toLowerCase());
        list.push({
          word: w,
          correction: e.correction || '',
          explanation: e.explanation || "Imlo yoki shakl xatosi",
          type: 'spelling',
        });
      }
    }

    for (const c of criteria) {
      for (const errStr of c.errors ?? []) {
        const { before, after } = splitEvidence(errStr);
        const w = (before || '').trim();
        if (w && !seen.has(w.toLowerCase())) {
          seen.add(w.toLowerCase());
          list.push({
            word: w,
            correction: after || '',
            explanation: `${c.name}: ${c.reason || 'Grammatik yoki uslubiy tavsiya'}`,
            type: c.id >= 6 && c.id <= 8 ? 'spelling' : 'grammar',
          });
        }
      }
    }
    return list;
  }, [spelling, criteria]);

  const groups = useMemo(() => {
    if (!criteria.length) return [];
    if (isEnglish) return [{ key: 'er_group_ielts', items: criteria }];
    const used = new Set<number>();
    const out = BMB_GROUPS.map((g) => {
      const items = criteria.filter((c) => g.ids.includes(c.id));
      items.forEach((c) => used.add(c.id));
      return { key: g.key, items };
    }).filter((g) => g.items.length);
    const rest = criteria.filter((c) => !used.has(c.id));
    if (rest.length) out[0] = { ...out[0], items: [...out[0].items, ...rest] };
    return out;
  }, [criteria, isEnglish]);

  // Open the criterion that cost the most points by default.
  useEffect(() => {
    if (!criteria.length) return;
    const worst = [...criteria].sort(
      (a, b) => (b.max_score ?? 2) - b.score - ((a.max_score ?? 2) - a.score),
    )[0];
    setOpenCrit((prev) => (prev.size ? prev : new Set([worst.id])));
  }, [criteria]);

  const takeaways = useMemo(() => {
    if (!res) return [];
    const out: string[] = [];
    for (const s of numberedSteps(res.teacher_recommendation)) if (out.length < 3) out.push(s);
    for (const w of res.weaknesses ?? []) if (out.length < 3 && w && !out.includes(w)) out.push(w);
    const lossy = [...criteria]
      .filter((c) => c.score < (c.max_score ?? 2) && c.reason)
      .sort((a, b) => (b.max_score ?? 2) - b.score - ((a.max_score ?? 2) - a.score));
    for (const c of lossy) if (out.length < 3) out.push(`${c.name}: ${c.reason}`);
    return out;
  }, [res, criteria]);

  const loadImproved = useCallback(async () => {
    if (improved !== null || improvedBusy) return;
    setImprovedBusy(true);
    setImprovedErr(null);
    try {
      const r = await Essays.improve(id);
      if (r.ok && r.content) setImproved(r.content);
      else setImprovedErr(r.error ?? t('essay_improved_error'));
    } catch {
      setImprovedErr(t('essay_improved_error'));
    } finally {
      setImprovedBusy(false);
    }
  }, [id, improved, improvedBusy, t]);

  const copy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied((c) => (c === key ? null : c)), 2000);
    } catch {
      /* clipboard unavailable — the user can still select the text */
    }
  };

  const replaceIn = (text: string, e: SpellingError) => {
    try {
      return text.replace(new RegExp(`(?<![\\p{L}\\p{N}])${escapeRe(e.word)}(?![\\p{L}\\p{N}])`, 'giu'), e.correction);
    } catch {
      return text.split(e.word).join(e.correction);
    }
  };

  const applyFix = (e: SpellingError) => {
    setWorkingText((cur) => replaceIn(cur || res?.essay_text || '', e));
    setFixed((prev) => ({ ...prev, [e.word.toLowerCase()]: e.correction }));
    setActiveError(null);
  };

  const applyAll = () => {
    let txt = workingText || res?.essay_text || '';
    const next = { ...fixed };
    for (const e of spelling) {
      txt = replaceIn(txt, e);
      next[e.word.toLowerCase()] = e.correction;
    }
    setWorkingText(txt);
    setFixed(next);
    setActiveError(null);
  };

  const sendReview = async () => {
    setReviewBusy(true);
    setReviewErr(null);
    try {
      const r = await requestTeacherReview(id, reason.trim());
      if (r.ok) setReviewSent(true);
      else setReviewErr(t('essay_js_error'));
    } catch {
      setReviewErr(t('essay_js_error'));
    } finally {
      setReviewBusy(false);
    }
  };

  const retryGrading = async () => {
    if (!res || retryBusy) return;
    const text = (res.essay_text ?? '').trim();
    if (!text) {
      setRetryErr(t('essay_js_error'));
      return;
    }
    setRetryBusy(true);
    setRetryErr(null);
    try {
      await Essays.submit(id, text);
      setRes({ ...res, status: 'pending' });
      setPollNonce((n) => n + 1);
    } catch (e) {
      setRetryErr(e instanceof Error ? e.message : t('essay_js_error'));
    } finally {
      setRetryBusy(false);
    }
  };

  if (err) return <p className="error" role="alert">{err}</p>;
  if (!res) return <Skeleton />;

  const pending = !isEssayTerminal(res.status);
  const done = isEssayDone(res.status);
  const hasTeacherScore = res.final_score !== null && res.final_score !== undefined;
  const displayScore = res.final_score ?? res.total_score;
  const grade = !isEnglish ? gradeFor(displayScore, res.max_score) : null;
  const band = res.overall_band ?? (isEnglish ? displayScore : null);
  const fullMarks = criteria.filter((c) => c.score >= (c.max_score ?? 2)).length;
  const activeErrors = spelling.filter((e) => !fixed[e.word.toLowerCase()]);
  const offTopicFull = res.is_completely_off_topic || res.topic_status === 'completely_off_topic';
  const offTopicPartial = !offTopicFull && (res.is_off_topic || res.topic_status === 'partially_off_topic');
  const minutes = res.time_spent_seconds ? Math.max(1, Math.round(res.time_spent_seconds / 60)) : null;

  const toggleCrit = (cid: number) =>
    setOpenCrit((prev) => {
      const next = new Set(prev);
      if (next.has(cid)) next.delete(cid);
      else next.add(cid);
      return next;
    });


  const tabs: Array<{ key: Tab; label: string; count?: number }> = [
    { key: 'essay', label: `🎨 ${t('er_tab_essay')} (Rangli Tahlil)`, count: allHighlightErrors.length || undefined },
    { key: 'criteria', label: t('er_tab_criteria'), count: criteria.length || undefined },
    { key: 'corrections', label: t('er_tab_corrections'), count: spelling.length || undefined },
    { key: 'improved', label: t('er_tab_improved') },
  ];

  return (
    <div className="er">
      <header className="er-head">
        <h1 className="clamp-2">{res.topic_title || t('essay_results')}</h1>
        <div className="er-badges">
          <span className={`es-status is-${essayStatus(res.status)}`}>{t(`es_status_${essayStatus(res.status)}`)}</span>
          {done && !hasTeacherScore && res.grading_source !== 'mock' && (
            <span className="es-status">{t('er_ai_graded')}</span>
          )}
          {hasTeacherScore && <span className="es-status is-graded">{t('essay_teacher_done')}</span>}
        </div>
      </header>

      {pending && res.status !== 'draft' && (
        <div className="ui-card er-pending" role="status">
          <strong>{t('essay_grading_pending')}</strong>
          <div className="er-progress" aria-hidden="true"><i /></div>
          <div className="dsh-skeleton-line" style={{ height: 14, width: '80%' }} />
          <div className="dsh-skeleton-line" style={{ height: 14, width: '55%' }} />
          <p className="muted small">{t('er_can_leave')}</p>
        </div>
      )}

      {res.status === 'pending_teacher' && !reviewSent && (
        <div className="ui-card">
          <strong>{t('essay_grading_recheck')}</strong>
          <p className="muted">{t('essay_teacher_reviewing')}</p>
        </div>
      )}

      {reviewSent && (
        <div className="ui-card">
          <strong>{t('essay_review_requested')}</strong>
          <p className="muted small">{t('essay_review_requested_hint')}</p>
        </div>
      )}

      {res.status === 'error' && (
        <div className="ui-card er-banner is-bad" role="alert">
          <strong>{t('essay_grading_failed')}</strong>
          <p>{t('essay_error')}</p>
          {res.error && <p className="muted small">{res.error}</p>}
          {retryErr && <p className="error small">{retryErr}</p>}
          <div className="er-actions">
            <button
              className="ui-btn ui-btn--primary"
              disabled={retryBusy || !(res.essay_text ?? '').trim()}
              onClick={retryGrading}
            >
              {retryBusy ? t('loading') : t('essay_error_retry')}
            </button>
            <Link className="ui-btn" to={res.topic_id ? `/essays/write/${res.topic_id}` : '/essays'}>
              {res.topic_id ? t('essay_continue_writing') : t('essay_back_topics')}
            </Link>
          </div>
        </div>
      )}

      {res.status === 'draft' && (
        <div className="ui-card">
          <p className="muted">{t('essay_status_draft')}</p>
          <Link className="ui-btn ui-btn--primary" to="/essays">{t('essay_continue_writing')}</Link>
        </div>
      )}

      {done && (
        <>
          {(offTopicFull || offTopicPartial) && (
            <div className={`ui-card er-banner ${offTopicFull ? 'is-bad' : 'is-warn'}`} role="alert">
              <strong>{t(offTopicFull ? 'er_offtopic_full_title' : 'er_offtopic_partial_title')}</strong>
              <p>{t(offTopicFull ? 'er_offtopic_full_text' : 'er_offtopic_partial_text')}</p>
              {res.topic_match_reason && <p className="muted small">{res.topic_match_reason}</p>}
            </div>
          )}

          {/* ---- Hero: the essentials --------------------------------- */}
          <section className="ui-card er-hero" aria-labelledby="er-hero-title">
            <div className="er-hero__score">
              {isEnglish ? (
                <>
                  <span className="er-hero__big is-info">{band !== null && band !== undefined ? Number(band).toFixed(1) : '—'}</span>
                  <span className="er-hero__label" id="er-hero-title">{t('er_band')} <small>/ 9.0</small></span>
                </>
              ) : (
                <>
                  <span className={`er-hero__big is-${grade?.tone ?? 'info'}`}>{grade?.grade ?? '—'}</span>
                  <span className="er-hero__label" id="er-hero-title">
                    {hasTeacherScore ? t('essay_final_score').replace(/:\s*$/, '') : t('er_bmb_grade')}
                  </span>
                  {grade && <span className={`er-hero__hint is-${grade.tone}`}>{t(grade.key)}</span>}
                </>
              )}
            </div>

            <dl className="er-stats">
              {!isEnglish && (
                <div>
                  <dt>{t('er_score')}</dt>
                  <dd>{displayScore !== null ? num(displayScore) : '—'}<small> / {res.max_score}</small></dd>
                </div>
              )}
              {isEnglish && res.cefr_level && (
                <div>
                  <dt>{t('er_cefr')}</dt>
                  <dd>{res.cefr_level}</dd>
                </div>
              )}
              <div>
                <dt>{t('words')}</dt>
                <dd>{res.word_count || countEssayWords(res.essay_text ?? '')}</dd>
              </div>
              {minutes !== null && (
                <div>
                  <dt>{t('er_time_spent')}</dt>
                  <dd>{fmt(t('er_minutes'), { m: minutes })}</dd>
                </div>
              )}
            </dl>

            {res.cached && <p className="muted small er-hero__note">{t('essay_grading_cached')}</p>}
            {res.grading_source === 'mock' && <p className="muted small er-hero__note">{t('essay_grading_mock')}</p>}
            {res.summary && <p className="er-hero__summary">{res.summary}</p>}

            {takeaways.length > 0 && (
              <div className="er-takeaways">
                <h2>{t('er_takeaways')}</h2>
                <ol>
                  {takeaways.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ol>
              </div>
            )}
          </section>

          {/* ---- Tabs ---------------------------------------------------- */}
          <div className="er-tabs" role="tablist" aria-label={t('essay_results')}>
            {tabs.map((tb) => (
              <button
                key={tb.key}
                type="button"
                role="tab"
                id={`er-tab-${tb.key}`}
                aria-selected={tab === tb.key}
                aria-controls={`er-panel-${tb.key}`}
                className={`er-tab${tab === tb.key ? ' is-active' : ''}`}
                onClick={() => {
                  setTab(tb.key);
                  if (tb.key === 'improved') void loadImproved();
                }}
              >
                {tb.label}
                {tb.count !== undefined && <span className="er-tab__count">{tb.count}</span>}
              </button>
            ))}
          </div>

          {tab === 'criteria' && (
            <section id="er-panel-criteria" role="tabpanel" aria-labelledby="er-tab-criteria" className="er-panel">
              {criteria.length > 0 && (
                <div className="er-panel__bar">
                  {!isEnglish && <span className="muted small">{fmt(t('er_criteria_full'), { n: fullMarks })}</span>}
                  <button
                    type="button"
                    className="ui-btn ui-btn--sm"
                    onClick={() =>
                      setOpenCrit(openCrit.size === criteria.length ? new Set() : new Set(criteria.map((c) => c.id)))
                    }
                  >
                    {openCrit.size === criteria.length ? t('er_collapse_all') : t('er_expand_all')}
                  </button>
                </div>
              )}

              {groups.map((g) => (
                <div key={g.key} className="er-group">
                  <h3 className="er-group__title">{t(g.key)}</h3>
                  {g.items.map((c) => {
                    const max = c.max_score ?? 2;
                    const lost = Math.max(0, max - c.score);
                    const open = openCrit.has(c.id);
                    const tn = tone(c.score, max);
                    return (
                      <div key={c.id} className={`er-crit${open ? ' is-open' : ''}`}>
                        <button
                          type="button"
                          className="er-crit__head"
                          aria-expanded={open}
                          aria-controls={`er-crit-${c.id}`}
                          onClick={() => toggleCrit(c.id)}
                        >
                          <span className="er-crit__name">{c.name}</span>
                          <span className={`er-crit__score is-${tn}`}>
                            {num(c.score)}<small>/{num(max)}</small>
                          </span>
                          <span className="er-crit__bar" aria-hidden="true">
                            <i className={`is-${tn}`} style={{ width: `${Math.min(100, Math.round((c.score / (max || 1)) * 100))}%` }} />
                          </span>
                          <span className="er-crit__chev" aria-hidden="true">▾</span>
                        </button>
                        <div className="er-crit__body" id={`er-crit-${c.id}`} role="region">
                          <div className="er-crit__inner">
                            <p className={`er-chip is-${tn}`}>
                              {lost > 0 && !isEnglish ? fmt(t('er_lost'), { n: num(lost) }) : lost > 0 ? `${num(c.score)} / ${num(max)}` : t('er_full_marks')}
                            </p>
                            {c.reason && <p className="er-crit__reason">{c.reason}</p>}
                            {!!c.errors?.length && (
                              <div className="er-evidence">
                                <span className="muted small">{t('er_evidence')}</span>
                                {c.errors.map((e, i) => {
                                  const ev = splitEvidence(e);
                                  return ev.after ? (
                                    <div key={i} className="er-diff">
                                      <p className="er-diff__before"><span aria-hidden="true">❌</span> {ev.before}</p>
                                      <p className="er-diff__after"><span aria-hidden="true">✅</span> {ev.after}</p>
                                    </div>
                                  ) : (
                                    <blockquote key={i} className="er-quote">{ev.before}</blockquote>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}

              {(!!res.strengths?.length || !!res.weaknesses?.length || !!res.teacher_recommendation) && (
                <div className="er-notes">
                  {!!res.strengths?.length && (
                    <div className="ui-card er-note is-good">
                      <h3>{t('er_strengths')}</h3>
                      <ul>{res.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
                    </div>
                  )}
                  {!!res.weaknesses?.length && (
                    <div className="ui-card er-note is-warn">
                      <h3>{t('er_weaknesses')}</h3>
                      <ul>{res.weaknesses.map((w, i) => <li key={i}>{w}</li>)}</ul>
                    </div>
                  )}
                  {!!res.teacher_recommendation && (
                    <div className="ui-card er-note is-info er-note--wide">
                      <h3>{t('er_recommendation')}</h3>
                      <p>{res.teacher_recommendation}</p>
                    </div>
                  )}
                </div>
              )}
            </section>
          )}

          {tab === 'corrections' && (
            <section id="er-panel-corrections" role="tabpanel" aria-labelledby="er-tab-corrections" className="er-panel">
              {spelling.length === 0 ? (
                <p className="ui-card muted">{t('er_no_corrections')}</p>
              ) : (
                <>
                  <div className="er-panel__bar">
                    <span className="muted small">{fmt(t('er_fixed_count'), { n: Object.keys(fixed).length })}</span>
                    {activeErrors.length > 0 && (
                      <button type="button" className="ui-btn ui-btn--sm" onClick={applyAll}>
                        {fmt(t('er_fix_all'), { n: activeErrors.length })}
                      </button>
                    )}
                  </div>
                  <div className="er-fixes">
                    {spelling.map((e, idx) => {
                      const isFixed = Boolean(fixed[e.word.toLowerCase()]);
                      return (
                        <article key={idx} className={`ui-card er-fix${isFixed ? ' is-fixed' : ''}`}>
                          <p className="er-diff__before">
                            <span className="er-fix__tag">{t('er_original')}</span> {e.word}
                          </p>
                          <p className="er-diff__after">
                            <span className="er-fix__tag">{t('er_corrected')}</span> {e.correction}
                          </p>
                          {e.explanation && <p className="er-fix__why"><b>{t('er_explanation')}:</b> {e.explanation}</p>}
                          <button
                            type="button"
                            className="ui-btn ui-btn--sm"
                            disabled={isFixed}
                            onClick={() => applyFix(e)}
                          >
                            {isFixed ? `✓ ${t('er_fixed')}` : t('er_apply_fix')}
                          </button>
                        </article>
                      );
                    })}
                  </div>
                </>
              )}
            </section>
          )}

          {tab === 'essay' && (
            <section id="er-panel-essay" role="tabpanel" aria-labelledby="er-tab-essay" className="er-panel">
              <div className="er-panel__bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span className="muted small">
                  {t('er_essay_hint')}
                </span>
                <button
                  type="button"
                  className="ui-btn ui-btn--sm"
                  onClick={() => void copy('essay', workingText || res.essay_text || '')}
                >
                  {copied === 'essay' ? t('er_copied') : t('er_copy')}
                </button>
              </div>

              <InlineEssayHighlighter
                essayText={workingText || res.essay_text || ''}
                errors={allHighlightErrors}
                strengths={res.strengths}
                onApplyFix={(err) => {
                  applyFix({
                    word: err.word,
                    correction: err.correction,
                    explanation: err.explanation || '',
                  });
                }}
                title="Talaba Essesi — Rangli Tahlil & Xatolar Ustida Ishlash"
              />
            </section>
          )}

          {tab === 'improved' && (
            <section id="er-panel-improved" role="tabpanel" aria-labelledby="er-tab-improved" className="er-panel">
              <p className="muted small">{t('er_improved_hint')}</p>
              {improvedBusy && (
                <div className="ui-card er-pending" role="status">
                  <span className="muted small">{t('er_improved_loading')}</span>
                  <div className="dsh-skeleton-line" style={{ height: 14 }} />
                  <div className="dsh-skeleton-line" style={{ height: 14, width: '90%' }} />
                  <div className="dsh-skeleton-line" style={{ height: 14, width: '70%' }} />
                </div>
              )}
              {improvedErr && <p className="error small">{improvedErr}</p>}
              {improved && (
                <>
                  <div className="er-seg" role="group">
                    {(['diff', 'after', 'before'] as const).map((v) => (
                      <button
                        key={v}
                        type="button"
                        aria-pressed={improvedView === v}
                        className={`er-seg__btn${improvedView === v ? ' is-active' : ''}`}
                        onClick={() => setImprovedView(v)}
                      >
                        {t(v === 'diff' ? 'er_view_diff' : v === 'after' ? 'er_view_after' : 'er_view_before')}
                      </button>
                    ))}
                  </div>
                  <div className={`er-compare${improvedView === 'diff' ? ' is-split' : ''}`}>
                    {improvedView !== 'after' && (
                      <div className="ui-card er-compare__col is-before">
                        <div className="er-compare__head">
                          <strong>{t('er_before_label')}</strong>
                          <span className="muted small">{res.word_count} {t('words_suffix')}</span>
                        </div>
                        <div className="er-compare__text">{res.essay_text || t('er_no_text')}</div>
                      </div>
                    )}
                    {improvedView !== 'before' && (
                      <div className="ui-card er-compare__col is-after">
                        <div className="er-compare__head">
                          <strong>{t('er_after_label')}</strong>
                          <button type="button" className="ui-btn ui-btn--sm" onClick={() => void copy('improved', improved)}>
                            {copied === 'improved' ? t('er_copied') : t('er_copy')}
                          </button>
                        </div>
                        <div className="er-compare__text">{improved}</div>
                      </div>
                    )}
                  </div>
                </>
              )}
            </section>
          )}

          {(res.status === 'graded' || res.status === 'ai_evaluated') && !hasTeacherScore && !reviewSent && (
            <details className="ui-card er-review">
              <summary>{t('essay_ask_teacher')}</summary>
              <div className="er-review__body">
                <textarea
                  className="ui-input"
                  rows={3}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder={t('essay_review_reason_ph')}
                />
                <button className="ui-btn ui-btn--primary" disabled={reviewBusy} onClick={sendReview}>
                  {reviewBusy ? t('loading') : t('essay_review_send')}
                </button>
                {reviewErr && <p className="error small">{reviewErr}</p>}
              </div>
            </details>
          )}

          <div className="er-actions er-actions--footer">
            <button type="button" className="ui-btn" onClick={() => window.print()}>
              {t('er_print')}
            </button>
            <button type="button" className="ui-btn ui-btn--primary" onClick={() => setShowScoreCard(true)}>
              {t('er_share')}
            </button>
          </div>
        </>
      )}

      {done && (
        <ScoreCardModal
          isOpen={showScoreCard}
          onClose={() => setShowScoreCard(false)}
          title={res.topic_title || t('essay_results')}
          studentName={formatDisplayName(user?.full_name, user?.email)}
          scorePercentage={
            res.score_percentage ??
            (displayScore !== null && res.max_score ? Math.round((displayScore / res.max_score) * 100) : 0)
          }
          gradeBadge={grade ? fmt(t('er_badge'), { grade: grade.grade }) : isEnglish && band ? `IELTS ${Number(band).toFixed(1)}` : t('er_badge_default')}
          correctCount={fullMarks}
          incorrectCount={Math.max(0, criteria.length - fullMarks)}
          totalQuestions={criteria.length}
          timeSpent={minutes !== null ? fmt(t('er_minutes'), { m: minutes }) : `${res.word_count} ${t('words_suffix')}`}
        />
      )}

      <p>
        <Link to="/essays">{t('essay_back_topics')}</Link>
      </p>
    </div>
  );
}
