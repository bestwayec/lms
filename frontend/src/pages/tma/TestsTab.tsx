import { useEffect, useState } from 'react';
import { useLang } from '../../i18n/LangContext';
import { TmaApi, tmaErrorMessage } from './api';
import type { TmaTestSummary } from './api';
import Essays from './Essays';

const DIFF_CLASS: Record<string, string> = {
  easy: 'tma-diff-easy',
  medium: 'tma-diff-medium',
  hard: 'tma-diff-hard',
};
const DIFF_LABEL: Record<string, string> = { easy: 'Oson', medium: "O'rta", hard: 'Qiyin' };

type Mode = 'all' | 'topic_test' | 'attestation' | 'full_mock' | 'national_cert' | 'essays';

export default function TestsTab({
  onOpenTest,
  setBackHandler,
}: {
  onOpenTest: (testId: number) => void;
  setBackHandler: (fn: (() => void) | null) => void;
}) {
  const { t } = useLang();
  const [mode, setMode] = useState<Mode>('all');
  const [tests, setTests] = useState<TmaTestSummary[] | null>(() => {
    try {
      const uid = localStorage.getItem('tma_cached_uid');
      const raw = uid ? localStorage.getItem(`tma_cached_tests_${uid}`) : null;
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(!tests);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const ts = await TmaApi.tests();
        if (!alive) return;
        const list = ts.tests ?? [];
        setTests(list);
        try {
          const uid = localStorage.getItem('tma_cached_uid');
          if (uid) localStorage.setItem(`tma_cached_tests_${uid}`, JSON.stringify(list));
        } catch {
          /* ignore */
        }
      } catch (e) {
        if (alive && !tests) setError(tmaErrorMessage(e, t('tma_loading_error')));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = (tests ?? []).filter((item) => {
    const matchCat = mode === 'all' || item.assessment_category === mode;
    const matchSearch = !search.trim() || item.title.toLowerCase().includes(search.toLowerCase());
    return matchCat && matchSearch;
  });

  return (
    <div className="tma-slide">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>📝 {t('tma_tests')}</h2>
        {mode !== 'essays' && (
          <span className="tma-badge" style={{ background: 'rgba(217,119,6,0.15)', color: '#d97706' }}>
            {filtered.length} {t('tma_tests_count')}
          </span>
        )}
      </div>

      {/* Category Chips Bar */}
      <div className="tma-chips-row">
        <button
          className={`tma-chip ${mode === 'all' ? 'on' : ''}`}
          onClick={() => setMode('all')}
        >
          {t('all_categories') || 'Barchasi'}
        </button>
        <button
          className={`tma-chip ${mode === 'topic_test' ? 'on' : ''}`}
          onClick={() => setMode('topic_test')}
        >
          📚 {t('cat_topic_test')}
        </button>
        <button
          className={`tma-chip ${mode === 'attestation' ? 'on' : ''}`}
          onClick={() => setMode('attestation')}
        >
          🎓 {t('cat_attestation')}
        </button>
        <button
          className={`tma-chip ${mode === 'full_mock' ? 'on' : ''}`}
          onClick={() => setMode('full_mock')}
        >
          ⏱ {t('cat_full_mock')}
        </button>
        <button
          className={`tma-chip ${mode === 'national_cert' ? 'on' : ''}`}
          onClick={() => setMode('national_cert')}
        >
          🏅 {t('cat_national_cert')}
        </button>
        <button
          className={`tma-chip ${mode === 'essays' ? 'on' : ''}`}
          onClick={() => setMode('essays')}
        >
          ✍️ {t('cat_essays')}
        </button>
      </div>

      {mode === 'essays' ? (
        <Essays setBackHandler={setBackHandler} />
      ) : (
        <>
          {/* Search Input */}
          <div style={{ marginBottom: 12 }}>
            <input
              className="tma-input"
              placeholder={t('tma_search_tests')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {error && <div className="tma-err">{error}</div>}

          {loading && (
            <div className="tma-list">
              <div className="tma-skel" />
              <div className="tma-skel" />
            </div>
          )}

          {!loading && (
            <div className="tma-list">
              {filtered.length === 0 && (
                <div className="tma-empty">
                  {search ? t('tma_search_empty') : t('tma_no_tests')}
                </div>
              )}
              {filtered.map((item) => (
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
          )}
        </>
      )}
    </div>
  );
}
