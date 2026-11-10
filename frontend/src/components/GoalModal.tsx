import React, { useState, useEffect, useRef } from 'react';
import { Auth } from '../lib/api';
import { useAuth } from '../context/AuthContext';

export interface GoalModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: (newPlan: {
    target_exam: string;
    target_grade: string;
    daily_goal_questions: number;
    daily_goal_minutes: number;
  }) => void;
  currentExam?: string;
  currentGrade?: string;
  currentQuestions?: number;
  subject?: Subject;
}

export type Subject = 'uzbek' | 'english' | 'biology' | 'chemistry' | 'law';

interface ExamOption {
  id: string;
  title: string;
  subject: Subject;
  icon: string;
  grades: Array<{ id: string; label: string }>;
}

const EXAM_OPTIONS: ExamOption[] = [
  {
    id: 'milliy_sertifikat',
    title: 'Ona tili Milliy Sertifikat (BMB)',
    subject: 'uzbek',
    icon: '🇺🇿',
    grades: [
      { id: 'A+', label: 'A+ (Maksimal — 70+ ball)' },
      { id: 'A', label: 'A daraja (65–69 ball)' },
      { id: 'B+', label: 'B+ daraja (60–64 ball)' },
      { id: 'B', label: 'B daraja (50–59 ball)' },
    ],
  },
  {
    id: 'bmba',
    title: 'BMBA (DTM) Asosiy va Majburiy Blok',
    subject: 'uzbek',
    icon: '🏛️',
    grades: [
      { id: '189 ball', label: '189 ball (Maksimal / Davlat Granti)' },
      { id: '160+ ball', label: '160+ ball (Davlat Granti)' },
      { id: '140+ ball', label: '140+ ball (To‘lov-shartnoma)' },
    ],
  },
  {
    id: 'chemistry_milliy',
    title: 'Kimyo Milliy Sertifikat (BMB)',
    subject: 'chemistry',
    icon: '🧪',
    grades: [
      { id: 'A+', label: 'A+ (Maksimal — 70+ ball)' },
      { id: 'A', label: 'A daraja (65–69 ball)' },
      { id: 'B+', label: 'B+ daraja (60–64 ball)' },
      { id: 'B', label: 'B daraja (50–59 ball)' },
    ],
  },
  {
    id: 'chemistry_dtm',
    title: 'BMBA Kimyo (Tibbiyot Yo‘nalishi)',
    subject: 'chemistry',
    icon: '🩺',
    grades: [
      { id: '93 ball', label: '93 ball (Maksimal)' },
      { id: '80+ ball', label: '80+ ball (Davlat Granti)' },
      { id: '65+ ball', label: '65+ ball (Kontrakt)' },
    ],
  },
  {
    id: 'biology_milliy',
    title: 'Biologiya Milliy Sertifikat (BMB)',
    subject: 'biology',
    icon: '🧬',
    grades: [
      { id: 'A+', label: 'A+ (Maksimal — 70+ ball)' },
      { id: 'A', label: 'A daraja (65–69 ball)' },
      { id: 'B+', label: 'B+ daraja (60–64 ball)' },
      { id: 'B', label: 'B daraja (50–59 ball)' },
    ],
  },
  {
    id: 'biology_cbt',
    title: 'Biologiya 45 talik CBT Arena',
    subject: 'biology',
    icon: '🔬',
    grades: [
      { id: 'A+', label: 'A+ (Maksimal — 70+ ball)' },
      { id: 'A', label: 'A daraja (65–69 ball)' },
      { id: 'B+', label: 'B+ daraja (60–64 ball)' },
    ],
  },
  {
    id: 'law_milliy',
    title: 'Huquqshunoslik Milliy Sertifikat (BMB)',
    subject: 'law',
    icon: '⚖️',
    grades: [
      { id: 'A+', label: 'A+ (Maksimal — 70+ ball)' },
      { id: 'A', label: 'A daraja (65–69 ball)' },
      { id: 'B+', label: 'B+ daraja (60–64 ball)' },
    ],
  },
  {
    id: 'law_bmba',
    title: 'BMBA Yurisprudensiya Bloki',
    subject: 'law',
    icon: '🏛️',
    grades: [
      { id: '93 ball', label: '93 ball (Maksimal)' },
      { id: '80+ ball', label: '80+ ball (Yuridik grant)' },
    ],
  },
  {
    id: 'cefr',
    title: 'CEFR Multi-Level (BMB)',
    subject: 'english',
    icon: '🇬🇧',
    grades: [
      { id: 'C1', label: 'C1 (Maksimal — 65+ ball)' },
      { id: 'B2', label: 'B2 (Mustaqil — 51–64 ball)' },
      { id: 'B1', label: 'B1 (Boshlang‘ich — 38–50 ball)' },
    ],
  },
  {
    id: 'ielts',
    title: 'IELTS Academic',
    subject: 'english',
    icon: '🎓',
    grades: [
      { id: 'Band 7.5+', label: 'Band 7.5+ (Ilg‘or)' },
      { id: 'Band 7.0', label: 'Band 7.0 (Yaxshi)' },
      { id: 'Band 8.0+', label: 'Band 8.0+ (Maksimal)' },
      { id: 'Band 6.5', label: 'Band 6.5 (Yetarli)' },
    ],
  },
];

const QUESTION_GOALS = [
  { count: 15, minutes: 15, title: '15 ta savol', desc: 'Yengil (kuniga 15–20 daqiqa)', badge: '🌱 Yengil' },
  { count: 30, minutes: 30, title: '30 ta savol', desc: 'Tavsiya etiladi (kuniga 30–40 daqiqa)', badge: '⭐ Tavsiya etiladi' },
  { count: 50, minutes: 50, title: '50 ta savol', desc: 'Intensiv (kuniga 50–60 daqiqa)', badge: '🔥 Intensiv' },
];

export const GoalModal: React.FC<GoalModalProps> = ({
  isOpen,
  onClose,
  onSaved,
  currentExam = 'milliy_sertifikat',
  currentGrade = 'A+',
  currentQuestions = 30,
  subject,
}) => {
  const { user, updateUser } = useAuth();
  const [selectedExam, setSelectedExam] = useState<string>(currentExam);
  const [selectedGrade, setSelectedGrade] = useState<string>(currentGrade);
  const [selectedQuestions, setSelectedQuestions] = useState<number>(currentQuestions);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const modalRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  // Sync initial values when opened or props change
  useEffect(() => {
    if (isOpen) {
      let defaultForSubject: string | undefined;
      if (subject) {
        const found = EXAM_OPTIONS.find((e) => e.subject === subject);
        if (found) defaultForSubject = found.id;
      }
      const matchExam = EXAM_OPTIONS.find((e) =>
        subject
          ? e.subject === subject && (e.id === currentExam || currentExam.toLowerCase().includes(e.id))
          : e.id === currentExam || currentExam.toLowerCase().includes(e.id),
      );
      setSelectedExam(matchExam ? matchExam.id : defaultForSubject || 'milliy_sertifikat');
      setSelectedGrade(currentGrade || 'A+');
      setSelectedQuestions(currentQuestions || 30);
      setError(null);
      setTimeout(() => closeBtnRef.current?.focus(), 50);
    }
  }, [isOpen, currentExam, currentGrade, currentQuestions, subject]);

  // Handle ESC key to close
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const currentExamObj = EXAM_OPTIONS.find((e) => e.id === selectedExam) || EXAM_OPTIONS[0];

  const handleSelectExam = (examId: string) => {
    setSelectedExam(examId);
    const targetObj = EXAM_OPTIONS.find((e) => e.id === examId);
    if (targetObj && targetObj.grades.length > 0) {
      // Pick first grade if current grade doesn't fit
      const exists = targetObj.grades.some((g) => g.id === selectedGrade);
      if (!exists) {
        setSelectedGrade(targetObj.grades[0].id);
      }
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const goalObj = QUESTION_GOALS.find((q) => q.count === selectedQuestions) || QUESTION_GOALS[1];
    const targetSubject = currentExamObj.subject;

    const payload = {
      target_exam: selectedExam,
      exam_target: selectedExam,
      target_grade: selectedGrade,
      daily_goal_minutes: goalObj.minutes,
      goal_questions: selectedQuestions,
      daily_goal_questions: selectedQuestions,
      active_subject: targetSubject,
    };

    try {
      // 1. Persist to backend via updateProfile and saveOnboarding
      await Auth.updateProfile({
        target_exam: selectedExam,
        exam_target: selectedExam,
        target_grade: selectedGrade,
        daily_goal_minutes: goalObj.minutes,
        active_subject: targetSubject,
      });

      try {
        await Auth.saveOnboarding(payload);
      } catch {
        /* best-effort fallback */
      }

      // 2. Persist locally
      try {
        localStorage.setItem(
          'grandec_user_plan',
          JSON.stringify({
            ...payload,
            updated_at: new Date().toISOString(),
          }),
        );
        localStorage.setItem('active_subject', targetSubject);
        window.dispatchEvent(new CustomEvent('subject-changed', { detail: targetSubject }));
      } catch {
        /* storage ignore */
      }

      // 3. Update Auth context state
      updateUser({
        ...(user || {}),
        target_exam: selectedExam,
        exam_target: selectedExam,
        target_grade: selectedGrade,
        daily_goal_minutes: goalObj.minutes,
        active_subject: targetSubject,
        daily_plan_summary: {
          ...((user?.daily_plan_summary as Record<string, unknown>) || {}),
          goal_questions: selectedQuestions,
          target_exam: selectedExam,
          target_grade: selectedGrade,
          daily_minutes: goalObj.minutes,
        },
      });

      // 4. Notify parent Dashboard
      onSaved?.({
        target_exam: selectedExam,
        target_grade: selectedGrade,
        daily_goal_questions: selectedQuestions,
        daily_goal_minutes: goalObj.minutes,
      });

      onClose();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Rejani saqlashda xatolik yuz berdi. Qaytadan urinib ko‘ring.',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="goal-modal-title"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(6px)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !loading) onClose();
      }}
    >
      <div
        ref={modalRef}
        style={{
          width: '100%',
          maxWidth: '540px',
          maxHeight: '90vh',
          overflowY: 'auto',
          backgroundColor: 'var(--card, #ffffff)',
          color: 'var(--ink, #0f172a)',
          borderRadius: '20px',
          border: '1px solid var(--border, rgba(226, 232, 240, 0.8))',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h2 id="goal-modal-title" style={{ margin: 0, fontSize: '20px', fontWeight: 800 }}>
              🎯 O‘quv rejasini o‘zgartirish
            </h2>
            <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: 'var(--muted, #64748b)' }}>
              Imtihon maqsadi va kunlik mashq yuklamasini belgilang
            </p>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            disabled={loading}
            aria-label="Yopish"
            style={{
              background: 'transparent',
              border: 'none',
              fontSize: '22px',
              cursor: 'pointer',
              color: 'var(--muted, #64748b)',
              padding: '6px',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.15s ease',
            }}
          >
            ✕
          </button>
        </div>

        {error && (
          <div
            style={{
              padding: '12px 14px',
              borderRadius: '12px',
              backgroundColor: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: 'var(--danger, #ef4444)',
              fontSize: '13.5px',
              fontWeight: 600,
            }}
          >
            ⚠️ {error}
          </div>
        )}

        <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Section 1: Asosiy yo'nalish / imtihon */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <label style={{ fontSize: '13.5px', fontWeight: 700, color: 'var(--ink, #0f172a)' }}>
              1. Asosiy yo‘nalish / Imtihon turi
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '8px' }}>
              {(subject
                ? [...EXAM_OPTIONS].sort((a, b) => {
                    if (a.subject === subject && b.subject !== subject) return -1;
                    if (b.subject === subject && a.subject !== subject) return 1;
                    return 0;
                  })
                : EXAM_OPTIONS
              ).map((exam) => {
                const isSelected = selectedExam === exam.id;
                return (
                  <button
                    key={exam.id}
                    type="button"
                    onClick={() => handleSelectExam(exam.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '12px 14px',
                      borderRadius: '12px',
                      border: isSelected ? '2px solid #C8922A' : '1px solid var(--border, rgba(226, 232, 240, 0.8))',
                      backgroundColor: isSelected ? 'rgba(200, 146, 42, 0.12)' : 'var(--card-2, #f8fafc)',
                      color: isSelected ? '#C8922A' : 'var(--ink, #0f172a)',
                      cursor: 'pointer',
                      textAlign: 'left',
                      fontWeight: isSelected ? 800 : 600,
                      fontSize: '14px',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <span style={{ fontSize: '20px' }}>{exam.icon}</span>
                    <span>{exam.title}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Section 2: Maqsad daraja */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <label style={{ fontSize: '13.5px', fontWeight: 700, color: 'var(--ink, #0f172a)' }}>
              2. Maqsad daraja ({currentExamObj.title})
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '8px' }}>
              {currentExamObj.grades.map((grade) => {
                const isSelected = selectedGrade === grade.id;
                return (
                  <button
                    key={grade.id}
                    type="button"
                    onClick={() => setSelectedGrade(grade.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 14px',
                      borderRadius: '12px',
                      border: isSelected ? '2px solid #C8922A' : '1px solid var(--border, rgba(226, 232, 240, 0.8))',
                      backgroundColor: isSelected ? 'rgba(200, 146, 42, 0.12)' : 'var(--card-2, #f8fafc)',
                      color: isSelected ? '#C8922A' : 'var(--ink, #0f172a)',
                      cursor: 'pointer',
                      fontWeight: isSelected ? 800 : 600,
                      fontSize: '13.5px',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <span>{grade.label}</span>
                    {isSelected && <span>✓</span>}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Section 3: Kunlik maqsad */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <label style={{ fontSize: '13.5px', fontWeight: 700, color: 'var(--ink, #0f172a)' }}>
              3. Kunlik maqsad (Savollar soni)
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
              {QUESTION_GOALS.map((goal) => {
                const isSelected = selectedQuestions === goal.count;
                return (
                  <button
                    key={goal.count}
                    type="button"
                    onClick={() => setSelectedQuestions(goal.count)}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      padding: '12px 8px',
                      borderRadius: '12px',
                      border: isSelected ? '2px solid #C8922A' : '1px solid var(--border, rgba(226, 232, 240, 0.8))',
                      backgroundColor: isSelected ? 'rgba(200, 146, 42, 0.12)' : 'var(--card-2, #f8fafc)',
                      color: isSelected ? '#C8922A' : 'var(--ink, #0f172a)',
                      cursor: 'pointer',
                      textAlign: 'center',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <span style={{ fontSize: '16px', fontWeight: 800 }}>{goal.title}</span>
                    <span style={{ fontSize: '11px', marginTop: '4px', opacity: 0.85 }}>{goal.badge}</span>
                  </button>
                );
              })}
            </div>
            <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--muted, #64748b)' }}>
              💡 {QUESTION_GOALS.find((q) => q.count === selectedQuestions)?.desc}
            </p>
          </div>

          {/* Action buttons */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: '12px',
              paddingTop: '8px',
              borderTop: '1px solid var(--border, rgba(226, 232, 240, 0.8))',
            }}
          >
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              style={{
                padding: '10px 18px',
                borderRadius: '12px',
                border: '1px solid var(--border, rgba(226, 232, 240, 0.8))',
                backgroundColor: 'transparent',
                color: 'var(--ink, #0f172a)',
                fontSize: '14px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Bekor qilish
            </button>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '10px 24px',
                borderRadius: '12px',
                border: 'none',
                background: 'linear-gradient(135deg, #C8922A 0%, #F59E0B 100%)',
                color: '#ffffff',
                fontSize: '14px',
                fontWeight: 800,
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.7 : 1,
                boxShadow: '0 4px 12px rgba(200, 146, 42, 0.3)',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              {loading ? 'Saqlanmoqda...' : '💾 Rejani saqlash'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default GoalModal;
