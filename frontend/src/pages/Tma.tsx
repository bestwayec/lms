import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useLang } from '../i18n/LangContext';
import { TelegramAuth } from '../lib/api';
import { TmaApi } from './tma/api';
import type { TmaProfile } from './tma/api';
import { loadTelegramScript, tg } from './tma/telegram';
import Home from './tma/Home';
import TestFlow from './tma/TestFlow';
import Essays from './tma/Essays';
import './tma/Tma.css';

/** Bot username fallback for the "open in Telegram" link (mirrors settings.TELEGRAM_BOT_NAME default). */
const BOT_USERNAME = 'uz_essaygrader_bot';

type Boot = 'boot' | 'outside' | 'authing' | 'ready' | 'error';
type Tab = 'home' | 'essays';

/**
 * Dedicated Telegram Mini App (routes /tma + /tma/, public).
 * Old tma/index.html parity: dark mini-app shell, bottom tabs, test player,
 * essay writer — all over /tma/api/* JSON. NOT the full website.
 */
export default function Tma() {
  const { user, loginWithTelegram } = useAuth();
  const { t, setLang } = useLang();
  const [boot, setBoot] = useState<Boot>('boot');
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<TmaProfile | null>(() => {
    try {
      const raw = localStorage.getItem('tma_cached_profile');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [tab, setTab] = useState<Tab>('home');
  const [activeTestId, setActiveTestId] = useState<number | null>(null);
  const backHandlerRef = useRef<(() => void) | null>(null);

  const setBackHandler = useCallback((fn: (() => void) | null) => {
    backHandlerRef.current = fn;
  }, []);

  // Sync Telegram BackButton with the registered handler (every render).
  useEffect(() => {
    const bb = tg()?.BackButton;
    if (!bb) return;
    const h = backHandlerRef.current;
    if (!h) {
      bb.hide();
      return;
    }
    bb.show();
    bb.onClick(h);
    return () => {
      bb.offClick(h);
      bb.hide();
    };
  });

  useEffect(() => {
    let cancelled = false;
    const timeoutId = setTimeout(() => {
      if (!cancelled) {
        setError("Telegram Mini App ma'lumotlari yuklanmadi yoki tarmoq javob bermadi.");
        setBoot((current) => (current === 'boot' || current === 'authing' ? 'error' : current));
      }
    }, 5000);

    (async () => {
      await loadTelegramScript();
      if (cancelled) return;
      const wa = tg();
      const rawLang = wa?.initDataUnsafe?.user?.language_code?.toLowerCase();
      if (rawLang) {
        const detected = rawLang.startsWith('ru') ? 'ru' : rawLang.startsWith('en') ? 'en' : 'uz';
        setLang(detected);
      }
      const initData = wa?.initData ?? '';
      if (!wa || !initData) {
        clearTimeout(timeoutId);
        setBoot(user ? 'ready' : 'outside');
        return;
      }
      try {
        wa.ready();
        wa.expand();
        try {
          wa.setHeaderColor('#FFFFFF');
          wa.setBackgroundColor('#F8FAFC');
        } catch {
          /* older clients — ignore */
        }
      } catch {
        /* non-critical */
      }
      setBoot('authing');
      try {
        const data = await TelegramAuth.loginWithInitData(initData);
        if (cancelled) return;
        if (!data.tokens || !data.user) throw new Error('Telegram auth failed');
        loginWithTelegram(data.tokens, data.user);
        clearTimeout(timeoutId);

        // Immediate responsive transition: construct baseline profile so UI renders with 0 delay
        const u = data.user as { id?: number | string; email?: string; full_name?: string; role?: string };
        setProfile((prev) => prev ?? {
          user: {
            id: Number(u.id) || 0,
            email: String(u.email || ''),
            full_name: String(u.full_name || ''),
            role: String(u.role || 'student'),
          },
          stats: {
            tests_taken: 0,
            tests_passed: 0,
            certificates: 0,
            total_xp: 0,
            essays_written: 0,
          },
        });
        setBoot('ready');

        // Refresh stats concurrently in background without blocking screen render
        TmaApi.profile().then((prof) => {
          if (!cancelled && prof) {
            setProfile(prof);
            try {
              localStorage.setItem('tma_cached_profile', JSON.stringify(prof));
            } catch {
              /* ignore storage quota */
            }
          }
        }).catch(() => undefined);
      } catch (e) {
        if (cancelled) return;
        clearTimeout(timeoutId);
        setError(e instanceof Error ? e.message : 'Telegram auth failed');
        setBoot('error');
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Refresh header stats when returning to tabs.
  const refreshProfile = useCallback(() => {
    TmaApi.profile().then(setProfile).catch(() => undefined);
  }, []);

  const openTest = (id: number) => {
    backHandlerRef.current = null;
    setActiveTestId(id);
  };

  const exitFlow = () => {
    backHandlerRef.current = null;
    setActiveTestId(null);
    refreshProfile();
  };

  const switchTab = (next: Tab) => {
    backHandlerRef.current = null;
    setActiveTestId(null);
    setTab(next);
    refreshProfile();
  };

  if (boot === 'boot' || boot === 'authing') {
    return (
      <div className="tma-root">
        <div className="tma-auth">
          <div>
            <div className="tma-spin" />
            <p className="tma-muted tma-center">{t('tma_checking')}</p>
          </div>
        </div>
      </div>
    );
  }

  if (boot === 'outside') {
    return (
      <div className="tma-root">
        <div className="tma-auth">
          <div className="tma-auth-card" style={{ maxWidth: 360, textAlign: 'center', padding: '24px 20px' }}>
            <div className="tma-auth-logo" style={{ fontSize: 36, marginBottom: 8 }}>📚</div>
            <h1 style={{ fontSize: 22, fontWeight: 800, margin: '0 0 8px' }}>Ona Tili &amp; Adabiyot</h1>
            <p className="tma-muted" style={{ marginBottom: 20 }}>{t('tma_open_in_telegram')}</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <a
                className="tma-btn tma-btn-hl"
                href={`https://t.me/${BOT_USERNAME}`}
                target="_blank"
                rel="noreferrer"
                style={{ display: 'block', textDecoration: 'none' }}
              >
                Telegram botda ochish
              </a>
              <button
                type="button"
                className="tma-btn tma-btn-card"
                onClick={() => window.open(window.location.origin, '_blank')}
                style={{ width: '100%' }}
              >
                🌐 Brauzerda ochish
              </button>
              <button
                type="button"
                className="tma-btn tma-btn-card"
                onClick={() => window.location.reload()}
                style={{ width: '100%' }}
              >
                🔄 Qayta urinish
              </button>
            </div>
            <p className="tma-muted" style={{ marginTop: 16 }}>
              <Link to="/login" style={{ color: 'var(--tma-hl)' }}>{t('login_with_telegram')}</Link>
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (boot === 'error') {
    return (
      <div className="tma-root">
        <div className="tma-auth">
          <div className="tma-auth-card" style={{ maxWidth: 360, textAlign: 'center', padding: '24px 20px' }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>⚠️</div>
            <h1 style={{ fontSize: 20, fontWeight: 800, margin: '0 0 8px' }}>Xatolik yuz berdi</h1>
            <p style={{ color: '#f87171', fontSize: '0.9rem', marginBottom: 20, lineHeight: 1.5 }}>
              {error || "Telegram orqali tizimga kirishda nosozlik yuz berdi."}
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <button
                type="button"
                className="tma-btn tma-btn-hl"
                onClick={() => window.location.reload()}
                style={{ width: '100%' }}
              >
                🔄 Qayta urinish
              </button>
              <button
                type="button"
                className="tma-btn tma-btn-card"
                onClick={() => window.open(window.location.origin, '_blank')}
                style={{ width: '100%' }}
              >
                🌐 Brauzerda ochish
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const firstName = user?.first_name || (user?.full_name ?? '').split(' ')[0] || '';
  const inFlow = activeTestId !== null;

  return (
    <div className="tma-root">
      <div className="tma-wrap">
        <header className="tma-header">
          <h1>{firstName ? `Salom, ${firstName}!` : t('dashboard')}</h1>
          <span className="tma-xp">⚡ {profile?.stats.total_xp ?? 0} XP</span>
        </header>

        <main className="tma-main">
          {inFlow ? (
            <TestFlow testId={activeTestId} onExit={exitFlow} setBackHandler={setBackHandler} />
          ) : tab === 'home' ? (
            <Home profile={profile} onProfileLoaded={setProfile} onOpenTest={openTest} />
          ) : (
            <Essays setBackHandler={setBackHandler} />
          )}
        </main>

        {!inFlow && (
          <nav className="tma-nav">
            <div className="tma-nav-inner">
              <button className={tab === 'home' ? 'on' : ''} onClick={() => switchTab('home')}>
                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>
                <span>{t('tma_home')}</span>
              </button>
              <button
                className={tab === 'home' ? 'on' : ''}
                onClick={() => {
                  switchTab('home');
                  window.scrollTo({ top: 0 });
                }}
              >
                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                <span>{t('tma_tests')}</span>
              </button>
              <button className={tab === 'essays' ? 'on' : ''} onClick={() => switchTab('essays')}>
                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                <span>{t('tma_essays_tab')}</span>
              </button>
            </div>
          </nav>
        )}
      </div>
    </div>
  );
}
