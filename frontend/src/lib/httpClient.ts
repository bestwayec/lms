/** Pure HTTP/JSON response parsing and safe diagnostic error helpers. */

export interface ApiError extends Error {
  status: number;
  detail: string;
  code?: string;
  requestId?: string;
}

export type TranslateFn = (key: string) => string;

export function makeRequestId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    /* ignore */
  }
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function isJsonContentType(contentType: string): boolean {
  const ct = contentType.toLowerCase();
  return ct.includes('application/json') || ct.includes('+json');
}

export function parseErrorBody(body: unknown, fallback: string): string {
  if (typeof body === 'object' && body !== null) {
    const o = body as Record<string, unknown>;
    if (typeof o.detail === 'string' && o.detail) return o.detail;
    if (typeof o.message === 'string' && o.message) return o.message;
    if (typeof o.error === 'string' && o.error) return o.error;
    const parts: string[] = [];
    for (const [key, value] of Object.entries(o)) {
      if (Array.isArray(value)) {
        parts.push(key === 'non_field_errors' ? value.join(' ') : `${key}: ${value.join(' ')}`);
      } else if (typeof value === 'string') {
        parts.push(key === 'non_field_errors' ? value : `${key}: ${value}`);
      }
    }
    if (parts.length > 0) return parts.join(' ');
  }
  return fallback;
}

export function makeTranslatedApiError(
  status: number,
  key: string,
  tr: TranslateFn,
  requestId?: string,
): ApiError {
  const err = new Error(tr(key)) as ApiError;
  err.status = status;
  err.detail = err.message;
  err.requestId = requestId;
  return err;
}

export async function parseJsonSuccess<T>(
  res: Response,
  path: string,
  method: string,
  requestId: string,
  tr: TranslateFn,
): Promise<T> {
  if (res.status === 204 || res.status === 205) return undefined as T;
  const contentLength = res.headers.get('content-length');
  if (contentLength === '0') return undefined as T;
  const contentType = res.headers.get('content-type') || '';
  if (contentType && !isJsonContentType(contentType)) {
    console.warn('[api] unexpected non-JSON success response', {
      path,
      method,
      status: res.status,
      contentType,
      requestId,
    });
    throw makeTranslatedApiError(res.status || 502, 'error_invalid_server_response', tr, requestId);
  }
  const text = await res.text();
  if (!text.trim()) return undefined as T;
  const trimmed = text.trimStart();
  if (trimmed.startsWith('<')) {
    console.warn('[api] HTML body received where JSON was expected', {
      path,
      method,
      status: res.status,
      contentType,
      requestId,
    });
    throw makeTranslatedApiError(res.status || 502, 'error_invalid_server_response', tr, requestId);
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    console.warn('[api] malformed JSON success response', {
      path,
      method,
      status: res.status,
      contentType,
      requestId,
    });
    throw makeTranslatedApiError(res.status || 502, 'error_invalid_server_response', tr, requestId);
  }
}

export async function toApiError(
  res: Response,
  path: string,
  method: string,
  requestId: string,
  tr: TranslateFn,
): Promise<ApiError> {
  const ct = res.headers.get('content-type') || '';
  let ownCode = false;
  if ((res.status === 429 || res.status === 502 || res.status === 503 || res.status === 504) && (!ct || isJsonContentType(ct))) {
    try {
      const probe = (await res.clone().json()) as { code?: unknown } | null;
      ownCode = typeof probe?.code === 'string';
    } catch {
      ownCode = false;
    }
  }
  if (!ownCode && (res.status === 502 || res.status === 503 || res.status === 504)) {
    return makeTranslatedApiError(res.status, 'error_server_unavailable', tr, requestId);
  }
  if (!ownCode && res.status === 429) {
    return makeTranslatedApiError(429, 'error_too_many_requests', tr, requestId);
  }

  const fallbackDetail =
    res.status === 403
      ? tr('error_forbidden')
      : res.status === 409
      ? tr('error_conflict')
      : `Request failed (${res.status})`;
  let detail = fallbackDetail;
  let code: string | undefined;

  if (!ct || isJsonContentType(ct)) {
    try {
      const text = await res.text();
      if (text.trim() && !text.trimStart().startsWith('<')) {
        const body = JSON.parse(text) as Record<string, unknown> | null;
        if (typeof body === 'object' && body !== null) {
          if (typeof body.code === 'string') code = body.code;
          detail = parseErrorBody(body, fallbackDetail);
        }
      }
    } catch {
      /* keep safe fallback — never surface HTML */
    }
  } else {
    console.warn('[api] non-JSON error response suppressed', {
      path,
      method,
      status: res.status,
      contentType: ct,
      requestId,
    });
  }

  if (res.status >= 500 && detail === fallbackDetail) {
    return makeTranslatedApiError(res.status, 'error_server_failed', tr, requestId);
  }

  const err = new Error(detail) as ApiError;
  err.status = res.status;
  err.detail = detail;
  err.code = code;
  err.requestId = requestId;
  return err;
}
