import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/authState';
import { useLang } from '../i18n/LangContext';
import {
  GamificationApi,
  isPlatformAdmin,
  type StreakInfoResponse,
} from '../lib/api';
import PlanBadge from './PlanBadge';
import { useSubject } from '../lib/useSubject';
import { formatDisplayName, initialsOf } from '../lib/displayName';
import {
  getAvailableWorkspaces,
  getDefaultWorkspace,
  shouldShowSubjectSwitcher,
  type WorkspaceMode,
} from '../lib/routeTitle';
import BottomNav from './BottomNav';
import Navbar from './Navbar';
import MobileNavDrawer from './MobileNavDrawer';
import MobileProfileDrawer from './MobileProfileDrawer';
import SubjectSwitcher from './SubjectSwitcher';
import {
  BarChartIcon,
  CameraIcon,
  CreditCardIcon,
  FileTextIcon,
  FolderOpenIcon,
  HomeIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  MailIcon,
  MicIcon,
  PenLineIcon,
  ShieldCheckIcon,
  SparklesIcon,
  SwordsIcon,
  TrophyIcon,
  UploadIcon,
  UserPlusIcon,
  UsersIcon,
} from './icons';

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `nav-link side-link${isActive ? ' active' : ''}`;

const OWN_TEST_ITEMS = ['/tests/create', '/tests/scan-omr'];
const testsLinkClass = (pathname: string) => ({ isActive }: { isActive: boolean }) =>
  linkClass({ isActive: isActive && !OWN_TEST_ITEMS.some((p) => pathname.startsWith(p)) });

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <>
      <p className="side-section">{title}</p>
      {children}
    </>
  );
}

const PAGE_TITLES: [string, string][] = [
  ['/panel/tests', 'panel_test_control_center'],
  ['/panel/users', 'users'],
  ['/panel/teachers', 'manage_teachers'],
  ['/panel/branches', 'branches'],
  ['/panel/topics', 'essay_topics'],
  ['/panel/tuition', 'tuition_title'],
  ['/panel/feedback', 'fbi_title'],
  ['/panel/groups', 'groups'],
  ['/panel', 'tb_admin_panel'],
  ['/enterprise', 'enterprise_title'],
  ['/dashboard', 'tb_title_home'],
  ['/tests/create', 'create_smart_test'],
  ['/tests/scan-omr', 'titul_scanner'],
  ['/tests', 'tests'],
  ['/take', 'tests'],
  ['/essays', 'tb_title_essays'],
  ['/results', 'results_analysis'],
  ['/arena', 'arena'],
  ['/profile', 'tb_title_profile'],
  ['/groups', 'groups'],
  ['/my-homework', 'my_homework_title'],
  ['/speaking', 'tb_title_speaking'],
  ['/subscribe', 'pay_plans_title'],
  ['/plans', 'pay_plans_title'],
  ['/checkout', 'pay_plans_title'],
  ['/my-subscription', 'pay_current_sub'],
  ['/certificates', 'certificates'],
  ['/games', 'games'],
  ['/teacher/studio', 'studio_title'],
  ['/teacher/essays', 'teacher_queue'],
  ['/teacher/finance', 'tuition_title'],
  ['/teacher', 'teacher_cabinet'],
  ['/analytics', 'analytics'],
];

const WORKSPACE_META: Record<WorkspaceMode, { label: string; landing: string }> = {
  admin: { label: 'Admin', landing: '/panel' },
  teacher: { label: 'Ustoz', landing: '/dashboard' },
  student: { label: "O'quvchi", landing: '/dashboard' },
  parent: { label: 'Ota-ona', landing: '/parent' },
};

export default function Layout() {
  const { user, logout } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem('lms_sidebar_collapsed') === '1';
    } catch {
      return false;
    }
  });
  const [streakData, setStreakData] = useState<StreakInfoResponse | null>(null);
  const [navDrawerOpen, setNavDrawerOpen] = useState(false);
  const [profileDrawerOpen, setProfileDrawerOpen] = useState(false);
  const activeSubject = useSubject();
  const { pathname } = useLocation();

  const availableWorkspaces = getAvailableWorkspaces(user);
  const [workspaceOverride, setWorkspaceOverride] = useState<WorkspaceMode | null>(() => {
    try {
      const saved = sessionStorage.getItem('lms_workspace_mode') as WorkspaceMode | null;
      return saved;
    } catch {
      return null;
    }
  });
  const workspace: WorkspaceMode =
    workspaceOverride && availableWorkspaces.includes(workspaceOverride)
      ? workspaceOverride
      : getDefaultWorkspace(user, pathname);

  const selectWorkspace = (mode: WorkspaceMode) => {
    setWorkspaceOverride(mode);
    try {
      sessionStorage.setItem('lms_workspace_mode', mode);
    } catch {
      /* ignore */
    }
    setOpen(false);
    navigate(WORKSPACE_META[mode].landing);
  };

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('lms_sidebar_collapsed', next ? '1' : '0');
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  const titleKey = PAGE_TITLES.find(([prefix]) => pathname.startsWith(prefix))?.[1];
  const pageTitle = titleKey ? t(titleKey) : 'GRANDEC';

  const isAdmin = isPlatformAdmin(user);
  const showSubjectSwitcher = shouldShowSubjectSwitcher(workspace, pathname);

  useEffect(() => {
    if (!user || isAdmin) return;
    let active = true;
    GamificationApi.streak()
      .then((res) => {
        if (active) setStreakData(res);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [user, isAdmin]);

  const visibleStreakData = !user || isAdmin ? null : streakData;

  const onLogout = async () => {
    await logout();
    navigate('/login');
  };

  const close = () => setOpen(false);
  const examFocus = /^\/take\/\d+/.test(pathname);
  if (examFocus) {
    return (
      <div className="app exam-focus">
        <main id="main-content" className="content exam-focus-content">
          <Outlet />
        </main>
      </div>
    );
  }

  return (
    <div className={`app${sidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
      <aside className={`sidebar${open ? ' open' : ''}`} aria-label="Yon boshqaruv menyusi">
        <Link
          to={workspace === 'admin' ? '/panel' : '/'}
          className="side-brand"
          onClick={close}
          aria-label="GRANDEC LMS"
        >
          <img
            src="/logo-mark.png"
            alt="GRANDEC"
            className="brand-badge"
            style={{ height: 34, width: 34, maxWidth: 34, maxHeight: 34, objectFit: 'contain', background: 'transparent' }}
          />
          <span className="side-brand-text">
            <span className="side-brand-name">GRANDEC</span>
            <span className="side-brand-sub" style={{ color: '#D97706', fontWeight: 700, fontSize: '9px', letterSpacing: '0.12em' }}>
              {workspace === 'admin' ? 'ADMIN CONSOLE' : workspace === 'teacher' ? 'TEACHER STUDIO' : 'ACADEMIC EDTECH'}
            </span>
          </span>
        </Link>

        {/* Multi-role Workspace Switcher */}
        {availableWorkspaces.length > 1 && (
          <div className="side-workspace-switch" role="group" aria-label="Ish maydoni">
            {availableWorkspaces.map((mode) => (
              <button
                key={mode}
                type="button"
                className={`side-ws-btn${workspace === mode ? ' is-active' : ''}`}
                aria-pressed={workspace === mode}
                onClick={() => selectWorkspace(mode)}
                title={WORKSPACE_META[mode].label}
              >
                {WORKSPACE_META[mode].label}
              </button>
            ))}
          </div>
        )}

        <nav className="side-nav" aria-label="Ilova bo'limlari">
          {workspace === 'admin' && (
            <Section title={t('panel', 'Tizim Boshqaruvi')}>
              <NavLink to="/panel" end className={linkClass} onClick={close}>
                <ShieldCheckIcon size={16} className="ico" /> <span className="side-label">{t('panel_dashboard', 'Boshqaruv Paneli')}</span>
              </NavLink>
              <NavLink to="/panel/users" className={linkClass} onClick={close}>
                <UsersIcon size={16} className="ico" /> <span className="side-label">{t('users', 'Foydalanuvchilar')}</span>
              </NavLink>
              <NavLink to="/panel/teachers" className={linkClass} onClick={close}>
                <UserPlusIcon size={16} className="ico" /> <span className="side-label">{t('manage_teachers', "O'qituvchilar")}</span>
              </NavLink>
              <NavLink to="/enterprise" className={linkClass} onClick={close}>
                <LayoutDashboardIcon size={16} className="ico" /> <span className="side-label">{t('enterprise_title', "O'quv Markazlari")}</span>
              </NavLink>
              <NavLink to="/panel/branches" className={linkClass} onClick={close}>
                <HomeIcon size={16} className="ico" /> <span className="side-label">{t('branches', 'Filiallar')}</span>
              </NavLink>
              <NavLink to="/panel/groups" className={linkClass} onClick={close}>
                <FolderOpenIcon size={16} className="ico" /> <span className="side-label">{t('groups', 'Guruhlar')}</span>
              </NavLink>
              <NavLink to="/panel/tests" className={linkClass} onClick={close}>
                <FileTextIcon size={16} className="ico" /> <span className="side-label">{t('all_tests_control', 'Barcha Testlar')}</span>
              </NavLink>
              <NavLink to="/panel/topics" className={linkClass} onClick={close}>
                <PenLineIcon size={16} className="ico" /> <span className="side-label">{t('essay_topics', 'Esse Mavzulari')}</span>
              </NavLink>
              <NavLink to="/teacher/essays" className={linkClass} onClick={close}>
                <SparklesIcon size={16} className="ico" /> <span className="side-label">{t('teacher_queue', 'Esse Tekshiruvi')}</span>
              </NavLink>
              <NavLink to="/panel/tuition" className={linkClass} onClick={close}>
                <CreditCardIcon size={16} className="ico" /> <span className="side-label">{t('tuition_title', "To'lovlar va Cheklar")}</span>
              </NavLink>
              <NavLink to="/analytics" className={linkClass} onClick={close}>
                <BarChartIcon size={16} className="ico" /> <span className="side-label">{t('analytics', 'Hisobotlar')}</span>
              </NavLink>
              <NavLink to="/panel/feedback" className={linkClass} onClick={close}>
                <MailIcon size={16} className="ico" /> <span className="side-label">{t('fbi_title', 'Fikrlar va Murojaatlar')}</span>
              </NavLink>
            </Section>
          )}

          {workspace === 'teacher' && (
            <Section title={t('role_teacher', "O'qituvchi Kabineti")}>
              <NavLink to="/dashboard" end className={linkClass} onClick={close}>
                <LayoutDashboardIcon size={16} className="ico" /> <span className="side-label">{t('teacher_cabinet', "O'qituvchi Kabineti")}</span>
              </NavLink>
              <NavLink to="/groups" className={linkClass} onClick={close}>
                <FolderOpenIcon size={16} className="ico" /> <span className="side-label">{t('my_groups', 'Mening Guruhlarim')}</span>
              </NavLink>
              <NavLink to="/teacher/studio" className={linkClass} onClick={close}>
                <SparklesIcon size={16} className="ico" /> <span className="side-label">{t('studio_title', 'Test Studio')}</span>
              </NavLink>
              <NavLink to="/tests/create" className={linkClass} onClick={close}>
                <SparklesIcon size={16} className="ico" /> <span className="side-label">{t('create_smart_test', 'Yangi Test Yaratish')}</span>
              </NavLink>
              <NavLink to="/tests" className={testsLinkClass(pathname)} onClick={close}>
                <FileTextIcon size={16} className="ico" /> <span className="side-label">{t('my_tests', 'Mening Testlarim')}</span>
              </NavLink>
              <NavLink to="/teacher/finance" className={linkClass} onClick={close}>
                <CreditCardIcon size={16} className="ico" /> <span className="side-label">{t('tuition_title', "To'lov va Davomat")}</span>
              </NavLink>
              <NavLink to="/teacher/ai-converter" className={linkClass} onClick={close}>
                <SparklesIcon size={16} className="ico" /> <span className="side-label">AI Test Konvertor</span>
              </NavLink>
              <NavLink to="/teacher/essays" className={linkClass} onClick={close}>
                <PenLineIcon size={16} className="ico" /> <span className="side-label">{t('teacher_queue', 'Esse Tekshiruvi')}</span>
              </NavLink>
              <NavLink to="/tests/scan-omr" className={linkClass} onClick={close}>
                <CameraIcon size={16} className="ico" /> <span className="side-label">{t('titul_scanner', 'Titul Skaner (OMR)')}</span>
              </NavLink>
              <NavLink to="/analytics" className={linkClass} onClick={close}>
                <BarChartIcon size={16} className="ico" /> <span className="side-label">{t('analytics', 'Tahlillar')}</span>
              </NavLink>
              <NavLink to="/import" className={linkClass} onClick={close}>
                <UploadIcon size={16} className="ico" /> <span className="side-label">CSV Import</span>
              </NavLink>
            </Section>
          )}

          {workspace === 'student' && (
            <Section title={t('main_menu', 'Asosiy Menyu')}>
              <NavLink to="/dashboard" end className={linkClass} onClick={close}>
                <LayoutDashboardIcon size={16} className="ico" /> <span className="side-label">{t('dashboard', 'Boshqaruv paneli')}</span>
              </NavLink>
              <NavLink to="/my-homework" className={linkClass} onClick={close}>
                <FileTextIcon size={16} className="ico" /> <span className="side-label">{t('my_homework_title', 'Mening vazifalarim')}</span>
              </NavLink>
              <NavLink to="/tests" className={testsLinkClass(pathname)} onClick={close}>
                <FileTextIcon size={16} className="ico" /> <span className="side-label">{t('cbt_tests', 'Testlar (CBT)')}</span>
              </NavLink>
              <NavLink to="/essays" className={linkClass} onClick={close}>
                <PenLineIcon size={16} className="ico" /> <span className="side-label">{t('ai_essay_studio', 'AI Esse Studiyasi')}</span>
              </NavLink>
              <NavLink to="/arena" className={linkClass} onClick={close}>
                <SwordsIcon size={16} className="ico" /> <span className="side-label">{t('arena_live_duel', '1v1 Arena (Jonli jang)')}</span>
              </NavLink>
              <NavLink to="/groups" className={linkClass} onClick={close}>
                <UsersIcon size={16} className="ico" /> <span className="side-label">{t('my_group_ranking', 'Guruhim va Reyting')}</span>
              </NavLink>
              <NavLink to="/results" className={linkClass} onClick={close}>
                <TrophyIcon size={16} className="ico" /> <span className="side-label">{t('results_analysis', 'Natijalar va Tahlil')}</span>
              </NavLink>
              <NavLink to="/tests/scan-omr" className={linkClass} onClick={close}>
                <CameraIcon size={16} className="ico" /> <span className="side-label">{t('titul_scanner', 'Titul Skaner (OMR)')}</span>
              </NavLink>
              {activeSubject === 'english' && (
                <NavLink to="/speaking" className={linkClass} onClick={close}>
                  <MicIcon size={16} className="ico" /> <span className="side-label">AI Speaking</span>
                </NavLink>
              )}
            </Section>
          )}

          {workspace === 'parent' && (
            <Section title={t('parent', 'Ota-ona')}>
              <NavLink to="/parent" className={linkClass} onClick={close}>
                <HomeIcon size={16} className="ico" /> <span className="side-label">{t('children', 'Farzandlarim')}</span>
              </NavLink>
            </Section>
          )}

          {workspace === 'student' && !sidebarCollapsed && <PlanBadge variant="card" onNavigate={close} />}
        </nav>

        <div className="side-user">
          <span className="avatar">{initialsOf(user?.full_name, user?.email)}</span>
          <span className="side-user-meta">
            <strong>{formatDisplayName(user?.full_name, user?.email) || t('user_default')}</strong>
            <small>{user?.role}</small>
          </span>
          <button className="btn ghost sm" onClick={onLogout} title={t('logout')} aria-label={t('logout')}>
            <LogOutIcon size={14} className="ico" />
          </button>
        </div>
      </aside>
      {open && <div className="overlay" onClick={close} aria-hidden="true" />}

      <div className="main">
        <Navbar
          streakData={visibleStreakData}
          onOpenProfile={() => setProfileDrawerOpen(true)}
          onOpenMenu={() => setNavDrawerOpen(true)}
          pageTitle={pageTitle}
          workspace={workspace}
          showSubjectSwitcher={showSubjectSwitcher}
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={toggleSidebar}
        />
        {showSubjectSwitcher && (
          <div className="tb-subject md:hidden flex items-center w-full bg-white/90 dark:bg-slate-950/90 border-b border-slate-200 dark:border-slate-800/60 backdrop-blur-md">
            <SubjectSwitcher variant="seg" />
          </div>
        )}
        <main id="main-content" className="content">
          <Outlet />
        </main>
      </div>

      <BottomNav workspace={workspace} onOpenProfile={() => setProfileDrawerOpen(true)} />
      <MobileNavDrawer
        isOpen={navDrawerOpen}
        onClose={() => setNavDrawerOpen(false)}
        workspace={workspace}
        availableWorkspaces={availableWorkspaces}
        onSelectWorkspace={selectWorkspace}
      />
      <MobileProfileDrawer
        isOpen={profileDrawerOpen}
        onClose={() => setProfileDrawerOpen(false)}
        onOpenMenu={() => {
          setProfileDrawerOpen(false);
          setNavDrawerOpen(true);
        }}
      />
    </div>
  );
}
