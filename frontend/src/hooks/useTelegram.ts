import { useEffect, useState } from 'react';
import { tg, initTelegramWebApp, type TelegramWebApp } from '../pages/tma/telegram';
import { hapticSelect, hapticImpact, hapticNotify } from '../lib/haptics';

export function useTelegram() {
  const [webApp, setWebApp] = useState<TelegramWebApp | null>(() => tg());
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    const wa = initTelegramWebApp();
    if (wa) {
      setWebApp(wa);
      setIsReady(true);
    }
  }, []);

  return {
    webApp,
    isReady,
    user: webApp?.initDataUnsafe?.user ?? null,
    initData: webApp?.initData ?? '',
    isTma: Boolean(webApp?.initData),
    hapticSelect,
    hapticImpact,
    hapticNotify,
    close: () => {
      try {
        webApp?.close();
      } catch {
        /* ignore */
      }
    },
    expand: () => {
      try {
        webApp?.expand();
      } catch {
        /* ignore */
      }
    },
  };
}

export default useTelegram;
