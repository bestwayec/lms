import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, Menu, Moon, PanelLeftClose, PanelLeftOpen, Sun } from 'lucide-react';
import { useAuth } from '../auth/authState';
import { useLang } from '../i18n/LangContext';
import { isPlatformAdmin, type StreakInfoResponse } from '../lib/api';
import { initialsOf } from '../lib/displayName';
import { useTier } from '../lib/useTier';
import { ShieldCheckIcon } from './icons';
import SubjectSwitcher from './SubjectSwitcher';
import UserNavDropdown from './UserNavDropdown';
import { useTheme } from '../theme/themeState';
import type { WorkspaceMode } from '../lib/routeTitle';

interface NavbarProps {
  streakData?: StreakInfoResponse | null;
  onOpenProfile?: () => void;
  onOpenMenu?: () => void;
  pageTitle?: string;
  workspace?: WorkspaceMode;
  showSubjectSwitcher?: boolean;
  sidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
}

const WORKSPACE_LABELS: Record<WorkspaceMode, string> = {
  admin: 'Admin Boshqaruvi',
  teacher: "O'qituvchi Kabineti",
  student: "O'quvchi Kabineti",
  parent: 'Ota-ona Nazorati',
};

export default function Navbar({
  streakData,
  onOpenProfile,
  onOpenMenu,
  pageTitle = 'GRANDEC',
  workspace = 'student',
  showSubjectSwitcher = true,
  sidebarCollapsed = false,
  onToggleSidebar,
}: NavbarProps) {
  const { user } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isAdmin = isPlatformAdmin(user);
  const tier = useTier();
  const { resolvedTheme, setTheme } = useTheme();

  const isRootOrDashboard = pathname === '/' || pathname === '/dashboard' || pathname === '/panel';
  const streakDays = streakData?.current_streak ?? 1;

  const toggleTheme = () => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
  };

  return (
    <header
      className="topbar app-topbar px-3 md:px-6"
      aria-label={t('topbar_label', 'Yuqori panel')}
      style={{
        paddingTop: 'max(env(safe-area-inset-top, 0px), 6px)',
        minHeight: 'calc(58px + max(env(safe-area-inset-top, 0px), 6px))',
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
      <div className="topbar-inner w-full flex items-center justify-between gap-2 md:gap-3 min-w-0">
        {/* Left: Sidebar collapse (desktop) + mobile menu/brand */}
        <div className="flex items-center gap-2 min-w-0 shrink-0">
          {onToggleSidebar && (
            <button
              type="button"
              onClick={onToggleSidebar}
              className="hidden md:inline-flex items-center justify-center w-9 h-9 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60"
              aria-label={sidebarCollapsed ? 'Yon menyuni ochish' : 'Yon menyuni yig‘ish'}
              aria-expanded={!sidebarCollapsed}
              title={sidebarCollapsed ? 'Yon menyuni ochish' : 'Yon menyuni yig‘ish'}
            >
              {sidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
            </button>
          )}

          {onOpenMenu && (
            <button
              type="button"
              onClick={onOpenMenu}
              className="md:hidden inline-flex items-center justify-center w-10 h-10 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200"
              aria-label={t('nav_menu_label', 'Menyuni ochish')}
            >
              <Menu size={19} />
            </button>
          )}

          {!isRootOrDashboard && (
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="md:hidden p-1.5 rounded-lg text-slate-500 dark:text-slate-300 hover:bg-slate-200/50 dark:hover:bg-slate-800/50"
              aria-label="Orqaga qaytish"
            >
              <ArrowLeft size={19} />
            </button>
          )}

          <Link
            to={workspace === 'admin' ? '/panel' : '/dashboard'}
            className="md:hidden flex items-center gap-2 no-underline min-w-0"
            style={{ textDecoration: 'none' }}
          >
            <div
              style={{
                width: 30,
                height: 30,
                borderRadius: 9,
                background: 'linear-gradient(135deg, #d97706, #f59e0b)',
                padding: 2,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                flexShrink: 0,
              }}
            >
              <img src="/logo-mark.png" alt="GRANDEC" style={{ width: 26, height: 26, objectFit: 'contain' }} />
            </div>
            <span className="font-extrabold text-sm tracking-tight leading-none truncate" style={{ color: 'var(--text-primary)' }}>
              {pageTitle}
            </span>
          </Link>

          {/* Desktop context title when student SubjectSwitcher is intentionally hidden */}
          {!showSubjectSwitcher && (
            <div className="hidden md:flex items-center gap-2.5 min-w-0">
              <span className="g-badge g-badge--info">{WORKSPACE_LABELS[workspace]}</span>
              <span className="font-extrabold text-sm truncate" style={{ color: 'var(--text-primary)' }}>
                {pageTitle}
              </span>
            </div>
          )}
        </div>

        {/* Center: Student Subject Switcher ONLY in Student / subject study contexts */}
        {showSubjectSwitcher && (
          <div className="hidden md:flex items-center justify-center flex-1 min-w-0 max-w-xl mx-auto">
            <SubjectSwitcher size="sm" variant="pill" />
          </div>
        )}

        {/* Right Section: Streak (Student), Theme Toggle, PRO Badge (Non-Admin), Panel Pill (Admin), Avatar */}
        <div className="flex items-center gap-2 md:gap-2.5 shrink-0">
          {workspace === 'student' && streakData && (
            <div className="hidden sm:inline-flex items-center gap-1.5">
              <span className="pill-badge" style={{ borderColor: 'rgba(245, 158, 11, 0.35)', background: 'rgba(245, 158, 11, 0.12)', color: '#d97706' }}>
                🔥 {streakDays} {t('dsh_days_unit')}
              </span>
              <span className="hidden lg:inline-flex text-xs font-bold font-mono px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700">
                {streakData.xp_points} XP
              </span>
            </div>
          )}

          <button
            type="button"
            onClick={toggleTheme}
            className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60 transition-colors"
            aria-label={t('drawer_theme')}
            title={resolvedTheme === 'dark' ? `☀️ ${t('nav_theme_light')}` : `🌙 ${t('nav_theme_dark')}`}
          >
            {resolvedTheme === 'dark' ? (
              <Sun size={17} className="text-amber-400" />
            ) : (
              <Moon size={17} className="text-indigo-600" />
            )}
          </button>

          {workspace !== 'admin' && !isAdmin && (
            <Link
              to="/subscribe"
              style={{ textDecoration: 'none' }}
              className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30 hover:bg-amber-500/25 transition-colors no-underline"
            >
              <span>👑</span>
              <span>{tier.isPaid ? 'PRO' : t('nav_go_pro')}</span>
            </Link>
          )}

          {isAdmin && workspace !== 'admin' && (
            <Link
              to="/panel"
              style={{ textDecoration: 'none' }}
              className="hidden xl:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30 hover:bg-indigo-500/25 transition-colors no-underline"
            >
              <ShieldCheckIcon size={14} />
              <span>{t('tb_admin_panel', 'Admin')}</span>
            </Link>
          )}

          <div className="hidden md:flex items-center">
            <UserNavDropdown />
          </div>

          <button
            type="button"
            className="md:hidden flex items-center justify-center w-9 h-9 rounded-full overflow-hidden border-2 border-amber-500/60 shadow-sm"
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
