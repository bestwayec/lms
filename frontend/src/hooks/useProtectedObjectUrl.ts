import { useEffect, useState } from 'react';
import { apiBlob } from '../lib/api';

export type ProtectedUrlState =
  | { status: 'idle'; url: null }
  | { status: 'loading'; url: null }
  | { status: 'ready'; url: string }
  | { status: 'error'; url: null; httpStatus: number };

interface Settled {
  path: string;
  url: string | null;
  httpStatus: number;
}

/**
 * Loads a private file through the authenticated API and exposes it as a revocable
 * blob: URL. The state is derived from the path that was actually settled, so
 * switching paths never shows the previous file and no setState runs in the effect body.
 */
export function useProtectedObjectUrl(path: string | null | undefined): ProtectedUrlState {
  const [settled, setSettled] = useState<Settled | null>(null);

  useEffect(() => {
    if (!path) return undefined;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    apiBlob(path, { signal: controller.signal })
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setSettled({ path, url: objectUrl, httpStatus: 200 });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const httpStatus = typeof (err as { status?: unknown })?.status === 'number' ? (err as { status: number }).status : 0;
        setSettled({ path, url: null, httpStatus });
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (!path) return { status: 'idle', url: null };
  if (!settled || settled.path !== path) return { status: 'loading', url: null };
  if (settled.url) return { status: 'ready', url: settled.url };
  return { status: 'error', url: null, httpStatus: settled.httpStatus };
}
