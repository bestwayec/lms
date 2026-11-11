import { createContext, useContext } from 'react';

interface ToastContextValue {
  success: (msg: string) => void;
  error: (msg: string) => void;
  info: (msg: string) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    return {
      success: (msg: string) => {
        if (typeof window !== 'undefined') console.log('Toast [success]:', msg);
      },
      error: (msg: string) => {
        if (typeof window !== 'undefined') console.error('Toast [error]:', msg);
      },
      info: (msg: string) => {
        if (typeof window !== 'undefined') console.info('Toast [info]:', msg);
      },
    };
  }
  return ctx;
}
