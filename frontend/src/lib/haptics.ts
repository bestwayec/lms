/**
 * Telegram Mini App Haptic Feedback utility with web vibrator fallback.
 */

export type HapticImpactStyle = 'light' | 'medium' | 'heavy' | 'rigid' | 'soft';
export type HapticNotificationType = 'error' | 'success' | 'warning';

/**
 * Triggers Telegram selection change haptic feedback (very light click).
 */
export function hapticSelect(): void {
  try {
    const wa = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;
    if (wa?.HapticFeedback && typeof wa.HapticFeedback.selectionChanged === 'function') {
      wa.HapticFeedback.selectionChanged();
    } else if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
      navigator.vibrate(10);
    }
  } catch {
    /* ignore fallback on unsupported platforms */
  }
}

/**
 * Triggers Telegram impact haptic feedback (light, medium, heavy, rigid, soft).
 */
export function hapticImpact(style: HapticImpactStyle = 'light'): void {
  try {
    const wa = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;
    if (wa?.HapticFeedback && typeof wa.HapticFeedback.impactOccurred === 'function') {
      wa.HapticFeedback.impactOccurred(style as 'light' | 'medium' | 'heavy');
    } else if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
      navigator.vibrate(style === 'heavy' ? 35 : style === 'medium' ? 22 : 12);
    }
  } catch {
    /* ignore */
  }
}

/**
 * Triggers Telegram notification haptic feedback (success, warning, error).
 */
export function hapticNotify(type: HapticNotificationType = 'success'): void {
  try {
    const wa = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;
    if (wa?.HapticFeedback && typeof wa.HapticFeedback.notificationOccurred === 'function') {
      wa.HapticFeedback.notificationOccurred(type);
    } else if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
      navigator.vibrate(type === 'error' ? [40, 40, 40] : type === 'warning' ? [30, 30] : [15, 30]);
    }
  } catch {
    /* ignore */
  }
}
