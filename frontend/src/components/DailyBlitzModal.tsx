import { useState, useEffect, useRef } from 'react';
import {
  Flame,
  Clock,
  CheckCircle2,
  XCircle,
  ArrowRight,
  X,
  Sparkles,
  AlertCircle,
} from 'lucide-react';
import {
  DailyBlitzApi,
  type DailyBlitzQuestion,
  type DailyBlitzResultResponse,
} from '../lib/api';
import { hapticNotify, hapticSelect } from '../lib/haptics';
import confetti from 'canvas-confetti';

interface DailyBlitzModalProps {
  isOpen: boolean;
  onClose: () => void;
  subject?: string;
  onCompleted?: (result: DailyBlitzResultResponse) => void;
}

export default function DailyBlitzModal({
  isOpen,
  onClose,
  subject = 'uzbek',
  onCompleted,
}: DailyBlitzModalProps) {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [questions, setQuestions] = useState<DailyBlitzQuestion[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [timeLeft, setTimeLeft] = useState(60);
  const [result, setResult] = useState<DailyBlitzResultResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const answersRef = useRef<Record<string, number>>({});

  useEffect(() => {
    answersRef.current = answers;
  }, [answers]);

  const startQuiz = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setAnswers({});
    setCurrentIndex(0);
    setTimeLeft(60);

    try {
      const data = await DailyBlitzApi.getQuestions(subject);
      setQuestions(data.questions || []);
      setLoading(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Savollarni yuklashda xatolik yuz berdi';
      setError(msg);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      startQuiz();
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isOpen, subject]);

  // Countdown timer
  useEffect(() => {
    if (!isOpen || loading || submitting || result || questions.length === 0) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    timerRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          handleAutoSubmit();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isOpen, loading, submitting, result, questions.length]);

  const handleAutoSubmit = async () => {
    await handleSubmit(answersRef.current);
  };

  const handleSelectChoice = (questionId: number, choiceId: number) => {
    hapticSelect();
    setAnswers((prev) => ({
      ...prev,
      [String(questionId)]: choiceId,
    }));
  };

  const handleSubmit = async (finalAnswers?: Record<string, number>) => {
    if (submitting || result) return;
    setSubmitting(true);
    if (timerRef.current) clearInterval(timerRef.current);

    const payload = finalAnswers || answers;

    try {
      const res = await DailyBlitzApi.submitAnswers(subject, payload);
      setResult(res);
      hapticNotify('success');
      try {
        confetti({
          particleCount: 90,
          spread: 75,
          origin: { y: 0.6 },
          colors: ['#F59E0B', '#10B981', '#38BDF8', '#EF4444', '#8B5CF6'],
        });
      } catch {
        /* ignore */
      }
      if (onCompleted) {
        onCompleted(res);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Natijani saqlashda xatolik';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const currentQ = questions[currentIndex];
  const timerPercentage = Math.round((timeLeft / 60) * 100);
  const isTimerUrgent = timeLeft <= 15;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(5, 10, 20, 0.85)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
    >
      <div
        style={{
          background: 'linear-gradient(180deg, #1E293B 0%, #0F172A 100%)',
          border: '1.5px solid rgba(245, 158, 11, 0.3)',
          borderRadius: 24,
          boxShadow: '0 20px 50px rgba(0, 0, 0, 0.6), 0 0 25px rgba(245, 158, 11, 0.15)',
          maxWidth: 540,
          width: '100%',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '90vh',
        }}
      >
        {/* Header Bar */}
        <div
          style={{
            padding: '16px 20px',
            background: 'rgba(255, 255, 255, 0.03)',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                background: 'linear-gradient(135deg, #F59E0B, #D97706)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                boxShadow: '0 0 12px rgba(245, 158, 11, 0.4)',
              }}
            >
              <Flame size={20} />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 800, color: '#fff', display: 'flex', alignItems: 'center', gap: 6 }}>
                ⚡ Kunlik Blits (60s)
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 800,
                    padding: '2px 6px',
                    borderRadius: 6,
                    background: 'rgba(245, 158, 11, 0.2)',
                    color: '#FBBF24',
                    border: '1px solid rgba(245, 158, 11, 0.3)',
                  }}
                >
                  +25 XP
                </span>
              </div>
              <div style={{ fontSize: 11, color: '#94A3B8' }}>
                5 ta tezkor savol • Streak olovini yoqing
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'rgba(255, 255, 255, 0.06)',
              border: 'none',
              borderRadius: 10,
              width: 32,
              height: 32,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#94A3B8',
              cursor: 'pointer',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Content Body */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px 10px', color: '#94A3B8' }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  border: '3px solid rgba(245, 158, 11, 0.2)',
                  borderTopColor: '#F59E0B',
                  borderRadius: '50%',
                  margin: '0 auto 16px',
                  animation: 'spin 0.8s linear infinite',
                }}
              />
              <div style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>Blits savollari tayyorlanmoqda...</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Ekspress savollar to'planmoqda</div>
            </div>
          ) : error ? (
            <div style={{ textAlign: 'center', padding: '30px 10px' }}>
              <AlertCircle size={40} color="#EF4444" style={{ margin: '0 auto 12px' }} />
              <div style={{ fontSize: 14, fontWeight: 700, color: '#EF4444' }}>{error}</div>
              <button
                onClick={startQuiz}
                style={{
                  marginTop: 16,
                  padding: '8px 16px',
                  borderRadius: 10,
                  background: '#F59E0B',
                  color: '#0F172A',
                  fontWeight: 700,
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                Qayta urinish
              </button>
            </div>
          ) : result ? (
            /* Result & Celebration Screen */
            <div style={{ textAlign: 'center', padding: '10px 0' }}>
              <div
                style={{
                  width: 72,
                  height: 72,
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #F59E0B, #EF4444)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 16px',
                  boxShadow: '0 0 35px rgba(245, 158, 11, 0.6)',
                  color: '#fff',
                }}
              >
                <Flame size={40} />
              </div>

              <h2 style={{ fontSize: 22, fontWeight: 900, color: '#fff', margin: '0 0 6px' }}>
                🎉 Blits Yakunlandi!
              </h2>
              <p style={{ fontSize: 13, color: '#94A3B8', margin: '0 0 16px' }}>
                Bugungi ekspress mashg'ulot yakunlandi
              </p>

              {/* Badges Row */}
              <div style={{ display: 'flex', justifyContent: 'center', gap: 10, marginBottom: 20 }}>
                <div
                  style={{
                    background: 'rgba(245, 158, 11, 0.15)',
                    border: '1px solid rgba(245, 158, 11, 0.35)',
                    padding: '8px 16px',
                    borderRadius: 14,
                  }}
                >
                  <div style={{ fontSize: 11, color: '#FBBF24', fontWeight: 700, textTransform: 'uppercase' }}>
                    Natija
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 900, color: '#fff' }}>
                    {result.score} / {result.total}
                  </div>
                </div>

                <div
                  style={{
                    background: 'rgba(239, 68, 68, 0.15)',
                    border: '1px solid rgba(239, 68, 68, 0.35)',
                    padding: '8px 16px',
                    borderRadius: 14,
                  }}
                >
                  <div style={{ fontSize: 11, color: '#F87171', fontWeight: 700, textTransform: 'uppercase' }}>
                    Streak Olovi
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 900, color: '#FF7A00', display: 'flex', alignItems: 'center', gap: 4 }}>
                    🔥 {result.streak_days} kun
                  </div>
                </div>

                <div
                  style={{
                    background: 'rgba(34, 197, 94, 0.15)',
                    border: '1px solid rgba(34, 197, 94, 0.35)',
                    padding: '8px 16px',
                    borderRadius: 14,
                  }}
                >
                  <div style={{ fontSize: 11, color: '#4ADE80', fontWeight: 700, textTransform: 'uppercase' }}>
                    Mukofot
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 900, color: '#4ADE80' }}>
                    +{result.xp_earned} XP
                  </div>
                </div>
              </div>

              {/* Answers Details Breakdown */}
              <div
                style={{
                  textAlign: 'left',
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                  borderRadius: 14,
                  padding: '12px 14px',
                  marginBottom: 20,
                  maxHeight: 220,
                  overflowY: 'auto',
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 700, color: '#94A3B8', marginBottom: 8 }}>
                  Savollar Tahlili:
                </div>
                {result.details.map((d, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                      padding: '8px 0',
                      borderBottom: i < result.details.length - 1 ? '1px solid rgba(255, 255, 255, 0.05)' : 'none',
                    }}
                  >
                    {d.is_correct ? (
                      <CheckCircle2 size={16} color="#22C55E" style={{ flexShrink: 0, marginTop: 2 }} />
                    ) : (
                      <XCircle size={16} color="#EF4444" style={{ flexShrink: 0, marginTop: 2 }} />
                    )}
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: '#F1F5F9' }}>
                        {i + 1}. {d.question_text}
                      </div>
                      {d.explanation && (
                        <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 2 }}>
                          💡 {d.explanation}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <button
                onClick={onClose}
                style={{
                  width: '100%',
                  padding: '12px',
                  borderRadius: 14,
                  background: 'linear-gradient(135deg, #F59E0B, #D97706)',
                  color: '#0F172A',
                  fontSize: 14,
                  fontWeight: 800,
                  border: 'none',
                  cursor: 'pointer',
                  boxShadow: '0 4px 14px rgba(245, 158, 11, 0.4)',
                }}
              >
                Ajoyib, tushundim!
              </button>
            </div>
          ) : (
            /* Active Test Screen */
            <div>
              {/* Timer & Progress Bar */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, color: isTimerUrgent ? '#EF4444' : '#FBBF24' }}>
                    <Clock size={15} />
                    <span>Qolgan vaqt: <b>{timeLeft} soniya</b></span>
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#94A3B8' }}>
                    Savol {currentIndex + 1} / {questions.length}
                  </div>
                </div>

                {/* Animated timer bar */}
                <div
                  style={{
                    height: 6,
                    background: 'rgba(255, 255, 255, 0.1)',
                    borderRadius: 4,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${timerPercentage}%`,
                      background: isTimerUrgent
                        ? 'linear-gradient(90deg, #EF4444, #F43F5E)'
                        : 'linear-gradient(90deg, #F59E0B, #10B981)',
                      transition: 'width 1s linear',
                    }}
                  />
                </div>
              </div>

              {/* Question Text */}
              {currentQ && (
                <div>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 700,
                      color: '#F8FAFC',
                      lineHeight: 1.5,
                      marginBottom: 16,
                      minHeight: 48,
                    }}
                  >
                    {currentIndex + 1}. {currentQ.text}
                  </div>

                  {/* Options */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
                    {currentQ.choices.map((c, cIdx) => {
                      const isSelected = answers[String(currentQ.id)] === c.id;
                      const letter = String.fromCharCode(65 + cIdx);

                      return (
                        <button
                          key={c.id}
                          type="button"
                          onClick={() => handleSelectChoice(currentQ.id, c.id)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 12,
                            padding: '12px 14px',
                            borderRadius: 12,
                            background: isSelected
                              ? 'linear-gradient(135deg, rgba(245, 158, 11, 0.22), rgba(217, 119, 6, 0.16))'
                              : 'rgba(255, 255, 255, 0.04)',
                            border: isSelected
                              ? '2px solid #F59E0B'
                              : '1px solid rgba(255, 255, 255, 0.08)',
                            boxShadow: isSelected
                              ? '0 0 16px rgba(245, 158, 11, 0.4)'
                              : 'none',
                            transform: isSelected ? 'scale(1.02)' : 'scale(1)',
                            cursor: 'pointer',
                            textAlign: 'left',
                            transition: 'all 0.18s cubic-bezier(0.4, 0, 0.2, 1)',
                          }}
                        >
                          <span
                            style={{
                              width: 24,
                              height: 24,
                              borderRadius: 6,
                              background: isSelected ? '#F59E0B' : 'rgba(255, 255, 255, 0.08)',
                              color: isSelected ? '#0F172A' : '#CBD5E1',
                              fontWeight: 800,
                              fontSize: 12,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0,
                            }}
                          >
                            {letter}
                          </span>
                          <span style={{ fontSize: 13, fontWeight: 600, color: isSelected ? '#FBBF24' : '#F1F5F9' }}>
                            {c.text}
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  {/* Navigation controls */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                    <button
                      type="button"
                      disabled={currentIndex === 0}
                      onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
                      style={{
                        padding: '10px 16px',
                        borderRadius: 10,
                        background: 'rgba(255, 255, 255, 0.06)',
                        color: currentIndex === 0 ? '#475569' : '#CBD5E1',
                        fontSize: 13,
                        fontWeight: 700,
                        border: 'none',
                        cursor: currentIndex === 0 ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Oldingi
                    </button>

                    {currentIndex < questions.length - 1 ? (
                      <button
                        type="button"
                        onClick={() => setCurrentIndex((prev) => prev + 1)}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: '10px 18px',
                          borderRadius: 10,
                          background: '#334155',
                          color: '#fff',
                          fontSize: 13,
                          fontWeight: 700,
                          border: 'none',
                          cursor: 'pointer',
                        }}
                      >
                        <span>Keyingi</span>
                        <ArrowRight size={14} />
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={submitting}
                        onClick={() => handleSubmit()}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: '10px 20px',
                          borderRadius: 10,
                          background: 'linear-gradient(135deg, #F59E0B, #D97706)',
                          color: '#0F172A',
                          fontSize: 13,
                          fontWeight: 800,
                          border: 'none',
                          cursor: submitting ? 'wait' : 'pointer',
                          boxShadow: '0 4px 12px rgba(245, 158, 11, 0.35)',
                        }}
                      >
                        <Sparkles size={14} />
                        <span>{submitting ? 'Tekshirilmoqda...' : 'Blitsni yakunlash'}</span>
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
