import { useCallback, useEffect, useRef, useState } from 'react';
import { useLang } from '../../i18n/LangContext';
import { TmaApi, tmaErrorMessage } from './api';
import type { TmaAnswerValue, TmaQuestion, TmaSubmitResult, TmaTestStart } from './api';
import { formatClock, hapticImpact, hapticNotify } from './telegram';

type Phase = 'info' | 'play' | 'result';

export default function TestFlow({
  testId,
  onExit,
  setBackHandler,
}: {
  testId: number;
  onExit: () => void;
  setBackHandler: (fn: (() => void) | null) => void;
}) {
  const { t } = useLang();
  const [phase, setPhase] = useState<Phase>('info');
  const [start, setStart] = useState<TmaTestStart | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<number, TmaAnswerValue>>({});
  const [index, setIndex] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [flagged, setFlagged] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [submitErr, setSubmitErr] = useState<string | null>(null);
  const [exitConfirm, setExitConfirm] = useState(false);
  const [submitConfirm, setSubmitConfirm] = useState(false);
  const [result, setResult] = useState<TmaSubmitResult | null>(null);
  const [resultTitle, setResultTitle] = useState('');
  const [attemptNonce, setAttemptNonce] = useState(0);
  const timerRef = useRef<number | null>(null);
  const autoSubmittedRef = useRef(false);

  const stopTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => stopTimer, []);

  // Load (creates or resumes the attempt) — mirrors old showTestInfo().
  useEffect(() => {
    let alive = true;
    autoSubmittedRef.current = false;
    (async () => {
      try {
        const data = await TmaApi.startTest(testId);
        if (!alive) return;
        const restored: Record<number, TmaAnswerValue> = {};
        for (const q of data.questions ?? []) {
          if (q.question_type === 'text' && q.text_answer) {
            restored[q.id] = { choice_ids: [], text_answer: q.text_answer };
          } else if (q.selected_choice_ids?.length) {
            restored[q.id] = [...q.selected_choice_ids];
          }
        }
        try {
          const cached = sessionStorage.getItem(`tma_attempt_${data.attempt_id}`);
          if (cached) {
            const parsed = JSON.parse(cached) as Record<number, TmaAnswerValue>;
            Object.assign(restored, parsed);
          }
        } catch {
          /* ignore storage quota */
        }
        setAnswers(restored);
        setStart(data);
        const isTestTimed = !!(
          data.is_timed ?? ((data.time_limit_minutes ?? 0) > 0 && data.remaining_seconds !== null)
        );
        if (isTestTimed) {
          setRemaining(data.remaining_seconds ?? data.time_limit_minutes * 60);
        } else {
          setRemaining(0);
        }
      } catch (e) {
        if (alive) setLoadError(tmaErrorMessage(e, t('tma_loading_error')));
      }
    })();
    return () => {
      alive = false;
    };
  }, [testId, attemptNonce, t]);

  const doSubmit = useCallback(
    async (attemptId: number, finalAnswers: Record<number, TmaAnswerValue>) => {
      if (!start) return;
      setSubmitting(true);
      setSubmitErr(null);
      setSubmitConfirm(false);
      try {
        const data = await TmaApi.submitTest(testId, attemptId, finalAnswers);
        try {
          sessionStorage.removeItem(`tma_attempt_${attemptId}`);
        } catch {
          /* ignore */
        }
        hapticNotify(data.is_passed ? 'success' : 'error');
        setResult(data);
        setResultTitle(start.test_title);
        setPhase('result');
      } catch (e) {
        // Timeout auto-finalize: fetch the produced result instead.
        const status = (e as { status?: number }).status;
        if (status === 408) {
          try {
            const r = await TmaApi.attemptResult(attemptId);
            try {
              sessionStorage.removeItem(`tma_attempt_${attemptId}`);
            } catch {
              /* ignore */
            }
            setResult(r);
            setResultTitle(start.test_title);
            setPhase('result');
            return;
          } catch {
            /* fall through to error */
          }
        }
        // Keep answers & player phase active on network/server failure so student can retry safely
        setSubmitErr(tmaErrorMessage(e, t('tma_loading_error')));
      } finally {
        setSubmitting(false);
      }
    },
    [start, testId, t],
  );

  const isTimed = !!(
    start &&
    (start.is_timed ?? ((start.time_limit_minutes ?? 0) > 0 && start.remaining_seconds !== null))
  );

  // Countdown during play (auto-submit at zero only for timed tests).
  const answersRef = useRef(answers);
  useEffect(() => {
    answersRef.current = answers;
  }, [answers]);

  useEffect(() => {
    if (phase !== 'play' || !start || !isTimed) return;
    stopTimer();
    timerRef.current = window.setInterval(() => {
      setRemaining((prev) => (prev <= 1 ? 0 : prev - 1));
    }, 1000);
    return stopTimer;
  }, [phase, start, isTimed]);

  // Trigger timed auto-submit outside the state updater so StrictMode never double-submits.
  useEffect(() => {
    if (phase !== 'play' || !start || !isTimed || remaining > 0) return;
    if (autoSubmittedRef.current) return;
    autoSubmittedRef.current = true;
    stopTimer();
    hapticNotify('warning');
    void doSubmit(start.attempt_id, answersRef.current);
  }, [phase, start, isTimed, remaining, doSubmit]);

  // BackButton: inline confirmation mid-test, plain back otherwise.
  useEffect(() => {
    if (phase === 'play') {
      setBackHandler(() => setExitConfirm(true));
    } else {
      setBackHandler(() => onExit());
    }
    return () => setBackHandler(null);
  }, [phase, onExit, setBackHandler]);

  // Persist local attempt draft on every answer change so reload/network hiccup never loses work
  useEffect(() => {
    if (!start || phase !== 'play') return;
    try {
      sessionStorage.setItem(`tma_attempt_${start.attempt_id}`, JSON.stringify(answers));
    } catch {
      /* ignore storage quota */
    }
  }, [answers, start, phase]);

  if (loadError) {
    return (
      <div>
        <div className="tma-err">{loadError}</div>
        <div className="tma-btn-row">
          <button className="tma-btn tma-btn-card" onClick={onExit}>
            {t('tma_back_home')}
          </button>
        </div>
      </div>
    );
  }

  if (!start) {
    return (
      <div className="tma-list">
        <div className="tma-skel" />
      </div>
    );
  }

  if (phase === 'result' && result) {
    const passed = !!result.is_passed;
    const pct = Math.round(result.percentage ?? 0);
    return (
      <div className="tma-slide tma-center">
        <div className={`tma-result-ico ${passed ? 'tma-ok' : 'tma-bad'}`} style={{ background: passed ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)' }}>
          {passed ? '🎉' : '😔'}
        </div>
        <h2 style={{ fontSize: 22, fontWeight: 800, margin: '0 0 8px', color: passed ? '#16a34a' : '#dc2626' }}>
          {passed ? `${t('em_greeting_congrats')}!` : `${t('em_greeting_sorry')}...`}
        </h2>
        <p className="tma-muted" style={{ marginBottom: 24 }}>
          {resultTitle} · {passed ? t('tma_passed_msg') : t('tma_failed_msg')}
        </p>
        <div className="tma-card" style={{ marginBottom: 24 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
            <div className="tma-center">
              <p style={{ fontSize: 30, fontWeight: 800, margin: 0, color: passed ? '#16a34a' : '#dc2626' }}>{pct}%</p>
              <p className="tma-sub">{t('tma_percent')}</p>
            </div>
            <div className="tma-center">
              <p style={{ fontSize: 30, fontWeight: 800, margin: 0 }}>
                {result.correct_answers ?? 0}/{result.total_questions ?? 0}
              </p>
              <p className="tma-sub">{t('tma_correct')}</p>
            </div>
          </div>
          <div className="tma-bar" style={{ marginBottom: 0 }}>
            <div style={{ width: `${pct}%`, background: passed ? '#22c55e' : '#ef4444' }} />
          </div>
        </div>
        <div className="tma-btn-row">
          <button className="tma-btn tma-btn-card" onClick={onExit}>
            {t('tma_back_home')}
          </button>
          <button
            className="tma-btn tma-btn-hl"
            onClick={() => {
              setLoadError(null);
              setResult(null);
              setStart(null);
              setAnswers({});
              setFlagged(new Set());
              setSubmitErr(null);
              setIndex(0);
              setPhase('info');
              setAttemptNonce((n) => n + 1);
            }}
          >
            {t('tma_retry')}
          </button>
        </div>
      </div>
    );
  }

  if (phase === 'info') {
    const secs = isTimed ? (start.remaining_seconds ?? start.time_limit_minutes * 60) : 0;
    return (
      <div className="tma-slide">
        <div className="tma-card tma-center" style={{ padding: 24 }}>
          <div className="tma-ico" style={{ background: 'rgba(59,130,246,0.2)', width: 64, height: 64, fontSize: 30, margin: '0 auto 16px' }}>
            📝
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 800, margin: '0 0 8px' }}>{start.test_title}</h2>
          {!!start.test_description && <p className="tma-muted">{start.test_description}</p>}
          <div className="tma-grid2" style={{ margin: '24px 0' }}>
            <div className="tma-stat" style={{ background: 'var(--tma-elevated)' }}>
              <b>{start.total_questions}</b>
              <p>{t('tma_info_questions')}</p>
            </div>
            <div className="tma-stat" style={{ background: 'var(--tma-elevated)' }}>
              <b>{isTimed ? start.time_limit_minutes : '∞'}</b>
              <p>{isTimed ? t('tma_info_minutes') : (t('tma_untimed') || "Vaqt chegarasiz")}</p>
            </div>
          </div>
          <div className="tma-card" style={{ background: 'var(--tma-bg)', marginBottom: 24 }}>
            <p className="tma-sub">⏱ {isTimed ? t('tma_remaining') : (t('tma_time_policy') || "Vaqt tartibi")}:</p>
            <p style={{ fontSize: 24, fontFamily: 'ui-monospace,monospace', fontWeight: 800, margin: '4px 0 0', color: isTimed && secs < 300 ? '#dc2626' : 'var(--tma-ink)' }}>
              {isTimed ? formatClock(secs) : (t('tma_untimed') || "Vaqt chegarasiz")}
            </p>
          </div>
          <button className="tma-btn tma-btn-hl" onClick={() => { setIndex(0); setPhase('play'); }}>
            🚀 {t('tma_begin')}
          </button>
        </div>
      </div>
    );
  }

  // Player.
  const questions = start.questions ?? [];
  const q: TmaQuestion | undefined = questions[index];
  if (!q) return <div className="tma-empty">{t('tma_loading_error')}</div>;
  const total = questions.length;
  const raw = answers[q.id];
  const selected: number[] = Array.isArray(raw) ? raw : [];
  const textVal = !Array.isArray(raw) && raw ? raw.text_answer : q.text_answer || '';

  const toggleChoice = (choiceId: number) => {
    hapticImpact('light');
    setAnswers((prev) => {
      const cur = Array.isArray(prev[q.id]) ? [...(prev[q.id] as number[])] : [];
      if (q.question_type === 'multiple') {
        const i = cur.indexOf(choiceId);
        if (i > -1) cur.splice(i, 1);
        else cur.push(choiceId);
        return { ...prev, [q.id]: cur };
      }
      return { ...prev, [q.id]: [choiceId] };
    });
  };

  const setText = (value: string) => {
    setAnswers((prev) => ({ ...prev, [q.id]: { choice_ids: [], text_answer: value } }));
  };

  const toggleFlag = (qid: number) => {
    hapticImpact('light');
    setFlagged((prev) => {
      const next = new Set(prev);
      if (next.has(qid)) next.delete(qid);
      else next.add(qid);
      return next;
    });
  };

  const unanswered = questions.filter((item) => {
    const v = answers[item.id];
    return !v || (Array.isArray(v) ? v.length === 0 : !v.text_answer.trim());
  }).length;

  const submit = () => {
    if (unanswered > 0 && !submitConfirm) {
      setSubmitConfirm(true);
      return;
    }
    hapticImpact('heavy');
    stopTimer();
    void doSubmit(start.attempt_id, answers);
  };

  const isLast = index === total - 1;
  const timerClass = isTimed && remaining <= 60 ? 'danger' : isTimed && remaining <= 300 ? 'warn' : '';

  return (
    <div>
      {exitConfirm && (
        <div className="tma-err" style={{ marginBottom: 14, textAlign: 'left' }}>
          <p style={{ margin: '0 0 10px' }}>{t('tma_exit_test')}</p>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="tma-btn tma-btn-card" onClick={() => setExitConfirm(false)}>
              Davom etish
            </button>
            <button
              type="button"
              className="tma-btn tma-btn-hl"
              onClick={() => {
                stopTimer();
                onExit();
              }}
            >
              Chiqish
            </button>
          </div>
        </div>
      )}

      {submitConfirm && (
        <div className="tma-err" style={{ marginBottom: 14, textAlign: 'left', background: 'var(--tma-accent-light)', borderColor: 'var(--tma-streak-border)', color: 'var(--tma-streak-title)' }}>
          <p style={{ margin: '0 0 10px' }}>{unanswered} {t('tma_unanswered_suffix')}</p>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="tma-btn tma-btn-card" onClick={() => setSubmitConfirm(false)}>
              Bekor qilish
            </button>
            <button
              type="button"
              className="tma-btn tma-btn-green"
              onClick={() => {
                hapticImpact('heavy');
                stopTimer();
                void doSubmit(start.attempt_id, answers);
              }}
            >
              Baribir yakunlash
            </button>
          </div>
        </div>
      )}

      {submitErr && (
        <div className="tma-err" style={{ marginBottom: 14, textAlign: 'left' }}>
          <p style={{ margin: '0 0 10px' }}>⚠️ {submitErr}</p>
          <button
            type="button"
            className="tma-btn tma-btn-green"
            disabled={submitting}
            onClick={() => void doSubmit(start.attempt_id, answers)}
          >
            🔄 Qayta yuborish
          </button>
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div className={`tma-timer ${isTimed ? timerClass : ''}`}>
          ⏱ {isTimed ? formatClock(remaining) : (t('tma_untimed') || "Chegarasiz")}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            type="button"
            className={`tma-flag-btn ${flagged.has(q.id) ? 'flagged' : ''}`}
            onClick={() => toggleFlag(q.id)}
            title={flagged.has(q.id) ? "Belgilangan savol" : "Savolni belgilash"}
          >
            {flagged.has(q.id) ? '🚩 Belgilangan' : '🏳️ Belgilash'}
          </button>
          <div className="tma-timer">
            {index + 1}/{total}
          </div>
        </div>
      </div>
      <div className="tma-bar">
        <div style={{ width: `${((index + 1) / total) * 100}%` }} />
      </div>
      {submitting ? (
        <div className="tma-center" style={{ padding: '48px 0' }}>
          <div className="tma-spin" />
          <p className="tma-muted">{t('tma_grading')}</p>
        </div>
      ) : (
        <div style={{ marginBottom: 24 }}>
          <p className="tma-q">
            {index + 1}. {q.text}
          </p>
          {q.question_type === 'text' ? (
            <textarea
              className="tma-textarea"
              rows={3}
              placeholder="Javobingizni yozing"
              value={textVal}
              onChange={(e) => setText(e.target.value)}
            />
          ) : (
            <div className="tma-list" style={{ marginBottom: 0 }}>
              {q.choices.map((c) => (
                <button
                  key={c.id}
                  onClick={() => toggleChoice(c.id)}
                  className={`tma-choice${selected.includes(c.id) ? ' sel' : ''}`}
                >
                  {c.text}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="tma-btn-row" style={{ marginTop: 0 }}>
        {index > 0 && (
          <button className="tma-btn tma-btn-card" onClick={() => setIndex(index - 1)}>
            {t('tma_prev')}
          </button>
        )}
        {!isLast && (
          <button className="tma-btn tma-btn-card" style={{ background: 'var(--tma-accent)', color: '#fff', border: 'none' }} onClick={() => setIndex(index + 1)}>
            {t('tma_next')}
          </button>
        )}
        {isLast && (
          <button className="tma-btn tma-btn-green" disabled={submitting} onClick={submit}>
            {t('tma_submit')}
          </button>
        )}
      </div>
      <div className="tma-dots">
        {questions.map((item, i) => {
          const v = answers[item.id];
          const done = Array.isArray(v) ? v.length > 0 : !!(v && v.text_answer.trim());
          const isFl = flagged.has(item.id);
          return (
            <button
              key={item.id}
              aria-label={`q${i + 1}`}
              className={`${i === index ? 'on' : done ? 'done' : ''} ${isFl ? 'flagged' : ''}`}
              onClick={() => setIndex(i)}
            />
          );
        })}
      </div>
    </div>
  );
}
