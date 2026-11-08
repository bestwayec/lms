import { useEffect, useRef, useState } from 'react';
import { Check, Copy, Send, X } from 'lucide-react';
import { useLang } from '../../i18n/LangContext';
import { api } from '../../lib/api';
import { StudioApi, type StudioAssignment, type StudioLinks } from '../../lib/studio';

interface Group {
  id: number;
  name: string;
  student_count?: number;
}

interface Props {
  testId: number;
  testTitle: string;
  links: StudioLinks;
  assignments: StudioAssignment[];
  onClose: () => void;
  onAssigned?: (a: StudioAssignment) => void;
}

/** Local "YYYY-MM-DDTHH:mm" for <input type="datetime-local">. */
function localInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function CopyField({ label, value }: { label: string; value: string }) {
  const { t } = useLang();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked: the value stays selectable */
    }
  };
  return (
    <div className="studio-copy">
      <span className="studio-copy__label">{label}</span>
      <div className="studio-copy__row">
        <code className="studio-copy__value">{value}</code>
        <button type="button" className="btn sm" onClick={() => void copy()} aria-label={`${t('studio_copy')}: ${label}`}>
          {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}{' '}
          {copied ? t('studio_copied') : t('studio_copy')}
        </button>
      </div>
    </div>
  );
}

/** One-click assignment of a published test to a group, plus the share links. */
export default function AssignDialog({ testId, testTitle, links, assignments, onClose, onAssigned }: Props) {
  const { t } = useLang();
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [groupId, setGroupId] = useState<number | ''>('');
  const [due, setDue] = useState(() => {
    const d = new Date(Date.now() + 7 * 86_400_000);
    d.setHours(23, 59, 0, 0);
    return localInput(d);
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [list, setList] = useState<StudioAssignment[]>(assignments);
  const [current, setCurrent] = useState<StudioLinks>(links);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .get<Group[]>('/api/v1/school/groups/')
      .then((g) => {
        const arr = Array.isArray(g) ? g : [];
        setGroups(arr);
        if (arr.length) setGroupId((v) => (v === '' ? arr[0].id : v));
      })
      .catch(() => setGroups([]));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    dialogRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const assign = async () => {
    if (groupId === '') return;
    setBusy(true);
    setErr(null);
    try {
      const res = await StudioApi.assign(testId, Number(groupId), new Date(due).toISOString());
      setList((l) => [...l.filter((a) => a.group_id !== res.assignment.group_id), res.assignment]);
      setCurrent({ join_code: res.join_code, access_pin: res.access_pin, tma_link: res.tma_link, web_path: res.web_path });
      onAssigned?.(res.assignment);
    } catch (e) {
      const code = (e as { code?: string }).code;
      setErr(code ? t(`studio_err_${code}`, e instanceof Error ? e.message : undefined) : t('err_retry_js'));
    } finally {
      setBusy(false);
    }
  };

  const webLink = `${window.location.origin}${current.web_path}`;

  return (
    <div className="studio-modal" role="presentation" onClick={onClose}>
      <div
        ref={dialogRef}
        className="studio-modal__card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="studio-assign-title"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="studio-modal__head">
          <div>
            <h2 id="studio-assign-title">{t('studio_assign_title')}</h2>
            <p className="muted small">{testTitle}</p>
          </div>
          <button type="button" className="studio-icon" onClick={onClose} aria-label={t('close')}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        {groups === null ? (
          <p className="muted">{t('loading')}</p>
        ) : groups.length === 0 ? (
          <p className="muted">{t('studio_no_groups')}</p>
        ) : (
          <div className="studio-assign">
            <label className="studio-field">
              <span>{t('studio_group')}</span>
              <select value={groupId} onChange={(e) => setGroupId(Number(e.target.value))}>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                    {g.student_count != null ? ` · ${t('studio_students_n').replace('{n}', String(g.student_count))}` : ''}
                  </option>
                ))}
              </select>
            </label>
            <label className="studio-field">
              <span>{t('studio_deadline')}</span>
              <input type="datetime-local" value={due} min={localInput(new Date())} onChange={(e) => setDue(e.target.value)} />
            </label>
            <button type="button" className="btn primary" onClick={() => void assign()} disabled={busy || groupId === '' || !due}>
              <Send size={16} aria-hidden="true" /> {busy ? t('studio_assigning') : t('studio_assign_btn')}
            </button>
          </div>
        )}
        {err && (
          <p className="studio-err-text" role="alert">
            {err}
          </p>
        )}

        {list.length > 0 && (
          <ul className="studio-assigned">
            {list.map((a) => (
              <li key={a.id}>
                <strong>{a.group_name}</strong>
                <span className="muted small">
                  {t('studio_due_at').replace('{date}', new Date(a.due_at).toLocaleString())} ·{' '}
                  {t('studio_students_n').replace('{n}', String(a.student_count))}
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="studio-share">
          {current.join_code && <CopyField label={t('studio_join_code')} value={current.join_code} />}
          {current.access_pin && <CopyField label={t('studio_pin')} value={current.access_pin} />}
          <CopyField label={t('studio_tma_link')} value={current.tma_link} />
          <CopyField label={t('studio_web_link')} value={webLink} />
          <a className="btn sm" href={current.tma_link} target="_blank" rel="noreferrer">
            {t('studio_open_telegram')}
          </a>
        </div>
      </div>
    </div>
  );
}
