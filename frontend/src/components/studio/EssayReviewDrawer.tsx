import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCheck, Save, X } from 'lucide-react';
import { useLang } from '../../i18n/LangContext';
import { TeacherEssays, type TeacherEssayDetail } from '../../lib/api';
import InlineEssayHighlighter from '../InlineEssayHighlighter';

const CRITERIA = Array.from({ length: 12 }, (_, i) => i + 1);

const steps = (max: number) => {
  const out: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += 0.5) out.push(Number(v.toFixed(1)));
  return out;
};

interface Props {
  submissionId: number;
  onClose: () => void;
  onSaved?: (finalScore: number) => void;
}

/**
 * Side drawer for a fast 12-criterion BMB essay review: approve the AI scores
 * as they are or override any criterion, and leave feedback. Uses the existing
 * teacher review API (scores are validated server-side).
 */
export default function EssayReviewDrawer({ submissionId, onClose, onSaved }: Props) {
  const { t } = useLang();
  const [data, setData] = useState<TeacherEssayDetail | null>(null);
  const [scores, setScores] = useState<Record<number, number>>({});
  const [comments, setComments] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState<number | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setErr(null);
    setSaved(null);
    TeacherEssays.detail(submissionId)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        const preset: Record<number, number> = {};
        const source = d.existing_review?.criteria_scores;
        for (const cid of CRITERIA) {
          const fromReview = source?.[String(cid)];
          const ai = d.ai_criteria.find((c) => c.criterion_id === cid)?.score;
          preset[cid] = Number(fromReview ?? ai ?? 0);
        }
        setScores(preset);
        setComments(d.existing_review?.teacher_comments ?? '');
      })
      .catch((e) => !cancelled && setErr(e instanceof Error ? e.message : t('err_retry_js')));
    return () => {
      cancelled = true;
    };
  }, [submissionId, t]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    panelRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const maxOf = (cid: number) => data?.criterion_max?.[String(cid)] ?? 2;
  const aiOf = (cid: number) => data?.ai_criteria.find((c) => c.criterion_id === cid);
  const total = useMemo(() => CRITERIA.reduce((a, cid) => a + (scores[cid] ?? 0), 0), [scores]);
  const maxTotal = CRITERIA.reduce((a, cid) => a + maxOf(cid), 0);
  const overridden = CRITERIA.filter((cid) => {
    const ai = aiOf(cid);
    return ai && Number(ai.score) !== scores[cid];
  }).length;

  const submit = async (approveAi: boolean) => {
    if (!data) return;
    const payload: Record<number, number> = {};
    for (const cid of CRITERIA) {
      const ai = aiOf(cid);
      payload[cid] = approveAi && ai ? Number(ai.score) : scores[cid] ?? 0;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await TeacherEssays.submitReview(submissionId, { criteria_scores: payload, teacher_comments: comments });
      if (approveAi) setScores(payload);
      setSaved(r.final_score);
      onSaved?.(r.final_score);
    } catch (e) {
      setErr(e instanceof Error ? e.message : t('err_retry_js'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="studio-drawer" role="presentation" onClick={onClose}>
      <div
        ref={panelRef}
        className="studio-drawer__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="essay-drawer-title"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="studio-drawer__head">
          <div>
            <h2 id="essay-drawer-title">{data ? data.submission.student : t('loading')}</h2>
            {data && (
              <p className="muted small">
                {data.submission.topic ?? '—'} · {data.submission.word_count} {t('essay_words')}
              </p>
            )}
          </div>
          <button type="button" className="studio-icon" onClick={onClose} aria-label={t('close')}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        {!data && !err && <div className="studio-skeleton" role="status" aria-label={t('loading')} />}
        {err && (
          <p className="studio-err-text" role="alert">
            {err}
          </p>
        )}

        {data && (
          <div className="studio-drawer__body">
            {data.submission.teacher_review_requested && data.submission.teacher_review_reason && (
              <p className="studio-alert is-warn">
                {t('studio_essay_student_asks')}: {data.submission.teacher_review_reason}
              </p>
            )}
            <details className="studio-essay" open>
              <summary>{t('tr_essay_text')}</summary>
              <div style={{ marginTop: 10 }}>
                <InlineEssayHighlighter
                  essayText={data.submission.essay_text}
                  readOnly={true}
                  title="O'quvchi Essesi (Rangli Tahlil)"
                />
              </div>
            </details>
            {data.submission.summary && <p className="muted small">{data.submission.summary}</p>}

            <div className="studio-crit__total">
              <strong>
                {t('tr_your_score')}: {total.toFixed(1)}/{maxTotal}
              </strong>
              <span className="muted small">
                {t('tr_ai_score')}: {data.submission.total_score}/{data.submission.max_score}
                {overridden > 0 && ` · ${t('studio_essay_overridden').replace('{n}', String(overridden))}`}
              </span>
            </div>

            <ol className="studio-crit">
              {CRITERIA.map((cid) => {
                const ai = aiOf(cid);
                const max = maxOf(cid);
                const changed = ai && Number(ai.score) !== scores[cid];
                return (
                  <li key={cid} className={changed ? 'is-changed' : ''}>
                    <div className="studio-crit__name">
                      <b>{cid}.</b> {data.criterion_names[String(cid)] ?? ai?.name ?? '—'}
                      <span className="muted small">
                        {' '}
                        · {t('tr_ai_score')} {ai ? ai.score : '—'}/{max}
                      </span>
                    </div>
                    {ai?.reason && <p className="studio-crit__reason">{ai.reason}</p>}
                    <div className="studio-seg" role="radiogroup" aria-label={`${t('tr_your_score')} ${cid}`}>
                      {steps(max).map((v) => (
                        <button
                          key={v}
                          type="button"
                          role="radio"
                          aria-checked={scores[cid] === v}
                          className={scores[cid] === v ? 'is-on' : ''}
                          onClick={() => setScores((s) => ({ ...s, [cid]: v }))}
                        >
                          {v}
                        </button>
                      ))}
                    </div>
                  </li>
                );
              })}
            </ol>

            <label className="studio-field">
              <span>{t('tr_comments')}</span>
              <textarea rows={4} value={comments} onChange={(e) => setComments(e.target.value)} />
            </label>

            {saved !== null && (
              <p className="studio-alert is-ok" role="status">
                {t('tr_review_saved')}: {saved}/{maxTotal}
              </p>
            )}
          </div>
        )}

        {data && (
          <footer className="studio-drawer__foot">
            <button
              type="button"
              className="btn"
              disabled={busy || data.ai_criteria.length === 0}
              onClick={() => void submit(true)}
            >
              <CheckCheck size={16} aria-hidden="true" /> {t('studio_essay_approve_ai')}
            </button>
            <button type="button" className="btn primary" disabled={busy} onClick={() => void submit(false)}>
              <Save size={16} aria-hidden="true" /> {busy ? t('studio_saving') : t('tr_save_review')}
            </button>
          </footer>
        )}
      </div>
    </div>
  );
}
