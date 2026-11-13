import { useState, useEffect } from 'react';
import { useAuth } from '../auth/authState';
import { useLang } from '../i18n/LangContext';
import { ProfileApi } from '../lib/api';
import { useSubject, type Subject } from '../lib/useSubject';
import { hapticImpact } from '../lib/haptics';

interface SubjectSwitcherProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  /** seg = full-width scrollable segmented control for mobile & sub-headers. */
  variant?: 'pill' | 'seg';
  onSwitch?: (subject: Subject) => void;
}

export interface SubjectConfig {
  id: Subject;
  icon: string;
  labelKey: string;
  fallbackLabel: string;
  gradient: string;
  borderColor: string;
  activeTextColor: string;
  glowColor: string;
}

const SUBJECT_CONFIGS: SubjectConfig[] = [
  {
    id: 'english',
    icon: '🇬🇧',
    labelKey: 'subject_english',
    fallbackLabel: 'Ingliz tili',
    gradient: 'linear-gradient(135deg, rgba(59, 130, 246, 0.22), rgba(37, 99, 235, 0.32))',
    borderColor: '#3B82F6',
    activeTextColor: '#60a5fa',
    glowColor: 'rgba(59, 130, 246, 0.45)',
  },
  {
    id: 'chemistry',
    icon: '🧪',
    labelKey: 'subject_chemistry',
    fallbackLabel: 'Kimyo',
    gradient: 'linear-gradient(135deg, rgba(16, 185, 129, 0.22), rgba(5, 150, 105, 0.32))',
    borderColor: '#10B981',
    activeTextColor: '#34d399',
    glowColor: 'rgba(16, 185, 129, 0.45)',
  },
  {
    id: 'biology',
    icon: '🧬',
    labelKey: 'subject_biology',
    fallbackLabel: 'Biologiya',
    gradient: 'linear-gradient(135deg, rgba(6, 182, 212, 0.22), rgba(14, 165, 233, 0.32))',
    borderColor: '#06B6D4',
    activeTextColor: '#38bdf8',
    glowColor: 'rgba(6, 182, 212, 0.45)',
  },
  {
    id: 'law',
    icon: '⚖️',
    labelKey: 'subject_law',
    fallbackLabel: 'Huquq',
    gradient: 'linear-gradient(135deg, rgba(139, 92, 246, 0.22), rgba(124, 58, 237, 0.32))',
    borderColor: '#8B5CF6',
    activeTextColor: '#a78bfa',
    glowColor: 'rgba(139, 92, 246, 0.45)',
  },
  {
    id: 'uzbek',
    icon: '🇺🇿',
    labelKey: 'subject_uzbek',
    fallbackLabel: 'Ona tili',
    gradient: 'linear-gradient(135deg, rgba(14, 165, 233, 0.22), rgba(2, 132, 199, 0.32))',
    borderColor: '#0EA5E9',
    activeTextColor: '#38bdf8',
    glowColor: 'rgba(14, 165, 233, 0.45)',
  },
];

/**
 * Subject Switcher with smooth horizontal touch-scrolling & subject brand palettes.
 * Ingliz tili: royal blue (#3B82F6)
 * Kimyo: emerald green (#10B981)
 * Biologiya: bio teal (#06B6D4)
 * Huquq: imperial purple (#8B5CF6)
 * Ona tili: sky turquoise (#0EA5E9)
 */
export default function SubjectSwitcher({
  className = '',
  size = 'md',
  variant = 'pill',
  onSwitch,
}: SubjectSwitcherProps) {
  const { user, updateUserLocal } = useAuth();
  const { t } = useLang();
  const [loading, setLoading] = useState(false);

  const currentSubject = useSubject();
  const [error, setError] = useState<string | null>(null);
  const examOptions = currentSubject === 'english'
    ? [['undecided', t('exam_undecided', 'Hali tanlanmagan')], ['ielts', 'IELTS'], ['multilevel', 'CEFR Multilevel']]
    : currentSubject === 'uzbek'
      ? [['undecided', t('exam_undecided', 'Hali tanlanmagan')], ['national_certificate', t('exam_national', 'Milliy sertifikat')], ['attestation', t('exam_attestation', 'Attestatsiya')]]
      : [['undecided', t('exam_undecided', 'Hali tanlanmagan')], ['national_certificate', t('exam_national', 'Milliy sertifikat')]];

  // Keep data-subject synchronized on root document for CSS Chameleon Token
  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-subject', currentSubject);
    }
  }, [currentSubject]);

  const handleSelect = async (nextSubject: Subject, target?: string) => {
    if (loading || (nextSubject === currentSubject && !target)) return;
    hapticImpact('light');
    setError(null);
    setLoading(true);
    try {
      if (user) {
        const res = await ProfileApi.switchSubject(nextSubject, target);
        updateUserLocal({
          active_subject: res.active_subject,
          exam_target: res.exam_target,
          target_grade: res.target_grade,
          daily_plan_summary: res.daily_plan_summary,
        });
      }
      try { localStorage.setItem('lms_subject', nextSubject); } catch { /* storage is optional */ }
      window.dispatchEvent(new CustomEvent('subject-changed', { detail: nextSubject }));
      onSwitch?.(nextSubject);
    } catch {
      setError(t('subject_switch_failed', 'Fan yoki maqsad saqlanmadi. Qayta urinib ko‘ring.'));
    } finally {
      setLoading(false);
    }
  };

  const isSmall = size === 'sm';
  const isSeg = variant === 'seg';

  return (
    <div>
    <div
      role="group"
      aria-label={t('subject_label', 'Fan tanlash')}
      className={`subject-switcher-scroll ${
        isSeg
          ? 'subject-seg flex items-center gap-2 overflow-x-auto no-scrollbar py-2 px-3 bg-slate-100/90 dark:bg-slate-900/80 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300'
          : 'subject-switcher-container overflow-x-auto no-scrollbar bg-slate-100/90 border border-slate-200 text-slate-700 dark:bg-slate-900/80 dark:border-slate-800 dark:text-slate-300'
      } scroll-smooth transition-all duration-200 ${className}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: isSeg ? '8px' : '6px',
        maxWidth: '100%',
        width: isSeg ? '100%' : undefined,
        overflowX: 'auto',
        WebkitOverflowScrolling: 'touch',
        scrollbarWidth: 'none',
        msOverflowStyle: 'none',
        scrollSnapType: isSeg ? 'x proximity' : undefined,
        padding: isSeg ? '8px 12px' : '4px 5px',
        borderRadius: 14,
      }}
    >
      {SUBJECT_CONFIGS.map((s) => {
        const isActive = currentSubject === s.id;
        return (
          <button
            key={s.id}
            type="button"
            disabled={loading}
            aria-pressed={isActive}
            onClick={() => handleSelect(s.id)}
            className={`subject-pill-btn transition-all duration-200 ${
              isActive
                ? 'is-active shadow-sm text-slate-900 dark:text-white'
                : 'bg-white/80 dark:bg-slate-800/70 text-slate-700 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800'
            }`}
            style={{
              whiteSpace: 'nowrap',
              flex: '0 0 auto',
              flexShrink: 0,
              minWidth: 'max-content',
              overflow: 'visible',
              scrollSnapAlign: isSeg ? 'start' : undefined,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: isSmall ? '5px 11px' : isSeg ? '6px 13px' : '6px 14px',
              minHeight: isSeg ? 36 : undefined,
              borderRadius: isSeg ? 999 : 10,
              fontSize: isSmall ? 12 : 13,
              fontWeight: isActive ? 700 : 600,
              border: isActive
                ? `1.5px solid ${s.borderColor}`
                : '1px solid var(--border-subtle, rgba(148,163,184,0.3))',
              background: isActive ? s.gradient : undefined,
              boxShadow: isActive ? `0 2px 10px ${s.glowColor}` : undefined,
              cursor: loading ? 'default' : 'pointer',
              userSelect: 'none',
              WebkitTapHighlightColor: 'transparent',
            }}
          >
            <span style={{ fontSize: isSmall ? 13 : 15 }}>{s.icon}</span>
            <span>{t(s.labelKey) || s.fallbackLabel}</span>
            {isActive && (
              <span
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  backgroundColor: s.borderColor,
                  boxShadow: `0 0 6px ${s.borderColor}`,
                  display: 'inline-block',
                }}
              />
            )}
          </button>
        );
      })}
    </div>
    {user && <label style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 6px', fontSize: 12 }}>
      <span>{t('exam_goal_label', 'Imtihon maqsadi')}</span>
      <select aria-label={t('exam_goal_label', 'Imtihon maqsadi')} disabled={loading}
        value={examOptions.some(([value]) => value === user.exam_target) ? user.exam_target : ''}
        onChange={(event) => handleSelect(currentSubject, event.target.value)}>
        {!examOptions.some(([value]) => value === user.exam_target) && <option value="">{t('exam_goal_select', 'Maqsadni tanlang')}</option>}
        {examOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>}
    {error && <p role="alert" style={{ color: 'var(--text-danger, #b91c1c)', fontSize: 12 }}>{error}</p>}
    </div>
  );
}
