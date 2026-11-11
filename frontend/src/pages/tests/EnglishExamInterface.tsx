import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Tests as TestsApi } from '../../lib/api';
import { useLang } from '../../i18n/LangContext';
import CdExamInterface, { type CdAttempt } from './CdExamInterface';
import { withSyntheticStructure } from './cdAdapter';

/**
 * Entry point of /english-exam/:attemptId. Every English exam (CEFR, IELTS)
 * runs on the CD engine: this component only loads the attempt and shows
 * loading / error / empty states around it.
 */
export default function EnglishExamInterface() {
  const { attemptId = '' } = useParams<{ attemptId: string }>();
  const { t, lang } = useLang();
  const [retry, setRetry] = useState(0);
  const [loaded, setLoaded] = useState<{ key: string; attempt: CdAttempt | null; error: string | null } | null>(null);
  const key = `${attemptId}:${lang}:${retry}`;
  const current = loaded?.key === key ? loaded : null;
  const attempt = current?.attempt ?? null;
  const loading = !current;
  const err = current?.error ?? null;

  useEffect(() => {
    let active = true;
    TestsApi.attempt(attemptId)
      .then((data) => { if (active) setLoaded({ key, attempt: data as unknown as CdAttempt, error: null }); })
      .catch((e: unknown) => { if (active) setLoaded({ key, attempt: null, error: e instanceof Error ? e.message : t('error_retry') }); });
    return () => { active = false; };
  }, [attemptId, key, t]);

  if (loading) {
    return (
      <div className="exam-state" role="status">
        <div className="exam-state__spinner" aria-hidden="true" />
        <p>{t('exam_loading')}</p>
      </div>
    );
  }

  if (err || !attempt) {
    return (
      <div className="error-boundary" role="alert">
        <div className="card error-boundary-card">
          <div className="error-boundary-icon" aria-hidden="true">⚠️</div>
          <h2>{t('error_boundary_exam_title')}</h2>
          <p className="muted">{err}</p>
          <div className="error-boundary-actions">
            <button type="button" className="btn primary" onClick={() => setRetry((value) => value + 1)}>
              {t('error_retry')}
            </button>
            <Link to="/tests" className="btn">{t('error_boundary_back')}</Link>
          </div>
        </div>
      </div>
    );
  }

  if (!attempt.questions?.length) {
    return (
      <div className="error-boundary" role="alert">
        <div className="card error-boundary-card">
          <h2>{t('exam_no_questions')}</h2>
          <div className="error-boundary-actions">
            <Link to="/tests" className="btn primary">{t('error_boundary_back')}</Link>
          </div>
        </div>
      </div>
    );
  }

  return <CdExamInterface attempt={withSyntheticStructure(attempt)} />;
}
