import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { PaymentsApi } from './api';

export type CardStatus = 'loading' | 'ready' | 'login' | 'error';

export const DEFAULT_CARD_NUMBER = '4916 9903 6325 9166';
export const DEFAULT_CARD_NUMBER_RAW = '4916990363259166';
export const DEFAULT_CARD_HOLDER = "GRAND EDUCATION (KOMILJON RO'ZIYEV)";

export interface CardInfo {
  card_number: string;
  card_holder: string;
  starter_price: number;
  pro_price: number;
  premium_price: number;
}

const DEFAULT_CARD_INFO: CardInfo = {
  card_number: DEFAULT_CARD_NUMBER,
  card_holder: DEFAULT_CARD_HOLDER,
  starter_price: 7000,
  pro_price: 15000,
  premium_price: 27000,
};

/**
 * Payment card details with instant fallback to the official GRAND EDUCATION
 * card (4916 9903 6325 9166) so the card box never hangs on "Loading...".
 */
export function useCardInfo(enabled = true) {
  const { user } = useAuth();
  const [info, setInfo] = useState<CardInfo>(DEFAULT_CARD_INFO);
  const [status, setStatus] = useState<CardStatus>('ready');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    PaymentsApi.cardInfo()
      .then((d) => {
        if (cancelled) return;
        setInfo({
          card_number: d?.card_number?.trim() || DEFAULT_CARD_NUMBER,
          card_holder: d?.card_holder?.trim() || DEFAULT_CARD_HOLDER,
          starter_price: d?.starter_price || 7000,
          pro_price: d?.pro_price ?? d?.plans?.pro?.price ?? 15000,
          premium_price: d?.premium_price || 27000,
        });
        setStatus('ready');
      })
      .catch(() => {
        if (!cancelled) {
          setInfo(DEFAULT_CARD_INFO);
          setStatus('ready');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, user, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { info, status, reload };
}
