import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BarChart3, PenLine, Plus, Share2 } from 'lucide-react';
import { useAuth } from '../auth/authState';
import { useLang } from '../i18n/LangContext';
import { TeacherEssays, canReviewEssays, type TeacherEssayCard } from '../lib/api';
import { StudioApi, type StudioDetail, type StudioListItem } from '../lib/studio';
import AssignDialog from '../components/studio/AssignDialog';
import EssayReviewDrawer from '../components/studio/EssayReviewDrawer';

/** Teacher Studio hub: my tests (edit / assign / results) and essays waiting for review. */
export default function TeacherStudio() {
  const { t } = useLang();
  const { user } = useAuth();
  const [tests, setTests] = useState<StudioListItem[] | null>(null);
  const [essays, setEssays] = useState<TeacherEssayCard[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [assignFor, setAssignFor] = useState<StudioDetail | null>(null);
  const [reviewId, setReviewId] = useState<number | null>(null);
  const reviewer = canReviewEssays(user);

  const loadEssays = useCallback(() => {
    if (!reviewer) return;
    TeacherEssays.queue()
      .then((q) => setEssays([...q.student_requested, ...q.pending]))
      .catch(() => setEssays([]));
  }, [reviewer]);

  useEffect(() => {
    StudioApi.list()
      .then(setTests)
      .catch((e) => setErr(e instanceof Error ? e.message : t('err_retry_js')));
    loadEssays();
  }, [t, loadEssays]);

  const openAssign = async (id: number) => {
    try {
      setAssignFor(await StudioApi.detail(id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : t('err_retry_js'));
    }
  };

  return (
    <div className="studio-page">
      <header className="studio-hub__head">
        <div>
          <h1 className="studio-h1">{t('studio_title')}</h1>
          <p className="muted">{t('studio_subtitle')}</p>
        </div>
        <Link to="/teacher/studio/new" className="btn primary">
          <Plus size={16} aria-hidden="true" /> {t('studio_new_test')}
        </Link>
      </header>

      {err && (
        <div className="studio-alert is-bad" role="alert">
          {err}
        </div>
      )}

      <div className="studio-hub">
        <section className="card studio-hub__tests" aria-labelledby="studio-my-tests">
          <h2 id="studio-my-tests">{t('studio_my_tests')}</h2>
          {tests === null ? (
            <div className="studio-skeleton" role="status" aria-label={t('loading')} />
          ) : tests.length === 0 ? (
            <div className="studio-empty">
              <p>{t('studio_no_tests')}</p>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
                <Link to="/teacher/ai-converter" className="btn primary sm">
                  ✨ AI Konvertor
                </Link>
                <Link to="/teacher/studio/new" className="btn secondary sm">
                  {t('studio_new_test')}
                </Link>
              </div>
            </div>
          ) : (
            <ul className="studio-list">
              {tests.map((test) => (
                <li key={test.id} className="studio-list__item">
                  <div className="studio-list__main">
                    <strong>{test.title}</strong>
                    <span className="muted small">
                      <span className={`studio-status is-${test.status}`}>{t(`studio_status_${test.status}`)}</span>{' '}
                      {t(`studio_subject_${test.subject}`, test.subject)} ·{' '}
                      {t('studio_n_questions').replace('{n}', String(test.questions))} ·{' '}
                      {t('studio_n_attempts').replace('{n}', String(test.attempts))}
                      {test.mock_code && ` · ${test.mock_code}`}
                    </span>
                  </div>
                  <div className="studio-list__actions">
                    {test.is_studio && test.attempts === 0 && (
                      <Link className="btn sm" to={`/teacher/studio/${test.id}/edit`}>
                        <PenLine size={14} aria-hidden="true" /> {t('studio_edit')}
                      </Link>
                    )}
                    {test.is_studio && test.attempts > 0 && (
                      <Link className="btn sm" to={`/teacher/studio/${test.id}/edit`}>
                        {t('studio_view')}
                      </Link>
                    )}
                    {test.status === 'published' && (
                      <button type="button" className="btn sm" onClick={() => void openAssign(test.id)}>
                        <Share2 size={14} aria-hidden="true" /> {t('studio_assign')}
                      </button>
                    )}
                    <Link className="btn sm" to={`/teacher/studio/${test.id}/results`}>
                      <BarChart3 size={14} aria-hidden="true" /> {t('studio_results')}
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {reviewer && (
          <section className="card studio-hub__essays" aria-labelledby="studio-essays-h">
            <h2 id="studio-essays-h">{t('studio_essays_waiting')}</h2>
            {essays === null ? (
              <div className="studio-skeleton" role="status" aria-label={t('loading')} />
            ) : essays.length === 0 ? (
              <p className="muted">{t('tr_no_items')}</p>
            ) : (
              <ul className="studio-list">
                {essays.slice(0, 12).map((e) => (
                  <li key={e.id} className="studio-list__item">
                    <div className="studio-list__main">
                      <strong>{e.student}</strong>
                      <span className="muted small">
                        {e.topic ?? '—'} · {t('tr_ai_score')} {e.total_score}/{e.max_score}
                        {e.teacher_review_requested && ` · ${t('tr_requested')}`}
                      </span>
                    </div>
                    <button type="button" className="btn sm primary" onClick={() => setReviewId(e.id)}>
                      {t('studio_quick_review')}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <Link to="/teacher/essays" className="small">
              {t('view_all')} →
            </Link>
          </section>
        )}
      </div>

      {assignFor && (
        <AssignDialog
          testId={assignFor.test.id}
          testTitle={assignFor.test.title}
          links={assignFor.links}
          assignments={assignFor.assignments}
          onClose={() => setAssignFor(null)}
        />
      )}
      {reviewId !== null && (
        <EssayReviewDrawer submissionId={reviewId} onClose={() => setReviewId(null)} onSaved={() => loadEssays()} />
      )}
    </div>
  );
}
