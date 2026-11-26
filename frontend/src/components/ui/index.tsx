import {
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';

/* ── Button ─────────────────────────────────────────────────────────────── */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'secondary' | 'danger' | 'ghost' | 'telegram';
  size?: 'sm' | 'md' | 'lg';
  block?: boolean;
  loading?: boolean;
}

export function Button({
  variant = 'default',
  size = 'md',
  block = false,
  loading = false,
  className = '',
  disabled,
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  const classes = [
    'g-btn',
    `g-btn--${variant}`,
    `g-btn--${size}`,
    block ? 'g-btn--block' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {children}
    </button>
  );
}

/* ── Form Controls ──────────────────────────────────────────────────────── */
export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export function Input({ label, hint, error, className = '', id, ...rest }: InputProps) {
  const autoId = useId();
  const fieldId = id || autoId;
  return (
    <div className="g-field">
      {label && <label className="g-label" htmlFor={fieldId}>{label}</label>}
      <input
        id={fieldId}
        className={`g-input ${error ? 'is-invalid' : ''} ${className}`.trim()}
        aria-invalid={Boolean(error) || undefined}
        {...rest}
      />
      {error ? (
        <span className="g-field-error" role="alert">{error}</span>
      ) : hint ? (
        <span className="g-field-hint">{hint}</span>
      ) : null}
    </div>
  );
}

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export function Textarea({ label, hint, error, className = '', id, ...rest }: TextareaProps) {
  const autoId = useId();
  const fieldId = id || autoId;
  return (
    <div className="g-field">
      {label && <label className="g-label" htmlFor={fieldId}>{label}</label>}
      <textarea
        id={fieldId}
        className={`g-textarea ${error ? 'is-invalid' : ''} ${className}`.trim()}
        aria-invalid={Boolean(error) || undefined}
        {...rest}
      />
      {error ? (
        <span className="g-field-error" role="alert">{error}</span>
      ) : hint ? (
        <span className="g-field-hint">{hint}</span>
      ) : null}
    </div>
  );
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export function Select({ label, hint, error, className = '', id, children, ...rest }: SelectProps) {
  const autoId = useId();
  const fieldId = id || autoId;
  return (
    <div className="g-field">
      {label && <label className="g-label" htmlFor={fieldId}>{label}</label>}
      <select
        id={fieldId}
        className={`g-select ${error ? 'is-invalid' : ''} ${className}`.trim()}
        aria-invalid={Boolean(error) || undefined}
        {...rest}
      >
        {children}
      </select>
      {error ? (
        <span className="g-field-error" role="alert">{error}</span>
      ) : hint ? (
        <span className="g-field-hint">{hint}</span>
      ) : null}
    </div>
  );
}

export interface ChoiceControlProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: ReactNode;
}

export function Checkbox({ label, className = '', id, ...rest }: ChoiceControlProps) {
  const autoId = useId();
  const fieldId = id || autoId;
  return (
    <label className={`g-choice ${className}`.trim()} htmlFor={fieldId}>
      <input id={fieldId} type="checkbox" className="g-checkbox" {...rest} />
      <span>{label}</span>
    </label>
  );
}

export function Radio({ label, className = '', id, ...rest }: ChoiceControlProps) {
  const autoId = useId();
  const fieldId = id || autoId;
  return (
    <label className={`g-choice ${className}`.trim()} htmlFor={fieldId}>
      <input id={fieldId} type="radio" className="g-radio" {...rest} />
      <span>{label}</span>
    </label>
  );
}

/* ── Surface & Status ───────────────────────────────────────────────────── */
export function Badge({
  tone = 'neutral',
  className = '',
  children,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & {
  tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'telegram';
}) {
  return (
    <span className={`g-badge g-badge--${tone} ${className}`.trim()} {...rest}>
      {children}
    </span>
  );
}

export function Card({
  elevated = false,
  className = '',
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { elevated?: boolean }) {
  return (
    <div className={`g-card ${elevated ? 'g-card--elevated' : ''} ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}

export function Alert({
  tone = 'info',
  title,
  onClose,
  className = '',
  children,
}: {
  tone?: 'info' | 'success' | 'warning' | 'danger';
  title?: ReactNode;
  onClose?: () => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={`g-alert g-alert--${tone} ${className}`.trim()}
      role={tone === 'danger' ? 'alert' : 'status'}
    >
      <div className="g-alert__body">
        {title && <div className="g-alert__title">{title}</div>}
        <div className="g-alert__text">{children}</div>
      </div>
      {onClose && (
        <button type="button" className="g-icon-btn" onClick={onClose} aria-label="Yopish">
          ✕
        </button>
      )}
    </div>
  );
}

export function ToastNotice({
  tone = 'info',
  children,
  onClose,
}: {
  tone?: 'info' | 'success' | 'warning' | 'danger';
  children: ReactNode;
  onClose?: () => void;
}) {
  return (
    <div className={`toast toast--${tone === 'danger' ? 'error' : tone}`} role="status">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <span>{children}</span>
        {onClose && (
          <button type="button" className="g-icon-btn" onClick={onClose} aria-label="Yopish">
            ✕
          </button>
        )}
      </div>
    </div>
  );
}

/* ── Modal & Confirmation Dialog ────────────────────────────────────────── */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  maxWidth = 580,
  footer,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  subtitle?: ReactNode;
  maxWidth?: number;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const prevFocus = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialogRef.current?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = prevOverflow;
      document.removeEventListener('keydown', onKeyDown);
      prevFocus?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="g-modal-backdrop" onClick={onClose}>
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        className="g-modal"
        style={{ maxWidth }}
        onClick={(e) => e.stopPropagation()}
      >
        {(title || subtitle) && (
          <div className="g-modal__head">
            <div style={{ minWidth: 0 }}>
              {title && (
                <h2 id={titleId} className="g-modal__title">
                  {title}
                </h2>
              )}
              {subtitle && <p className="g-modal__sub">{subtitle}</p>}
            </div>
            <button type="button" className="g-icon-btn" onClick={onClose} aria-label="Yopish">
              ✕
            </button>
          </div>
        )}
        <div className="g-modal__body">{children}</div>
        {footer && <div className="g-modal__foot">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Tasdiqlash',
  cancelLabel = 'Bekor qilish',
  danger = false,
  loading = false,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: ReactNode;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  loading?: boolean;
}) {
  return (
    <Modal
      open={open}
      onClose={loading ? () => undefined : onClose}
      title={title}
      maxWidth={460}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant={danger ? 'danger' : 'primary'}
            onClick={onConfirm}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="g-confirm-msg">{message}</div>
    </Modal>
  );
}

/* ── Dropdown / Overflow Menu ───────────────────────────────────────────── */
export interface DropdownItem {
  id: string;
  label: ReactNode;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

export function Dropdown({
  trigger,
  items,
  align = 'right',
}: {
  trigger: ReactNode;
  items: DropdownItem[];
  align?: 'left' | 'right';
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={wrapRef} className="g-dropdown">
      <div
        role="button"
        tabIndex={0}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpen((o) => !o);
          }
        }}
      >
        {trigger}
      </div>
      {open && (
        <div
          role="menu"
          className={`g-dropdown__menu ${align === 'left' ? 'is-left' : 'is-right'}`}
        >
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              className={`g-dropdown__item ${item.danger ? 'is-danger' : ''}`}
              onClick={() => {
                setOpen(false);
                item.onClick();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Tabs, Table, Pagination, Tooltip, Skeleton, Empty & Error States ──── */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  className = '',
}: {
  items: { id: T; label: ReactNode; count?: number }[];
  value: T;
  onChange: (next: T) => void;
  className?: string;
}) {
  return (
    <div className={`g-tabs ${className}`.trim()} role="tablist">
      {items.map((it) => {
        const active = it.id === value;
        return (
          <button
            key={it.id}
            type="button"
            role="tab"
            aria-selected={active}
            className={`g-tab ${active ? 'is-active' : ''}`}
            onClick={() => onChange(it.id)}
          >
            <span>{it.label}</span>
            {typeof it.count === 'number' && <span className="g-tab__count">{it.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function Table({
  className = '',
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`table-wrap g-table-wrap ${className}`.trim()}>
      <table className="data g-table">{children}</table>
    </div>
  );
}

export function Pagination({
  page,
  totalPages,
  totalCount,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  totalCount?: number;
  onPageChange: (nextPage: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <div className="g-pagination">
      <div className="g-pagination__meta">
        {typeof totalCount === 'number' ? `Jami: ${totalCount} | ` : ''}
        Sahifa {page} / {totalPages}
      </div>
      <div className="g-pagination__actions">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPageChange(Math.max(1, page - 1))}>
          ← Oldingi
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={page >= totalPages}
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
        >
          Keyingi →
        </Button>
      </div>
    </div>
  );
}

export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  return (
    <span className="g-tooltip" title={text} aria-label={text}>
      {children}
    </span>
  );
}

export function Skeleton({ height = 16, width = '100%' }: { height?: number; width?: string | number }) {
  return <div className="ui-skel" style={{ height, width }} aria-hidden="true" />;
}

export function EmptyState({
  icon = '✨',
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="ui-state">
      <span className="ic-chip">{icon}</span>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({
  title = 'Xatolik yuz berdi',
  message,
  onRetry,
  retryLabel = 'Qayta urinish',
}: {
  title?: ReactNode;
  message: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div className="ui-state g-error-state" role="alert">
      <span className="ic-chip ic-chip--danger">⚠️</span>
      <h3>{title}</h3>
      <p>{message}</p>
      {onRetry && (
        <Button variant="primary" onClick={onRetry}>
          {retryLabel}
        </Button>
      )}
    </div>
  );
}
