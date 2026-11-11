import { createContext, useContext } from 'react';
import type { AuthUser, TokenPair } from '../lib/api';

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  isAuthModalOpen: boolean;
  authModalMode: 'login' | 'register';
  openAuthModal: (mode?: 'login' | 'register') => void;
  closeAuthModal: () => void;
  login: (email: string, password: string) => Promise<AuthUser>;
  loginWithTokens: (tokens: TokenPair, rawUser?: Record<string, unknown>) => Promise<AuthUser>;
  loginWithTelegram: (tokens: TokenPair, rawUser: Record<string, unknown>) => AuthUser;
  loginWithGoogle: (credential: string) => Promise<AuthUser>;
  register: (payload: {
    email: string;
    password: string;
    password_confirm: string;
    first_name: string;
    last_name: string;
    role?: string;
  }) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<AuthUser | null>;
  updateUserLocal: (partial: Partial<AuthUser>) => void;
}

export const Ctx = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
