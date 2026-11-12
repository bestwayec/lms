import { Navigate } from 'react-router-dom';
import { useAuth } from '../auth/authState';
import { isPlatformAdmin } from '../lib/api';
import Dashboard from './Dashboard';
import TeacherDashboard from './TeacherDashboard';

export default function DashboardRouter() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex flex-col items-center justify-center min-h-[50vh] py-16 px-4"
      >
        <div className="relative flex items-center justify-center w-12 h-12 mb-3">
          <div className="absolute inset-0 rounded-full bg-amber-500/20 blur-xl animate-pulse" />
          <div className="w-10 h-10 rounded-full border-2 border-amber-500/20 border-t-amber-500 animate-spin" />
        </div>
        <span className="text-xs font-semibold text-slate-400">Yuklanmoqda...</span>
      </div>
    );
  }

  // 1. Admins & Center Admins route directly to the Admin Control Panel
  if (user?.role === 'center_admin' && !isPlatformAdmin(user)) return <Navigate to="/enterprise" replace />;
  if (isPlatformAdmin(user)) {
    return <Navigate to="/panel" replace />;
  }

  // 2. Teachers get the dedicated Teacher Dashboard (O'qituvchi Kabineti)
  if (user?.role === 'teacher') {
    return <TeacherDashboard />;
  }

  // 3. Students get the standard Student Dashboard
  return <Dashboard />;
}
