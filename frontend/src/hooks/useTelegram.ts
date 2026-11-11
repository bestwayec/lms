import { useSyncExternalStore } from 'react';
import { tg, initTelegramWebApp, type TelegramWebApp } from '../pages/tma/telegram';
import { hapticSelect, hapticImpact, hapticNotify } from '../lib/haptics';

type Snapshot = { webApp: TelegramWebApp | null; isReady: boolean };
const serverSnapshot: Snapshot = { webApp: null, isReady: false };
let snapshot: Snapshot = { webApp: tg(), isReady: false };
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  const webApp = initTelegramWebApp();
  if (webApp && (snapshot.webApp !== webApp || !snapshot.isReady)) {
    snapshot = { webApp, isReady: true };
    listeners.forEach((notify) => notify());
  }
  return () => { listeners.delete(listener); };
}

export function useTelegram() {
  const { webApp, isReady } = useSyncExternalStore(subscribe, () => snapshot, () => serverSnapshot);
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
      try { webApp?.close(); } catch { /* older clients */ }
    },
    expand: () => {
      try { webApp?.expand(); } catch { /* older clients */ }
    },
  };
}

export default useTelegram;
