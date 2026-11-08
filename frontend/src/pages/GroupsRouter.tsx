import { Navigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { canTeach, isPlatformAdmin } from '../lib/api';
import Groups from './Groups';
import JoinGroup from './JoinGroup';

/**
 * Universal Groups Router:
 * - Teachers, Center Admins, and Platform Admins get the Teacher Group Management Studio (`Groups.tsx`).
 * - Students who already belong to a group get routed to their interactive group dashboard (`StudentGroupDetail.tsx`).
 * - Students not in a group yet get the Join Group / Branch Catalog portal (`JoinGroup.tsx`).
 */
export default function GroupsRouter() {
  const { user, loading } = useAuth();

  if (loading) {
    return <p className="route-loading" role="status">Yuklanmoqda…</p>;
  }

  // Staff and Teachers get full group management hub
  if (canTeach(user) || isPlatformAdmin(user) || user?.role === 'center_admin') {
    return <Groups />;
  }

  // Student already enrolled in a group -> forward to interactive group view
  if (user?.primary_group_id) {
    return <Navigate to={`/groups/${user.primary_group_id}`} replace />;
  }

  // Student not enrolled yet -> prompt to join via code or browse center branches
  return <JoinGroup />;
}
