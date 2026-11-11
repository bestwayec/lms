import { useAuth as useBaseAuth } from '../auth/authState';
import type { AuthUser } from '../lib/api';

export function useAuth() {
  const ctx = useBaseAuth();
  return {
    ...ctx,
    updateUser: (partial: Partial<AuthUser>) => ctx.updateUserLocal(partial),
  };
}
