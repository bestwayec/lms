import { useEffect, useState } from 'react';
import { useLang } from '../../i18n/LangContext';
import { TmaApi, tmaErrorMessage } from './api';
import type { TmaProfile, TmaResultItem, TmaTestSummary } from './api';

const DIFF_CLASS: Record<string, string> = {
  easy: 'tma-diff-easy',
  medium: 'tma-diff-medium',
  hard: 'tma-diff-hard',
};
const DIFF_LABEL: Record<string, string> = { easy: 'Oson', medium: "O'rta", hard: 'Qiyin' };

type CategoryFilter = 'all' | 'topic_test' | 'attestation' | 'full_mock' | 'national_cert';

export default function Home({
  profile,
  onProfileLoaded,
  onOpenTest,
  onNavigateClassroom,
}: {
  profile: TmaProfile | null;
  onProfileLoaded: (p: TmaProfile) => void;
  onOpenTest: (testId: number) => void;
  onNavigateClassroom?: () => void;
}) {
  const { t } = useLang();
  const [tests, setTests] = useState<TmaTestSummary[] | null>(() => {
    try {
      const uid = localStorage.getItem('tma_cached_uid');
      const raw = uid ? localStorage.getItem(`tma_cached_tests_${uid}`) : null;
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [results, setResults] = useState<TmaResultItem[] | null>(() => {
    try {
      const uid = localStorage.getItem('tma_cached_uid');
      const raw = uid ? localStorage.getItem(`tma_cached_results_${uid}`) : null;
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('all');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [p, ts, rs] = await Promise.all([
          profile ? Promise.resolve(profile) : TmaApi.profile(),
          TmaApi.tests(),
          TmaApi.results(),
        ]);
        if (!alive) return;
        if (!profile) onProfileLoaded(p);
        const newTests = ts.tests ?? [];
        const newResults = rs.results ?? [];
        setTests(newTests);
        setResults(newResults);
        try {
          const uid = String(p?.user?.id || localStorage.getItem('tma_cached_uid') || '');
          if (uid) {
            localStorage.setItem('tma_cached_uid', uid);
            localStorage.setItem(`tma_cached_tests_${uid}`, JSON.stringify(newTests));
            localStorage.setItem(`tma_cached_results_${uid}`, JSON.stringify(newResults));
          }
        } catch {
          /* ignore storage quota */
        }
      } catch (e) {
        if (alive && !tests) setError(tmaErrorMessage(e, t('tma_loading_error')));
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) return <div className="tma-err">{error}</div>;
  if (!profile || !tests || !results) {
    return (
      <div className="tma-list">
        <div className="tma-skel" />
        <div className="tma-skel" />
      </div>
    );
  }

  const streak = profile.current_streak ?? profile.stats.current_streak ?? 0;
  const weeklyXp = profile.weekly_xp ?? profile.stats.weekly_xp ?? 0;
  const league = profile.weekly_league ?? profile.stats.weekly_league ?? 'Bronze';

  // Filter tests by selected category
  const filteredTests = tests.filter((item) => {
    if (categoryFilter === 'all') return true;
    return item.assessment_category === categoryFilter;
  });

  return (
    <div className="tma-slide">
      {/* Gamification Streak & League Banner */}
      <div
        className="tma-card"
        style={{
          marginBottom: 16,
          background: 'linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%)',
          borderColor: '#FDE68A',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 28 }}>🔥</span>
            <div>
              <p style={{ margin: 0, fontWeight: 800, fontSize: 15, color: '#92400E' }}>
                {streak > 0 ? `${streak} kunlik ketma-ketlik!` : 'Kunlik o‘qish odati'}
              </p>
              <p style={{ margin: '2px 0 0', fontSize: 12, color: '#B45309' }}>
                {streak > 0 ? 'To‘xtab qolmang, har kuni bilim oling!' : 'Bugun test yeching va streakni boshlang!'}
              </p>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span
              className="tma-badge"
              style={{ background: '#F59E0B', color: '#FFFFFF', fontWeight: 800, display: 'inline-block' }}
            >
              🏆 {league}
            </span>
            <p style={{ margin: '4px 0 0', fontSize: 11, color: '#78350F', fontWeight: 700 }}>
              +{weeklyXp} XP haftalik
            </p>
          </div>
        </div>
      </div>

      {/* Classroom Quick Access Banner */}
      {onNavigateClassroom && (
        <div
          role="button"
          tabIndex={0}
          onClick={onNavigateClassroom}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onNavigateClassroom();
          }}
          className="tma-card tma-press"
          style={{
            marginBottom: 20,
            background: 'linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%)',
            borderColor: '#BFDBFE',
            cursor: 'pointer',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 24 }}>🏫</span>
              <div>
                <p style={{ margin: 0, fontWeight: 700, fontSize: 14, color: '#1E40AF' }}>
                  {t('my_classrooms') || 'Mening sinfxonalarim'}
                </p>
                <p style={{ margin: '2px 0 0', fontSize: 12, color: '#3B82F6' }}>
                  {t('tma_classroom_subtitle')}
                </p>
              </div>
            </div>
            <span style={{ color: '#2563eb', fontWeight: 700, fontSize: 14 }}>→</span>
          </div>
        </div>
      )}

      {/* Top Stats */}
      <div className="tma-grid2">
        <div className="tma-stat">
          <p>{t('tma_tests')}</p>
          <b>{profile.stats.tests_taken ?? 0}</b>
        </div>
        <div className="tma-stat">
          <p>{t('tma_stats_essays')}</p>
          <b style={{ color: 'var(--tma-green)' }}>{profile.stats.essays_written ?? 0}</b>
        </div>
        <div className="tma-stat">
          <p>{t('tma_stats_passed')}</p>
          <b style={{ color: 'var(--tma-green)' }}>{profile.stats.tests_passed ?? 0}</b>
        </div>
        <div className="tma-stat">
          <p>{t('tma_stats_certs')}</p>
          <b style={{ color: 'var(--tma-gold)' }}>{profile.stats.certificates ?? 0}</b>
        </div>
      </div>

      {/* Test Catalog with 5 Category Chips */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <h3 className="tma-h3" style={{ margin: 0 }}>{t('available_tests')}</h3>
        <span style={{ fontSize: 12, color: 'var(--tma-muted)' }}>
          {filteredTests.length} {t('tma_available_count')}
        </span>
      </div>

      <div className="tma-chips-row">
        <button
          className={`tma-chip ${categoryFilter === 'all' ? 'on' : ''}`}
          onClick={() => setCategoryFilter('all')}
        >
          {t('all_categories') || 'Barchasi'}
        </button>
        <button
          className={`tma-chip ${categoryFilter === 'topic_test' ? 'on' : ''}`}
          onClick={() => setCategoryFilter('topic_test')}
        >
          📚 {t('cat_topic_test')}
        </button>
        <button
          className={`tma-chip ${categoryFilter === 'attestation' ? 'on' : ''}`}
          onClick={() => setCategoryFilter('attestation')}
        >
          🎓 {t('cat_attestation')}
        </button>
        <button
          className={`tma-chip ${categoryFilter === 'full_mock' ? 'on' : ''}`}
          onClick={() => setCategoryFilter('full_mock')}
        >
          ⏱ {t('cat_full_mock')}
        </button>
        <button
          className={`tma-chip ${categoryFilter === 'national_cert' ? 'on' : ''}`}
          onClick={() => setCategoryFilter('national_cert')}
        >
          🏅 {t('cat_national_cert')}
        </button>
      </div>

      <div className="tma-list">
        {filteredTests.length === 0 && (
          <div className="tma-empty">
            {categoryFilter === 'all' ? t('tma_no_tests') : t('cat_empty')}
          </div>
        )}
        {filteredTests.slice(0, 15).map((item) => (
          <button key={item.id} onClick={() => onOpenTest(item.id)} className="tma-card tma-press">
            <div className="tma-row">
              <div className="tma-ico" style={{ background: 'rgba(59,130,246,0.2)' }}>📝</div>
              <div className="tma-grow">
                <p className="tma-title">{item.title}</p>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                  <span className={`tma-badge ${DIFF_CLASS[item.difficulty] ?? ''}`}>
                    {DIFF_LABEL[item.difficulty] ?? item.difficulty}
                  </span>
                  {item.assessment_category && (
                    <span
                      className="tma-badge"
                      style={{ background: 'rgba(200, 146, 42, 0.18)', color: 'var(--tma-gold, #d97706)' }}
                    >
                      {item.assessment_category === 'topic_test'
                        ? t('cat_topic_test')
                        : item.assessment_category === 'full_mock'
                        ? t('cat_full_mock')
                        : item.assessment_category === 'attestation'
                        ? t('cat_attestation')
                        : item.assessment_category === 'national_cert'
                        ? t('cat_national_cert')
                        : t('cat_quiz')}
                    </span>
                  )}
                  <span className="tma-sub">
                    {item.total_questions} {t('tma_questions_count')} · {item.time_limit_minutes ? `${item.time_limit_minutes} ${t('tma_minutes_short')}` : t('tma_unlimited')}
                  </span>
                </div>
              </div>
              <span style={{ color: '#6b7280', fontSize: 14 }}>→</span>
            </div>
          </button>
        ))}
      </div>

      {/* Recent Results */}
      <h3 className="tma-h3" style={{ marginTop: 24 }}>{t('recent_results')}</h3>
      <div className="tma-list">
        {results.length === 0 && <div className="tma-empty">{t('tma_no_results')}</div>}
        {results.slice(0, 5).map((r, i) => (
          <div key={r.id ?? i} className="tma-card">
            <div className="tma-row">
              <div
                className="tma-ico"
                style={{ background: r.is_passed ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)' }}
              >
                {r.is_passed ? '✅' : '❌'}
              </div>
              <div className="tma-grow">
                <p className="tma-title">{r.test_title}</p>
                <p className="tma-sub">
                  {r.correct_answers}/{r.total_questions} to‘g‘ri
                </p>
              </div>
              <span className={`tma-score ${r.is_passed ? 'tma-ok' : 'tma-bad'}`}>{r.percentage}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
