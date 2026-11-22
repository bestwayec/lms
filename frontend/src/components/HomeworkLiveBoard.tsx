import { useCallback, useEffect, useRef, useState } from 'react';
import { useLang } from '../i18n/LangContext';
import { api } from '../lib/api';

/** Live tablo for one homework: real persisted progress, polled while visible. */
interface LiveRow {
  student_id: number;
  student_name: string;
  is_current_member: boolean;
  status: string;
  score: number | null;
  answered: number;
  remaining_seconds: number | null;
  last_activity_at: string | null;
  is_late: boolean;
}

interface LiveBoard {
  homework_id: number;
  title: string;
  total_questions: number | null;
  revision: string;
  summary: { total_students: number; submitted: number; graded: number; awaiting_review: number; grading_failed: number; in_progress: number };
  students: LiveRow[];
}

const POLL_MS = 10_000;

function mmss(sec: number | null): string {
  if (sec === null) return '—';
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function HomeworkLiveBoard({ homeworkId, onClose }: { homeworkId: number; onClose: () => void }) {
  const { t } = useLang();
  const [board, setBoard] = useState<LiveBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api<LiveBoard>(`/api/v1/school/teacher/homeworks/${homeworkId}/live/`);
      setBoard(data);
      setError(null);
    } catch (e) {
      // Keep the last good board on screen; the next poll retries (safe reconnect).
      setError(e instanceof Error ? e.message : t('err_retry_js'));
    }
  }, [homeworkId, t]);

  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible') void load();
    };
    tick();
    timer.current = window.setInterval(tick, POLL_MS);
    document.addEventListener('visibilitychange', tick);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 12 }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('hw_live_title', 'Jonli kuzatuv')}
        onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--card-bg, var(--bg, #fff))', color: 'var(--ink, inherit)', borderRadius: 14, width: 'min(760px, 100%)', maxHeight: '90vh', overflow: 'auto', padding: 16, border: '1px solid var(--border)' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <h2 style={{ margin: 0, fontSize: '1.1rem' }}>
            {t('hw_live_title', 'Jonli kuzatuv')}: {board?.title ?? ''}
          </h2>
          <button type="button" className="btn sm" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }} aria-label={t('close', 'Yopish')}>
            ✕
          </button>
        </div>
        {error && (
          <p role="alert" className="small" style={{ color: 'var(--danger, #DC2626)', margin: '0 0 8px' }}>
            {t('hw_live_reconnecting', 'Aloqa uzildi, qayta ulanmoqda…')}
          </p>
        )}
        {!board ? (
          <p className="muted">{t('loading', 'Yuklanmoqda…')}</p>
        ) : (
          <>
            <p className="small muted" style={{ margin: '0 0 10px' }}>
              {t('hw_live_summary', 'Topshirdi')}: {board.summary.submitted}/{board.summary.total_students} · {t('hw_status_graded', 'Baholandi')}: {board.summary.graded} · {t('hw_status_in_progress', 'Jarayonda')}: {board.summary.in_progress}
              {board.summary.awaiting_review > 0 && ` · ${t('hw_status_awaiting_review', 'Tekshiruv kutilmoqda')}: ${board.summary.awaiting_review}`}
              {board.summary.grading_failed > 0 && ` · ${t('hw_status_grading_failed', 'Natija hali tayyor emas')}: ${board.summary.grading_failed}`}
            </p>
            {board.students.length === 0 ? (
              <p className="muted">{t('hw_live_empty', "Bu vazifada hali o'quvchi yo'q.")}</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                      <th style={{ padding: 6 }}>{t('student', "O'quvchi")}</th>
                      <th style={{ padding: 6 }}>{t('status', 'Holat')}</th>
                      <th style={{ padding: 6 }}>{t('hw_live_answered', 'Javoblar')}</th>
                      <th style={{ padding: 6 }}>{t('hw_live_time_left', 'Qolgan vaqt')}</th>
                      <th style={{ padding: 6 }}>{t('score', 'Ball')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {board.students.map((r) => (
                      <tr key={r.student_id} style={{ borderBottom: '1px solid var(--border)', opacity: r.is_current_member ? 1 : 0.6 }}>
                        <td style={{ padding: 6 }}>
                          {r.student_name}
                          {!r.is_current_member && <span className="muted small"> ({t('hw_live_left_group', 'guruhdan chiqqan')})</span>}
                        </td>
                        <td style={{ padding: 6 }}>{t(`hw_status_${r.status}`, r.status)}{r.is_late ? ` · ${t('hw_late', 'kechikkan')}` : ''}</td>
                        <td style={{ padding: 6 }}>
                          {board.total_questions !== null ? `${r.answered}/${board.total_questions}` : '—'}
                        </td>
                        <td style={{ padding: 6 }}>{mmss(r.remaining_seconds)}</td>
                        <td style={{ padding: 6, fontWeight: 700 }}>{r.score !== null ? `${r.score}%` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
