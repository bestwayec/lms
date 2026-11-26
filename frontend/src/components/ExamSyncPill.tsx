import { RefreshCw } from 'lucide-react';
import type { SaveState } from '../lib/useAnswerQueue';

const STATE_STYLES: Record<SaveState, { label: string; cls: string }> = {
  unsaved: {
    label: 'Unsaved',
    cls: 'bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700',
  },
  saving: {
    label: 'Saving...',
    cls: 'bg-amber-50 text-amber-700 border-amber-300 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-700',
  },
  saved: {
    label: 'Saved',
    cls: 'bg-emerald-50 text-emerald-700 border-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-700',
  },
  offline: {
    label: 'Offline',
    cls: 'bg-slate-200 text-slate-800 border-slate-400 dark:bg-slate-800 dark:text-slate-200 dark:border-slate-600',
  },
  retrying: {
    label: 'Retrying...',
    cls: 'bg-orange-50 text-orange-700 border-orange-300 dark:bg-orange-950/40 dark:text-orange-300 dark:border-orange-700',
  },
  conflict: {
    label: 'Conflict',
    cls: 'bg-rose-50 text-rose-700 border-rose-400 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-700',
  },
  submitted: {
    label: 'Submitted',
    cls: 'bg-indigo-50 text-indigo-700 border-indigo-300 dark:bg-indigo-950/40 dark:text-indigo-300 dark:border-indigo-700',
  },
};

export default function ExamSyncPill({
  state,
  labelOverride,
  onTakeover,
}: {
  state: SaveState;
  labelOverride?: string;
  onTakeover?: () => void;
}) {
  const meta = STATE_STYLES[state] || STATE_STYLES.saved;
  return (
    <div className="inline-flex items-center gap-1.5" role="status" aria-live="polite" data-sync-state={state}>
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold border ${meta.cls}`}>
        <span
          aria-hidden="true"
          className={`w-1.5 h-1.5 rounded-full ${
            state === 'saved' || state === 'submitted'
              ? 'bg-emerald-500'
              : state === 'conflict'
                ? 'bg-rose-500'
                : 'bg-amber-500 animate-pulse'
          }`}
        />
        <span>{labelOverride || meta.label}</span>
      </span>
      {state === 'conflict' && onTakeover && (
        <button
          type="button"
          onClick={onTakeover}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-bold bg-rose-600 text-white hover:bg-rose-700"
        >
          <RefreshCw size={11} />
          <span>Take over</span>
        </button>
      )}
    </div>
  );
}
