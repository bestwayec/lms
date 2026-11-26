/** Route title & role-workspace helpers (pure TS for Node tests + React shell). */

export type WorkspaceMode = 'admin' | 'teacher' | 'student' | 'parent';

export interface WorkspaceUserShape {
  role?: string;
  is_staff?: boolean;
  is_superuser?: boolean;
  is_platform_admin?: boolean;
}

const ROUTE_TITLES: ReadonlyArray<readonly [string, string, string]> = [
  ['/panel/tests/smart-create', 'x_smart_create', 'Smart Test Yaratish'],
  ['/panel/tests/new', 'panel_new_test', 'Yangi Test Yaratish'],
  ['/panel/tests', 'panel_test_control_center', 'Testlar Nazorati'],
  ['/panel/teachers', 'manage_teachers', "O'qituvchilarni Boshqarish"],
  ['/panel/branches', 'branches', 'Filiallar'],
  ['/panel/topics', 'essay_topics', 'Esse Mavzulari'],
  ['/panel/feedback', 'fbi_title', 'Fikr-mulohazalar'],
  ['/panel/tuition', 'tuition_title', "To'lov Cheklari"],
  ['/panel/users', 'users', 'Foydalanuvchilar'],
  ['/panel/groups', 'groups', 'Guruhlar'],
  ['/panel', 'tb_admin_panel', 'Admin Panel'],
  ['/enterprise', 'enterprise_title', "O'quv Markazlari"],
  ['/teacher/studio', 'studio_title', 'Test Studio'],
  ['/teacher/essays', 'teacher_queue', 'Esse Tekshiruvi'],
  ['/teacher/finance', 'tuition_title', "O'qituvchi Moliyasi"],
  ['/teacher/ai-converter', 'nav_converter', 'AI Test Konvertor'],
  ['/teacher', 'teacher_cabinet', "O'qituvchi Kabineti"],
  ['/tests/create', 'create_smart_test', 'Yangi Test Yaratish'],
  ['/tests/scan-omr', 'titul_scanner', 'Titul Skaner (OMR)'],
  ['/tests', 'tests', 'Testlar'],
  ['/take', 'tests', 'Test Topshirish'],
  ['/english-exam', 'tests', 'Imtihon'],
  ['/groups', 'groups', 'Guruhlar'],
  ['/join', 'join', "Guruhga Qo'shilish"],
  ['/my-homework', 'my_homework_title', 'Vazifalarim'],
  ['/essays', 'tb_title_essays', 'AI Esse Studiyasi'],
  ['/results', 'results_analysis', 'Natijalar va Tahlil'],
  ['/certificates', 'certificates', 'Sertifikatlar'],
  ['/arena', 'arena', '1v1 Arena'],
  ['/tournaments', 'tournaments', 'Turnirlar'],
  ['/games', 'games', "O'yinlar"],
  ['/analytics', 'analytics', 'Tahlillar'],
  ['/import', 'import_title', 'CSV Import'],
  ['/speaking', 'tb_title_speaking', 'AI Speaking'],
  ['/english', 'english_center_title', 'English Center'],
  ['/parent', 'parent', 'Ota-ona Nazorati'],
  ['/profile', 'tb_title_profile', 'Profil'],
  ['/subscribe', 'pay_plans_title', 'Obuna Rejalari'],
  ['/plans', 'pay_plans_title', 'Obuna Rejalari'],
  ['/my-subscription', 'pay_current_sub', 'Mening Obunam'],
  ['/dashboard', 'tb_title_home', 'Boshqaruv Paneli'],
  ['/tma', 'tma_title', 'GRANDEC Telegram Mini App'],
  ['/login', 'login', 'Tizimga kirish'],
  ['/register', 'register', "Ro'yxatdan o'tish"],
  ['/password-reset', 'forgot_password_title', 'Parolni tiklash'],
  ['/pricing', 'pay_plans_title', 'Tariflar'],
];

export function resolveRouteTitle(
  pathname: string,
  tr?: (key: string, fallback?: string) => string,
): string {
  const clean = (pathname || '/').replace(/\/+$/, '') || '/';
  if (clean === '/') return 'GRANDEC 2.0 — Milliy Sertifikat, IELTS/CEFR va BMBA Intellektual LMS';
  for (const [prefix, key, fallback] of ROUTE_TITLES) {
    if (clean === prefix || clean.startsWith(`${prefix}/`)) {
      const label = tr ? tr(key, fallback) : fallback;
      const resolved = label && label !== key ? label : fallback;
      return `${resolved} | GRANDEC 2.0`;
    }
  }
  return 'GRANDEC 2.0';
}

export function isAdminRole(user: WorkspaceUserShape | null | undefined): boolean {
  if (!user) return false;
  return Boolean(
    user.is_platform_admin ||
      user.is_superuser ||
      user.is_staff ||
      user.role === 'admin' ||
      user.role === 'superadmin',
  );
}

export function getAvailableWorkspaces(user: WorkspaceUserShape | null | undefined): WorkspaceMode[] {
  if (!user) return ['student'];
  const admin = isAdminRole(user);
  const teacher = admin || user.role === 'teacher' || user.role === 'center_admin';
  const parent = user.role === 'parent';
  const modes: WorkspaceMode[] = [];
  if (admin) modes.push('admin');
  if (teacher) modes.push('teacher');
  if (parent) modes.push('parent');
  if (!admin && user.role !== 'parent') modes.push('student');
  else if (admin) modes.push('student');
  return modes.length ? modes : ['student'];
}

export function getDefaultWorkspace(
  user: WorkspaceUserShape | null | undefined,
  pathname?: string,
): WorkspaceMode {
  if (!user) return 'student';
  const admin = isAdminRole(user);
  if (pathname) {
    if (pathname.startsWith('/panel') && admin) return 'admin';
    if (pathname.startsWith('/enterprise') && (admin || user.role === 'center_admin')) {
      return admin ? 'admin' : 'teacher';
    }
    if (pathname.startsWith('/teacher') && (admin || user.role === 'teacher' || user.role === 'center_admin')) {
      return 'teacher';
    }
  }
  if (admin) return 'admin';
  if (user.role === 'teacher' || user.role === 'center_admin') return 'teacher';
  if (user.role === 'parent') return 'parent';
  return 'student';
}

export function shouldShowSubjectSwitcher(workspace: WorkspaceMode, pathname: string): boolean {
  if (workspace === 'admin' || workspace === 'parent') return false;
  if (workspace === 'teacher') {
    if (pathname.startsWith('/tests/create') || pathname.startsWith('/tests/scan-omr')) {
      return false;
    }
    return (
      pathname.startsWith('/tests') ||
      pathname.startsWith('/essays') ||
      pathname.startsWith('/speaking')
    );
  }
  return !pathname.startsWith('/panel') && !pathname.startsWith('/enterprise');
}
