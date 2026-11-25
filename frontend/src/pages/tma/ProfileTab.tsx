import { useEffect, useState } from 'react';
import { useLang } from '../../i18n/LangContext';
import { TmaApi } from './api';
import type { TmaProfile } from './api';

export default function ProfileTab({ profile }: { profile: TmaProfile | null }) {
  const { lang, setLang, t } = useLang();
  const [lbOptIn, setLbOptIn] = useState(Boolean(profile?.stats?.leaderboard_opt_in));
  const [pseudonym, setPseudonym] = useState(profile?.stats?.leaderboard_pseudonym || '');
  const [streakOptIn, setStreakOptIn] = useState(profile?.stats?.streak_opt_in !== false);
  const [savingPref, setSavingPref] = useState(false);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  useEffect(() => {
    TmaApi.gamificationSettings()
      .then((s) => {
        setLbOptIn(s.leaderboard_opt_in);
        setPseudonym(s.leaderboard_pseudonym || '');
        setStreakOptIn(s.streak_opt_in);
      })
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
      setSavedNotice('✓ Saqlandi');
    } catch {
      setSavedNotice('✕ Xatolik yuz berdi');
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
      ? '💎 Olmos liga'
      : league === 'gold'
      ? '🥇 Oltin liga'
      : league === 'silver'
      ? '🥈 Kumush liga'
      : '🥉 Bronza liga';

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
              <span className="tma-badge" style={{ background: '#f1f5f9', color: '#475569' }}>
                {user?.role === 'teacher' ? "👨‍🏫 O'qituvchi" : '🎓 O\'quvchi'}
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
          <p>🔥 Faollik streaki</p>
          <b style={{ color: '#ea580c' }}>{streak} kun</b>
        </div>
        <div className="tma-stat" style={{ borderLeft: '4px solid #d97706' }}>
          <p>⚡ Jami tajriba (XP)</p>
          <b style={{ color: '#d97706' }}>{stats?.total_xp ?? 0}</b>
        </div>
      </div>

      {/* Learning stats */}
      <div className="tma-card" style={{ marginBottom: 16 }}>
        <p className="tma-sub" style={{ fontWeight: 700, color: 'var(--tma-ink)', marginBottom: 12 }}>
          📊 O'quv faoliyati statistikasi
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <span className="tma-muted" style={{ fontSize: 11 }}>Topshirilgan testlar:</span>
            <p style={{ margin: '2px 0 0', fontWeight: 800, fontSize: 18 }}>{stats?.tests_taken ?? 0} ta</p>
          </div>
          <div>
            <span className="tma-muted" style={{ fontSize: 11 }}>Muvaffaqiyatli:</span>
            <p style={{ margin: '2px 0 0', fontWeight: 800, fontSize: 18, color: '#16a34a' }}>
              {stats?.tests_passed ?? 0} ta
            </p>
          </div>
          <div>
            <span className="tma-muted" style={{ fontSize: 11 }}>Yozilgan esselar:</span>
            <p style={{ margin: '2px 0 0', fontWeight: 800, fontSize: 18 }}>{stats?.essays_written ?? 0} ta</p>
          </div>
          <div>
            <span className="tma-muted" style={{ fontSize: 11 }}>Sertifikatlar:</span>
            <p style={{ margin: '2px 0 0', fontWeight: 800, fontSize: 18, color: '#d97706' }}>
              {stats?.certificates ?? 0} ta
            </p>
          </div>
        </div>
      </div>

      {/* Privacy & Optional Gamification Preferences */}
      <div className="tma-card" style={{ marginBottom: 16 }}>
        <p className="tma-sub" style={{ fontWeight: 700, color: 'var(--tma-ink)', marginBottom: 10 }}>
          🛡️ Reyting va maxfiylik sozlamalari
        </p>
        <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 13, marginBottom: 10, gap: 8 }}>
          <span>Umumiy reytingda qatnashish (ixtiyoriy)</span>
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
            placeholder="Taxallus (masalan: Lochin_01)"
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
            Saqlash
          </button>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 13, gap: 8 }}>
          <span>Kunlik streak hisoblagichini yoqish</span>
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
