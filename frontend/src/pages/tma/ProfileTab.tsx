import { useEffect, useState } from 'react';
import { useLang } from '../../i18n/LangContext';
import type { StudentInsightsResponse } from '../../lib/api';
import { TmaApi } from './api';
import type { TmaProfile } from './api';

export default function ProfileTab({ profile }: { profile: TmaProfile | null }) {
  const { lang, setLang, t } = useLang();
  const [lbOptIn, setLbOptIn] = useState(Boolean(profile?.stats?.leaderboard_opt_in));
  const [pseudonym, setPseudonym] = useState(profile?.stats?.leaderboard_pseudonym || '');
  const [streakOptIn, setStreakOptIn] = useState(profile?.stats?.streak_opt_in !== false);
  const [savingPref, setSavingPref] = useState(false);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);
  const [insights, setInsights] = useState<StudentInsightsResponse | null>(null);

  useEffect(() => {
    TmaApi.gamificationSettings()
      .then((s) => {
        setLbOptIn(s.leaderboard_opt_in);
        setPseudonym(s.leaderboard_pseudonym || '');
        setStreakOptIn(s.streak_opt_in);
      })
      .catch(() => undefined);
    TmaApi.insights()
      .then((res) => setInsights(res))
      .catch(() => undefined);
  }, []);

  const savePrivacySettings = async (
    nextLbOptIn = lbOptIn,
    nextPseudo = pseudonym,
    nextStreakOptIn = streakOptIn,
  ) => {
    setSavingPref(true);
    setSavedNotice(null);
    try {
      const updated = await TmaApi.updateGamificationSettings({
        leaderboard_opt_in: nextLbOptIn,
        leaderboard_pseudonym: nextPseudo,
        streak_opt_in: nextStreakOptIn,
      });
      setLbOptIn(updated.leaderboard_opt_in);
      setPseudonym(updated.leaderboard_pseudonym || '');
      setStreakOptIn(updated.streak_opt_in);
      setSavedNotice(`✓ ${t('tma_saved_ok')}`);
    } catch {
      setSavedNotice(`✕ ${t('tma_save_err')}`);
    } finally {
      setSavingPref(false);
    }
  };

  const user = profile?.user;
  const stats = profile?.stats;

  const streak = stats?.current_streak ?? 0;
  const league = stats?.weekly_league || 'bronze';
  const leagueTitle =
    league === 'diamond'
      ? `💎 ${t('tma_league_diamond')}`
      : league === 'gold'
      ? `🥇 ${t('tma_league_gold')}`
      : league === 'silver'
      ? `🥈 ${t('tma_league_silver')}`
      : `🥉 ${t('tma_league_bronze')}`;

  return (
    <div className="tma-slide">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>👤 {t('profile') || 'Mening profilim'}</h2>
      </div>

      {/* User info card */}
      <div className="tma-card" style={{ marginBottom: 16, padding: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #d97706, #b45309)',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 22,
              fontWeight: 800,
            }}
          >
            {(user?.full_name || user?.email || 'U')[0].toUpperCase()}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 style={{ fontSize: 17, fontWeight: 800, margin: '0 0 2px', color: 'var(--tma-ink)' }}>
              {user?.full_name || 'Foydalanuvchi'}
            </h3>
            <p className="tma-muted" style={{ margin: 0, fontSize: 12 }}>
              {user?.email || ''}
            </p>
            <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
              <span className="tma-badge" style={{ background: 'var(--tma-elevated)', color: 'var(--tma-muted)' }}>
                {user?.role === 'admin' || user?.role === 'superadmin'
                  ? '👑 Admin'
                  : user?.role === 'teacher'
                  ? `👨‍🏫 ${t('tma_role_teacher')}`
                  : `🎓 ${t('tma_role_student')}`}
              </span>
              <span className="tma-badge" style={{ background: '#fef3c7', color: '#b45309' }}>
                {leagueTitle}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Streak & XP Highlight */}
      <div className="tma-grid2" style={{ marginBottom: 16 }}>
        <div className="tma-stat" style={{ borderLeft: '4px solid #f97316' }}>
          <p>🔥 {t('tma_streak_label')}</p>
          <b style={{ color: '#ea580c' }}>{streak} {t('tma_days_suffix')}</b>
        </div>
        <div className="tma-stat" style={{ borderLeft: '4px solid #d97706' }}>
          <p>⚡ {t('tma_total_xp_label')}</p>
          <b style={{ color: '#d97706' }}>{stats?.total_xp ?? 0}</b>
        </div>
      </div>

      {/* Learning stats */}
      <div className="tma-card" style={{ marginBottom: 16 }}>
        <p className="tma-sub" style={{ fontWeight: 700, color: 'var(--tma-ink)', marginBottom: 12 }}>
          📊 {t('tma_stats_heading')}
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <span className="tma-muted" style={{ fontSize: 11 }}>{t('tma_tests_taken')}:</span>
            <p style={{ margin: '2px 0 0', fontWeight: 800, fontSize: 18 }}>{stats?.tests_taken ?? 0}</p>
          </div>
          <div>
            <span className="tma-muted" style={{ fontSize: 11 }}>{t('tma_tests_passed')}:</span>
            <p style={{ margin: '2px 0 0', fontWeight: 800, fontSize: 18, color: '#16a34a' }}>
              {stats?.tests_passed ?? 0}
            </p>
          </div>
          <div>
            <span className="tma-muted" style={{ fontSize: 11 }}>{t('tma_essays_written')}:</span>
            <p style={{ margin: '2px 0 0', fontWeight: 800, fontSize: 18 }}>{stats?.essays_written ?? 0}</p>
          </div>
          <div>
            <span className="tma-muted" style={{ fontSize: 11 }}>{t('tma_certificates_count')}:</span>
            <p style={{ margin: '2px 0 0', fontWeight: 800, fontSize: 18, color: '#d97706' }}>
              {stats?.certificates ?? 0}
            </p>
          </div>
        </div>
      </div>

      {/* Data-grounded Learning Insights */}
      {insights && (
        <div className="tma-card" style={{ marginBottom: 16 }}>
          <p className="tma-sub" style={{ fontWeight: 700, color: 'var(--tma-ink)', marginBottom: 10 }}>
            📈 {t('ins_title')}
          </p>
          {!insights.has_sufficient_data ? (
            <p className="tma-muted" style={{ margin: '0 0 8px', fontSize: 12 }}>
              {t('ins_min_samples_hint').replace('{n}', String(insights.min_subject_samples))}
            </p>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
              {insights.strongest_subject && (
                <div style={{ background: 'var(--tma-green-light)', borderRadius: 10, padding: '8px 10px' }}>
                  <span className="tma-muted" style={{ fontSize: 11 }}>{t('ins_strongest')}</span>
                  <p style={{ margin: '2px 0 0', fontWeight: 700, fontSize: 13, color: 'var(--tma-green-text)', textTransform: 'capitalize' }}>
                    {insights.strongest_subject.subject} ({insights.strongest_subject.avg_percentage}%)
                  </p>
                </div>
              )}
              {insights.weakest_subject && (
                <div style={{ background: 'var(--tma-accent-light)', borderRadius: 10, padding: '8px 10px' }}>
                  <span className="tma-muted" style={{ fontSize: 11 }}>{t('ins_weakest')}</span>
                  <p style={{ margin: '2px 0 0', fontWeight: 700, fontSize: 13, color: 'var(--tma-accent-text)', textTransform: 'capitalize' }}>
                    {insights.weakest_subject.subject} ({insights.weakest_subject.avg_percentage}%)
                  </p>
                </div>
              )}
            </div>
          )}

          {insights.improvement_trend && (
            <p className="tma-sub" style={{ margin: '0 0 8px', fontSize: 12 }}>
              {t('ins_trend_label')}:{' '}
              <strong style={{ color: insights.improvement_trend.delta_percentage >= 0 ? '#16a34a' : '#dc2626' }}>
                {insights.improvement_trend.delta_percentage >= 0 ? '+' : ''}
                {insights.improvement_trend.delta_percentage}%
              </strong>{' '}
              ({insights.improvement_trend.recent_avg}% / {insights.improvement_trend.prior_avg}%)
            </p>
          )}

          <p className="tma-sub" style={{ margin: '0 0 8px', fontSize: 12 }}>
            ✅ {t('ins_assignments_done')}:{' '}
            <strong>
              {insights.assignments.completed}/{insights.assignments.active_total}
            </strong>
            {insights.assignments.completion_rate !== null ? ` (${insights.assignments.completion_rate}%)` : ''}
          </p>

          {insights.essays.recent_teacher_feedback.length > 0 && (
            <div style={{ borderTop: '1px solid var(--tma-border)', paddingTop: 8 }}>
              <span className="tma-muted" style={{ fontSize: 11 }}>{t('ins_latest_feedback')}</span>
              {insights.essays.recent_teacher_feedback.slice(0, 2).map((fb) => (
                <div key={fb.submission_id} style={{ marginTop: 6, fontSize: 12 }}>
                  <strong>{fb.topic_title || `#${fb.submission_id}`}</strong> — {fb.final_score}/24
                  {fb.has_voice_feedback ? ' 🎙️' : ''}
                  {fb.comments && (
                    <p className="tma-muted" style={{ margin: '2px 0 0', fontSize: 11 }}>
                      {fb.comments}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Privacy & Optional Gamification Preferences */}
      <div className="tma-card" style={{ marginBottom: 16 }}>
        <p className="tma-sub" style={{ fontWeight: 700, color: 'var(--tma-ink)', marginBottom: 10 }}>
          🛡️ {t('tma_privacy_heading')}
        </p>
        <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 13, marginBottom: 10, gap: 8 }}>
          <span>{t('tma_privacy_opt_in')}</span>
          <input
            type="checkbox"
            checked={lbOptIn}
            disabled={savingPref}
            onChange={(e) => {
              const next = e.target.checked;
              setLbOptIn(next);
              void savePrivacySettings(next, pseudonym, streakOptIn);
            }}
          />
        </label>
        <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
          <input
            className="tma-input"
            placeholder={t('tma_pseudonym_placeholder')}
            maxLength={40}
            value={pseudonym}
            onChange={(e) => setPseudonym(e.target.value)}
          />
          <button
            type="button"
            className="tma-btn tma-btn-hl"
            style={{ width: 'auto', padding: '0 14px', fontSize: 12 }}
            disabled={savingPref}
            onClick={() => void savePrivacySettings(lbOptIn, pseudonym, streakOptIn)}
          >
            {t('tma_save')}
          </button>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 13, gap: 8 }}>
          <span>{t('tma_streak_opt_in')}</span>
          <input
            type="checkbox"
            checked={streakOptIn}
            disabled={savingPref}
            onChange={(e) => {
              const next = e.target.checked;
              setStreakOptIn(next);
              void savePrivacySettings(lbOptIn, pseudonym, next);
            }}
          />
        </label>
        {savedNotice && <p className="tma-sub" style={{ margin: '8px 0 0', color: '#16a34a' }}>{savedNotice}</p>}
      </div>

      {/* Language Switcher */}
      <div className="tma-card">
        <p className="tma-sub" style={{ fontWeight: 700, color: 'var(--tma-ink)', marginBottom: 10 }}>
          🌐 {t('language') || 'Tilni tanlash'}
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
          <button
            type="button"
            className={`tma-btn ${lang === 'uz' ? 'tma-btn-hl' : 'tma-btn-card'}`}
            style={{ padding: '8px 10px', fontSize: 12 }}
            onClick={() => setLang('uz')}
          >
            O'zbekcha
          </button>
          <button
            type="button"
            className={`tma-btn ${lang === 'ru' ? 'tma-btn-hl' : 'tma-btn-card'}`}
            style={{ padding: '8px 10px', fontSize: 12 }}
            onClick={() => setLang('ru')}
          >
            Русский
          </button>
          <button
            type="button"
            className={`tma-btn ${lang === 'en' ? 'tma-btn-hl' : 'tma-btn-card'}`}
            style={{ padding: '8px 10px', fontSize: 12 }}
            onClick={() => setLang('en')}
          >
            English
          </button>
        </div>
      </div>
    </div>
  );
}
