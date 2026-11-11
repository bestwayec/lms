import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, Moon, Sun } from 'lucide-react';
import { useAuth } from '../auth/authState';
import { useLang } from '../i18n/LangContext';
import { isPlatformAdmin, type StreakInfoResponse } from '../lib/api';
import { initialsOf } from '../lib/displayName';
import { useTier } from '../lib/useTier';
import { ShieldCheckIcon } from './icons';
import SubjectSwitcher from './SubjectSwitcher';
import UserNavDropdown from './UserNavDropdown';
import { useTheme } from '../theme/themeState';

interface NavbarProps {
  streakData?: StreakInfoResponse | null;
  onOpenProfile?: () => void;
  pageTitle?: string;
}

/**
 * GRANDEC 2.0 Top Command Bar (Navbar)
 * Left: Golden Humo winged GRANDEC logo
 * Center: Horizontal Pill-Shaped Subject Switcher (English, Chemistry, Biology, Law, Uzbek)
 * Right: Streak & XP Badge, Theme Toggle (Sun/Moon), PRO Badge, Circular Avatar
 */
export default function Navbar({ streakData, onOpenProfile, pageTitle: _pageTitle = 'GRANDEC' }: NavbarProps) {
  const { user } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isAdmin = isPlatformAdmin(user);
  const tier = useTier();
  const { resolvedTheme, setTheme } = useTheme();

  const isRootOrDashboard = pathname === '/' || pathname === '/dashboard';
  const streakDays = streakData?.current_streak ?? 1;

  const toggleTheme = () => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
  };

  return (
    <header
      className="topbar app-topbar px-3 md:px-6"
      aria-label={t('topbar_label', 'Yuqori panel')}
      style={{
        paddingTop: 'max(env(safe-area-inset-top, 0px), 8px)',
        height: 'calc(56px + max(env(safe-area-inset-top, 0px), 8px))',
        display: 'flex',
        alignItems: 'center',
        position: 'sticky',
        top: 0,
        zIndex: 40,
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        backgroundColor: 'var(--topbar-bg)',
        borderBottom: '1px solid var(--border-subtle)',
      }}
    >
      <div className="topbar-inner w-full h-14 flex items-center justify-between gap-2 md:gap-3 min-w-0" style={{ height: '100%' }}>
        {/* Left: Mobile-only branding (Hidden on Desktop >= 768px where Sidebar is active) */}
        <div className="flex items-center gap-2 shrink-0 md:hidden">
          {!isRootOrDashboard && (
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800/50 active:scale-95 transition-all"
              aria-label="Orqaga qaytish"
            >
              <ArrowLeft size={19} />
            </button>
          )}

          <Link
            to="/dashboard"
            className="flex items-center gap-2 group no-underline"
            style={{ textDecoration: 'none' }}
          >
            <div
              style={{
                width: 32,
                height: 32,
                minWidth: 32,
                minHeight: 32,
                maxWidth: 32,
                maxHeight: 32,
                borderRadius: 10,
                background: 'linear-gradient(135deg, #d97706, #f59e0b)',
                padding: 2,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                flexShrink: 0,
              }}
            >
              <img
                src="/logo-mark.png"
                alt="GRANDEC"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
                style={{
                  width: 28,
                  height: 28,
                  maxWidth: 28,
                  maxHeight: 28,
                  objectFit: 'contain',
                  borderRadius: 6,
                  display: 'block',
                }}
              />
            </div>
            <span
              className="font-extrabold text-sm tracking-tight leading-none text-slate-900 dark:text-white"
              style={{ textDecoration: 'none' }}
            >
              GRANDEC
            </span>
          </Link>
        </div>

        {/* Center: Gorizontal Pill-Shaped Fan Tanlagich (Desktop & Tablet) */}
        <div className="hidden md:flex items-center justify-center flex-1 max-w-xl mx-auto">
          <SubjectSwitcher size="sm" variant="pill" />
        </div>

        {/* Right Section: Streak, Theme Switcher, PRO badge, Avatar */}
        <div className="flex items-center gap-2 md:gap-3 shrink-0">
          {/* Streak nishoni */}
          {streakData && (
            <div className="hidden sm:inline-flex items-center gap-1.5">
              <span className="pill-badge" style={{ borderColor: 'rgba(245, 158, 11, 0.35)', background: 'rgba(245, 158, 11, 0.12)', color: '#d97706' }}>
                <span className="animate-pulse">🔥</span> {streakDays} {t('dsh_days_unit')}
              </span>
              <span className="hidden md:inline-flex text-xs font-bold font-mono px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700">
                {streakData.xp_points} XP
              </span>
            </div>
          )}

          {/* Theme Switcher Toggle (☀️ / 🌙) */}
          <button
            type="button"
            onClick={toggleTheme}
            className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60 active:scale-95 transition-all"
            aria-label={t('drawer_theme')}
            title={resolvedTheme === 'dark' ? `☀️ ${t('nav_theme_light')}` : `🌙 ${t('nav_theme_dark')}`}
          >
            {resolvedTheme === 'dark' ? (
              <Sun size={17} className="text-amber-400" />
            ) : (
              <Moon size={17} className="text-indigo-600" />
            )}
          </button>

          {/* 👑 PRO Badge */}
          <Link
            to="/subscribe"
            style={{ textDecoration: 'none' }}
            className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30 hover:bg-amber-500/25 transition-colors no-underline"
          >
            <span>👑</span>
            <span>{tier.isPaid ? 'PRO' : t('nav_go_pro')}</span>
          </Link>

          {/* Admin panel shortcut for staff */}
          {isAdmin && (
            <Link
              to="/panel"
              style={{ textDecoration: 'none' }}
              className="hidden xl:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30 hover:bg-indigo-500/25 transition-colors no-underline"
            >
              <ShieldCheckIcon size={14} />
              <span>{t('tb_admin_panel', 'Admin')}</span>
            </Link>
          )}

          {/* Desktop User Dropdown with Circular Avatar */}
          <div className="hidden md:flex items-center">
            <UserNavDropdown />
          </div>

          {/* Mobile Circular KR Avatar Trigger */}
          <button
            type="button"
            className="md:hidden flex items-center justify-center w-9 h-9 rounded-full overflow-hidden border-2 border-amber-500/60 shadow-sm active:scale-95 transition-transform"
            onClick={onOpenProfile}
            aria-label={t('tb_open_profile', 'Profil')}
            style={{
              background: 'linear-gradient(135deg, #d97706, #b45309)',
              color: '#ffffff',
              fontSize: '12px',
              fontWeight: 800,
            }}
          >
            {user?.avatar ? (
              <img src={user.avatar} alt="" className="w-full h-full object-cover" />
            ) : (
              <span>{initialsOf(user?.full_name, user?.email)}</span>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
