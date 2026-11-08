import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useLang } from '../i18n/LangContext';
import { ProfileApi } from '../lib/api';
import { isValidSubject, type Subject } from '../lib/useSubject';

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

export const SUBJECT_CONFIGS: SubjectConfig[] = [
  {
    id: 'biology',
    icon: '🧬',
    labelKey: 'subject_biology',
    fallbackLabel: 'Biologiya',
    gradient: 'linear-gradient(135deg, rgba(16, 185, 129, 0.22), rgba(20, 184, 166, 0.32))',
    borderColor: '#10b981',
    activeTextColor: '#34d399',
    glowColor: 'rgba(16, 185, 129, 0.45)',
  },
  {
    id: 'chemistry',
    icon: '🧪',
    labelKey: 'subject_chemistry',
    fallbackLabel: 'Kimyo',
    gradient: 'linear-gradient(135deg, rgba(139, 92, 246, 0.22), rgba(99, 102, 241, 0.32))',
    borderColor: '#8b5cf6',
    activeTextColor: '#a78bfa',
    glowColor: 'rgba(139, 92, 246, 0.45)',
  },
  {
    id: 'law',
    icon: '⚖️',
    labelKey: 'subject_law',
    fallbackLabel: 'Huquq',
    gradient: 'linear-gradient(135deg, rgba(245, 158, 11, 0.22), rgba(234, 179, 8, 0.32))',
    borderColor: '#f59e0b',
    activeTextColor: '#fbbf24',
    glowColor: 'rgba(245, 158, 11, 0.45)',
  },
  {
    id: 'uzbek',
    icon: '🇺🇿',
    labelKey: 'subject_uzbek',
    fallbackLabel: 'Ona tili',
    gradient: 'linear-gradient(135deg, rgba(14, 165, 233, 0.22), rgba(6, 182, 212, 0.32))',
    borderColor: '#0ea5e9',
    activeTextColor: '#38bdf8',
    glowColor: 'rgba(14, 165, 233, 0.45)',
  },
  {
    id: 'english',
    icon: '🇬🇧',
    labelKey: 'subject_english',
    fallbackLabel: 'Ingliz tili',
    gradient: 'linear-gradient(135deg, rgba(244, 63, 94, 0.22), rgba(249, 115, 22, 0.32))',
    borderColor: '#f43f5e',
    activeTextColor: '#fb7185',
    glowColor: 'rgba(244, 63, 94, 0.45)',
  },
];

/**
 * Subject Switcher with smooth horizontal touch-scrolling & subject brand palettes.
 * Biologiya: emerald/teal
 * Kimyo: violet/indigo
 * Huquq: amber/yellow
 * Ona tili: sky/cyan
 * Ingliz tili: rose/orange
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

  // Active subject from user profile or local storage fallback
  const currentSubject: Subject = isValidSubject(user?.active_subject)
    ? user.active_subject
    : (() => {
        try {
          const stored = localStorage.getItem('lms_subject');
          if (isValidSubject(stored)) return stored;
        } catch {
          /* ignore */
        }
        return 'biology';
      })();

  const handleSelect = async (nextSubject: Subject) => {
    if (nextSubject === currentSubject || loading) return;

    setLoading(true);
    try {
      localStorage.setItem('lms_subject', nextSubject);
    } catch {
      /* ignore */
    }

    const nextTarget = nextSubject === 'english' ? 'ielts' : 'national_certificate';
    const nextGrade = nextSubject === 'english' ? 'Band 7.5' : 'A+';

    if (user) {
      try {
        const res = await ProfileApi.switchSubject(nextSubject, nextTarget);
        updateUserLocal({
          active_subject: (res.active_subject as Subject) || nextSubject,
          exam_target: res.exam_target || nextTarget,
          target_grade: res.target_grade || nextGrade,
          daily_plan_summary: res.daily_plan_summary || undefined,
        });
      } catch (err) {
        console.error('Failed to switch subject on server:', err);
        updateUserLocal({
          active_subject: nextSubject,
          exam_target: nextTarget,
          target_grade: nextGrade,
        });
      }
    }

    window.dispatchEvent(new CustomEvent('subject-changed', { detail: nextSubject }));
    onSwitch?.(nextSubject);
    setLoading(false);
  };

  const isSmall = size === 'sm';

  return (
    <div
      role="group"
      aria-label={t('subject_label', 'Fan tanlash')}
      className={`subject-switcher-scroll ${variant === 'seg' ? 'ui-seg' : 'subject-switcher-container'} overflow-x-auto no-scrollbar scroll-smooth ${className}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        maxWidth: '100%',
        overflowX: 'auto',
        WebkitOverflowScrolling: 'touch',
        scrollbarWidth: 'none',
        msOverflowStyle: 'none',
        padding: variant === 'seg' ? '4px 6px' : '3px 4px',
        borderRadius: 14,
        background: variant === 'seg' ? 'rgba(15, 23, 42, 0.45)' : 'transparent',
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
            className={`subject-pill-btn transition-all duration-200 ${isActive ? 'is-active' : ''}`}
            style={{
              whiteSpace: 'nowrap',
              flexShrink: 0,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: isSmall ? '4px 10px' : '6px 13px',
              borderRadius: 10,
              fontSize: isSmall ? 12 : 13,
              fontWeight: isActive ? 700 : 500,
              border: isActive ? `1.5px solid ${s.borderColor}` : '1.5px solid transparent',
              background: isActive ? s.gradient : 'rgba(255, 255, 255, 0.04)',
              color: isActive ? s.activeTextColor : 'var(--muted, #94a3b8)',
              boxShadow: isActive ? `0 2px 10px ${s.glowColor}` : 'none',
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
  );
}
