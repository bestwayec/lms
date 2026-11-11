import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { api, getTokens } from '../lib/api';
import { Ctx, readStoredLang, storeLang, translate, type AppLang } from './LangContext';

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<AppLang>(readStoredLang);

  const t = useCallback(
    (key: string, fallback?: string) => translate(key, lang, fallback),
    [lang],
  );

  // Update document.documentElement.lang when language changes
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback(
    (next: AppLang) => {
      setLangState(next);
      storeLang(next);
      // Sync to profile so backend emails / locale views honor the choice.
      if (!getTokens().access && !getTokens().refresh) return;
      void api('/api/auth/me/', {
        method: 'PATCH',
        body: JSON.stringify({ language: next }),
      }).catch(() => undefined);
    },
    [],
  );

  return <Ctx.Provider value={{ t, lang, setLang }}>{children}</Ctx.Provider>;
}

