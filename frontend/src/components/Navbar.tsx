import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useLang } from '../i18n/LangContext';
import { isPlatformAdmin, type StreakInfoResponse } from '../lib/api';
import { initialsOf } from '../lib/displayName';
import { useSubject } from '../lib/useSubject';
import { ShieldCheckIcon } from './icons';
import StreakBadge from './StreakBadge';
import SubjectSwitcher from './SubjectSwitcher';
import UserNavDropdown from './UserNavDropdown';

interface NavbarProps {
  streakData?: StreakInfoResponse | null;
  onOpenProfile?: () => void;
  pageTitle?: string;
}

/**
 * Compact Top Navbar (Height 56px / h-14)
 * Mobile:
 * - Back button (when not on dashboard/home)
 * - Brand logo + dynamic section title
 * - Profile avatar toggle button
 * Desktop:
 * - Brand motto badge
 * - Streak & XP counter
 * - Desktop SubjectSwitcher
 * - Admin panel shortcut (for staff)
 * - User dropdown menu
 */
export default function Navbar({ streakData, onOpenProfile, pageTitle = 'GRANDEC' }: NavbarProps) {
  const { user } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const activeSubject = useSubject();
  const isAdmin = isPlatformAdmin(user);

  const isRootOrDashboard = pathname === '/' || pathname === '/dashboard';

  return (
    <header
      className="topbar app-topbar px-3 md:px-6"
      aria-label={t('topbar_label', 'Yuqori panel')}
      style={{
        paddingTop: 'max(env(safe-area-inset-top, 0px), 12px)',
        height: 'calc(56px + max(env(safe-area-inset-top, 0px), 12px))',
        display: 'flex',
        alignItems: 'center',
        position: 'sticky',
        top: 0,
        zIndex: 40,
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        borderBottom: '1px solid var(--border, rgba(255, 255, 255, 0.08))',
      }}
    >
      <div className="topbar-inner w-full flex items-center justify-between" style={{ height: '100%' }}>
        {/* Mobile Left: Back Button or Brand Logo */}
        <div className="flex items-center gap-2 md:hidden min-w-0 flex-1">
          {!isRootOrDashboard ? (
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 active:scale-95 transition-all shrink-0"
              aria-label="Orqaga qaytish"
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <ArrowLeft size={19} />
            </button>
          ) : null}

          <Link to="/dashboard" className="tb-brand flex items-center gap-2 min-w-0 shrink">
            <img
              src="/logo-mark.png"
              alt=""
              onError={(e) => {
                e.currentTarget.style.display = 'none';
              }}
              className="w-6 h-6 shrink-0 object-contain overflow-hidden rounded"
              width={24}
              height={24}
            />
            <span
              className="tb-title font-bold text-sm tracking-tight text-slate-100 truncate min-w-0"
              style={{ maxWidth: '180px' }}
            >
              {pageTitle}
            </span>
          </Link>
        </div>

        {/* Desktop Left: Brand & Motto */}
        <div className="hidden md:flex items-center gap-3">
          <Link to="/dashboard" className="tb-brand flex items-center gap-2">
            <img
              src="/logo-mark.png"
              alt=""
              onError={(e) => {
                e.currentTarget.style.display = 'none';
              }}
              className="w-6 h-6 shrink-0 object-contain overflow-hidden rounded"
              width={24}
              height={24}
            />
            <span className="font-bold text-sm tracking-tight text-slate-100">GRANDEC</span>
          </Link>
          {user?.active_subject && (
            <span className="tb-tag text-xs font-semibold px-2.5 py-1 rounded-md bg-amber-500/10 text-amber-400 border border-amber-500/20">
              {t(activeSubject === 'english' ? 'app_motto_badge_english' : 'app_motto_badge', 'Grand Education')}
            </span>
          )}
        </div>

        <div className="spacer flex-1" />

        {/* Right Section */}
        <div className="tb-right flex items-center gap-2 md:gap-3">
          {streakData && (
            <div className="inline-flex items-center gap-1.5">
              <StreakBadge streakData={streakData} compact />
              <span
                className="tb-xp hidden sm:inline-flex items-center font-bold px-2 py-0.5 rounded-full text-xs"
                style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b', border: '1px solid rgba(245, 158, 11, 0.3)' }}
              >
                {streakData.xp_points} XP
              </span>
            </div>
          )}

          {/* Desktop Subject Switcher */}
          <div className="hidden md:flex">
            <SubjectSwitcher size="sm" />
          </div>

          {/* Desktop Staff Shortcuts & Dropdown */}
          <div className="hidden md:flex items-center gap-2">
            {isAdmin && (
              <Link to="/panel" className="ui-btn ui-btn--sm flex items-center gap-1 text-xs">
                <ShieldCheckIcon size={14} />
                <span>{t('tb_admin_panel', 'Admin panel')}</span>
              </Link>
            )}
            <UserNavDropdown />
          </div>

          {/* Mobile Profile Drawer Trigger */}
          <button
            type="button"
            className="tb-avatar md:hidden flex items-center justify-center w-8 h-8 rounded-full overflow-hidden border border-slate-700 active:scale-95 transition-transform"
            onClick={onOpenProfile}
            aria-label={t('tb_open_profile', 'Profil')}
            style={{
              background: 'linear-gradient(135deg, #d97706, #b45309)',
              color: '#ffffff',
              fontSize: '12px',
              fontWeight: 700,
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
