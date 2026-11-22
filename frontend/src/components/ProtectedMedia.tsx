import { useTranslation } from '../i18n/useTranslation';
import { useProtectedObjectUrl } from '../hooks/useProtectedObjectUrl';

interface ImageLinkProps {
  path: string;
  alt: string;
  size?: number;
}

/** Thumbnail of a private image that opens the full file in a new tab (blob URL, never a public URL). */
export function ProtectedImageLink({ path, alt, size = 44 }: ImageLinkProps) {
  const { t } = useTranslation();
  const state = useProtectedObjectUrl(path);
  const box = {
    width: size,
    height: size,
    borderRadius: 6,
    border: '1px solid var(--border)',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 11,
    color: 'var(--muted)',
    background: 'var(--card)',
  } as const;
  if (state.status === 'ready') {
    return (
      <a href={state.url} target="_blank" rel="noopener noreferrer" aria-label={t('file_open')}>
        <img src={state.url} alt={alt} style={{ ...box, objectFit: 'cover' }} />
      </a>
    );
  }
  if (state.status === 'error') {
    return <span role="img" aria-label={t('file_load_failed')} title={t('file_load_failed')} style={box}>!</span>;
  }
  return <span aria-busy="true" aria-label={t('file_loading')} style={box} />;
}

/** Player for a private recording; renders nothing when there is none. */
export function ProtectedAudio({ path }: { path: string | null | undefined }) {
  const { t } = useTranslation();
  const state = useProtectedObjectUrl(path);
  if (!path) return null;
  if (state.status === 'ready') return <audio src={state.url} controls style={{ width: '100%', borderRadius: 10 }} />;
  if (state.status === 'error') return <p role="alert" className="muted small">{t('file_load_failed')}</p>;
  return <p aria-busy="true" className="muted small">{t('file_loading')}</p>;
}
