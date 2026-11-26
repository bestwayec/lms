import { useEffect, useState } from 'react';
import { ThemeContext, type Theme, type ResolvedTheme } from './themeState';
import type { ReactNode } from 'react';

const THEME_KEY = 'theme_v2';

function getStoredTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY) || localStorage.getItem('theme');
    if (saved === 'dark' || saved === 'light' || saved === 'system') {
      if (!localStorage.getItem(THEME_KEY)) {
        localStorage.setItem(THEME_KEY, saved);
      }
      return saved;
    }
  } catch {
    /* ignore */
  }
  return 'light';
}

function getSystemDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getStoredTheme);
  const [systemDark, setSystemDark] = useState<boolean>(getSystemDark);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const resolvedTheme: ResolvedTheme =
    theme === 'dark' ? 'dark' : theme === 'system' && systemDark ? 'dark' : 'light';

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', resolvedTheme);
    root.classList.remove('light', 'dark');
    root.classList.add(resolvedTheme);
    root.style.colorScheme = resolvedTheme;
    const metaTheme = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    if (metaTheme) {
      metaTheme.content = resolvedTheme === 'dark' ? '#090D16' : '#F8FAFC';
    }
  }, [resolvedTheme]);

  const setTheme = (next: Theme) => {
    setThemeState(next);
    try {
      localStorage.setItem(THEME_KEY, next);
      localStorage.setItem('theme', next);
    } catch {
      /* ignore */
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
