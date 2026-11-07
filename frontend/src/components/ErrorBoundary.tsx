import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useLang } from '../i18n/LangContext';

interface Props {
  children: ReactNode;
  /** i18n key for the heading (defaults to `error_boundary_title`). */
  titleKey?: string;
  /** Where the secondary button leads (defaults to the test list). */
  backTo?: string;
  /** i18n key for the secondary button (defaults to `error_boundary_back`). */
  backKey?: string;
}

interface State {
  error: Error | null;
}

const CHUNK_RELOAD_KEY = 'grandec:chunk-reload-at';

/**
 * After a deploy, a tab that was opened before it still references the old
 * hashed chunks; the lazy import then rejects and the page would show this
 * boundary. Reloading once fetches the new index.html and fixes it, so do
 * that automatically — but at most once per 30s to never loop.
 */
function isChunkLoadError(error: Error): boolean {
  const msg = `${error?.name ?? ''} ${error?.message ?? ''}`;
  return /ChunkLoadError|Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(
    msg,
  );
}

function tryChunkReload(): boolean {
  try {
    const last = Number(sessionStorage.getItem(CHUNK_RELOAD_KEY) || 0);
    if (Date.now() - last < 30_000) return false;
    sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()));
  } catch {
    return false;
  }
  window.location.reload();
  return true;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    if (isChunkLoadError(error) && tryChunkReload()) return;
    console.error('ErrorBoundary caught an unhandled error:', error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <ErrorFallback
          error={this.state.error}
          titleKey={this.props.titleKey}
          backTo={this.props.backTo}
          backKey={this.props.backKey}
        />
      );
    }
    return this.props.children;
  }
}

/** Class components can't use hooks, so the translated view lives here. */
function ErrorFallback({
  error,
  titleKey,
  backTo = '/tests',
  backKey = 'error_boundary_back',
}: {
  error: Error;
  titleKey?: string;
  backTo?: string;
  backKey?: string;
}) {
  const { t } = useLang();
  return (
    <div className="error-boundary" role="alert">
      <div className="card error-boundary-card">
        <div className="error-boundary-icon" aria-hidden="true">⚠️</div>
        <h2>{t(titleKey || 'error_boundary_title')}</h2>
        <p className="muted">{t('error_boundary_message')}</p>
        {error?.message && <pre className="error-boundary-detail">{error.message}</pre>}
        <div className="error-boundary-actions">
          <button type="button" className="btn primary" onClick={() => window.location.reload()}>
            {t('error_boundary_reload')}
          </button>
          {/* Full navigation drops any corrupted in-memory state. */}
          <button type="button" className="btn" onClick={() => window.location.assign(backTo)}>
            {t(backKey)}
          </button>
        </div>
      </div>
    </div>
  );
}
