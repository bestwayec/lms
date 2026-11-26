import { useCallback, useEffect, useRef, useState } from 'react';

export interface SavePayload {
  question_id: number;
  choice_ids?: number[];
  text_answer?: string;
  written_text?: string;
  revision?: number;
  session_token?: string;
  annotations?: Record<string, unknown>;
}

export type SaveState =
  | 'unsaved'
  | 'saving'
  | 'saved'
  | 'offline'
  | 'retrying'
  | 'conflict'
  | 'submitted';

export interface AnswerQueueOptions {
  userId?: number | string;
  initialRevision?: number;
  initialSessionToken?: string;
}

const readQueue = (key: string): Record<number, SavePayload> => {
  try {
    return JSON.parse(localStorage.getItem(key) || '{}') as Record<number, SavePayload>;
  } catch {
    return {};
  }
};

/**
 * Answers go to the server with monotonic per-question revisions and an optional
 * session lock token. Pending writes survive offline drops and page reloads in
 * user+attempt scoped localStorage keys; 409 conflicts transition cleanly into
 * `conflict` so the user can inspect or take over the session without silent overwrite.
 */
export function useAnswerQueue(
  attemptId: string,
  send: (payload: SavePayload) => Promise<unknown>,
  options: AnswerQueueOptions = {},
) {
  const userScope = options.userId != null ? `${options.userId}:` : '';
  const key = `cd-queue:${userScope}${attemptId}`;
  const backupKey = `grandec_attempt_${userScope}${attemptId}_answers`;
  const [initial] = useState(() => {
    const q = readQueue(key);
    if (Object.keys(q).length) return q;
    const legacy = readQueue(`cd-queue:${attemptId}`);
    if (Object.keys(legacy).length) return legacy;
    return readQueue(backupKey);
  });
  const queue = useRef<Record<number, SavePayload>>({ ...initial });
  const revRef = useRef<number>(options.initialRevision || 0);
  const sessionTokenRef = useRef<string>(options.initialSessionToken || '');
  const [state, setState] = useState<SaveState>(Object.keys(initial).length ? 'unsaved' : 'saved');
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  const [justRestored, setJustRestored] = useState(false);
  const flushing = useRef(false);

  const persist = useCallback(() => {
    try {
      if (Object.keys(queue.current).length) {
        const serialized = JSON.stringify(queue.current);
        localStorage.setItem(key, serialized);
        localStorage.setItem(backupKey, serialized);
      } else {
        localStorage.removeItem(key);
        localStorage.removeItem(backupKey);
        localStorage.removeItem(`cd-queue:${attemptId}`);
      }
    } catch {
      /* storage unavailable */
    }
  }, [key, backupKey, attemptId]);

  const setSessionToken = useCallback((token: string) => {
    sessionTokenRef.current = token;
    setState((prev) => (prev === 'conflict' ? (Object.keys(queue.current).length ? 'retrying' : 'saved') : prev));
  }, []);

  const markSubmitted = useCallback(() => {
    queue.current = {};
    persist();
    setState('submitted');
  }, [persist]);

  const flush = useCallback(async (): Promise<boolean> => {
    if (flushing.current) return Object.keys(queue.current).length === 0;
    flushing.current = true;
    try {
      for (;;) {
        const entry = Object.entries(queue.current)[0];
        if (!entry) break;
        const [qid, payload] = entry;
        setState(navigator.onLine ? 'saving' : 'offline');
        const outgoing: SavePayload = {
          ...payload,
          ...(sessionTokenRef.current ? { session_token: sessionTokenRef.current } : {}),
        };
        try {
          await send(outgoing);
        } catch (err: unknown) {
          const apiErr = err as { status?: number; code?: string };
          if (apiErr?.status === 409 || apiErr?.code === 'SESSION_TAKEN_OVER' || apiErr?.code === 'STALE_REVISION') {
            setState('conflict');
            return false;
          }
          setState(typeof navigator !== 'undefined' && navigator.onLine ? 'retrying' : 'offline');
          return false;
        }
        if (queue.current[Number(qid)] === payload) delete queue.current[Number(qid)];
        persist();
      }
      setState((prev) => (prev === 'submitted' ? 'submitted' : 'saved'));
      return true;
    } finally {
      flushing.current = false;
    }
  }, [send, persist]);

  const enqueue = useCallback(
    (payload: SavePayload) => {
      revRef.current += 1;
      const versioned: SavePayload = { ...payload, revision: payload.revision ?? revRef.current };
      queue.current[payload.question_id] = versioned;
      persist();
      setState('unsaved');
      void flush();
    },
    [flush, persist],
  );

  useEffect(() => {
    const goOnline = () => {
      setOnline(true);
      setJustRestored(true);
      void flush().then((ok) => ok && window.setTimeout(() => setJustRestored(false), 3000));
    };
    const goOffline = () => {
      setOnline(false);
      setState('offline');
    };
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    const timer = window.setInterval(() => {
      if (Object.keys(queue.current).length && state !== 'conflict' && state !== 'submitted') {
        void flush();
      }
    }, 6000);
    if (Object.keys(queue.current).length) void flush();
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
      window.clearInterval(timer);
    };
  }, [flush, state]);

  return {
    enqueue,
    flush,
    state,
    online,
    justRestored,
    initial,
    setSessionToken,
    markSubmitted,
    pending: () => Object.keys(queue.current).length,
  };
}
