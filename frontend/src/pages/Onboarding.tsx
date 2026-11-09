import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import confetti from 'canvas-confetti';
import { useAuth } from '../context/AuthContext';
import { api } from '../lib/api';

export interface OnboardingProps {
  isModal?: boolean;
  onClose?: () => void;
  onSuccess?: () => void;
}

type ActiveSubject = 'uzbek' | 'english' | 'biology' | 'chemistry' | 'law';
type TargetExam = 'milliy_sertifikat' | 'cefr' | 'ielts' | 'attestatsiya' | 'bmba' | 'biology' | 'chemistry' | 'law' | 'other';
type PrepLevel = 'zero' | 'beginner' | 'intermediate';
type ReminderSlot = 'morning' | 'afternoon' | 'evening';

const EXAM_TRACKS: Array<{
  id: TargetExam;
  icon: string;
  title: string;
  subtitle: string;
  active_subject: ActiveSubject;
  target_exam: string;
}> = [
  {
    id: 'milliy_sertifikat',
    icon: '🇺🇿',
    title: 'Ona tili va Adabiyot (Milliy sertifikat)',
    subtitle: 'BMB 45 talik test va 12 mezonli AI Esse tahlili',
    active_subject: 'uzbek',
    target_exam: 'milliy_sertifikat',
  },
  {
    id: 'cefr',
    icon: '🇬🇧',
    title: 'Ingliz tili (CEFR Multi-level)',
    subtitle: 'B1, B2, C1 darajali CBT Mock, Writing va Speaking',
    active_subject: 'english',
    target_exam: 'cefr',
  },
  {
    id: 'ielts',
    icon: '🎓',
    title: 'IELTS Academic / General',
    subtitle: 'Band 1.0–9.0 simulyatori, Writing va Speaking baholash',
    active_subject: 'english',
    target_exam: 'ielts',
  },
  {
    id: 'biology',
    icon: '🧬',
    title: 'Biologiya (Milliy sertifikat & DTM)',
    subtitle: 'Sitologiya, genetika, anatomiya va masalalar tahlili',
    active_subject: 'biology',
    target_exam: 'biology',
  },
  {
    id: 'chemistry',
    icon: '🧪',
    title: 'Kimyo (Milliy sertifikat & DTM)',
    subtitle: 'Umumiy, anorganik, eritmalar va organik kimyo',
    active_subject: 'chemistry',
    target_exam: 'chemistry',
  },
  {
    id: 'law',
    icon: '⚖️',
    title: 'Huquqshunoslik (Yurisprudensiya & DTM)',
    subtitle: 'Konstitutsiya, davlat va huquq nazariyasi, kazus tahlili',
    active_subject: 'law',
    target_exam: 'law',
  },
  {
    id: 'bmba',
    icon: '🏛️',
    title: 'BMBA (DTM) Davlat Imtihonlari',
    subtitle: 'Majburiy va mutaxassislik bloklar bo‘yicha to‘liq tayyorgarlik',
    active_subject: 'uzbek',
    target_exam: 'bmba',
  },
];

const GOAL_OPTIONS = [
  {
    id: 'certificate',
    icon: '🏆',
    title: 'Davlat yoki xalqaro sertifikat olish',
    subtitle: 'Rasmiy imtihonda yuqori daraja (A+, C1, Band 7.5+) qo‘lga kiritish',
  },
  {
    id: 'university_grant',
    icon: '🎓',
    title: 'Oliygohga davlat granti bilan kirish',
    subtitle: 'Maksimal ball va muddatidan oldin 100% imtiyozga ega bo‘lish',
  },
  {
    id: 'attestation_bonus',
    icon: '📜',
    title: 'Pedagoglar attestatsiyasi va ustama',
    subtitle: 'Oliy toifa va 70% vazir jamg‘armasi ustamasiga erishish',
  },
];

const LEVEL_OPTIONS: Array<{
  id: PrepLevel;
  icon: string;
  title: string;
  subtitle: string;
}> = [
  {
    id: 'zero',
    icon: '🌱',
    title: 'Nol darajadaman (Yangi boshlovchi)',
    subtitle: 'Tartibli poydevor, qoidalar va sodda tushuntirish kerak',
  },
  {
    id: 'beginner',
    icon: '⚡',
    title: 'Boshlang‘ich tushuncham bor',
    subtitle: 'Asoslarni bilaman, mashqlar va xatolar ustida ishlash zarur',
  },
  {
    id: 'intermediate',
    icon: '🔥',
    title: 'O‘rta va yuqori darajadaman',
    subtitle: 'Muntazam mock testlar, tezlik va yuqori ball uchun sprint',
  },
];

const QUESTION_GOALS = [
  { count: 15, minutes: 15, icon: '🌱', title: '15 ta savol (Yengil)', subtitle: 'Kuniga 15–20 daqiqa yengil mashq' },
  { count: 30, minutes: 30, icon: '⭐', title: '30 ta savol (Tavsiya etiladi)', subtitle: 'Kuniga 30–40 daqiqa barqaror rivojlanish' },
  { count: 50, minutes: 50, icon: '🔥', title: '50 ta savol (Intensiv)', subtitle: 'Kuniga 50–60 daqiqa chuqur tayyorgarlik' },
];

const REMINDER_OPTIONS: Array<{
  id: ReminderSlot;
  icon: string;
  title: string;
  subtitle: string;
}> = [
  { id: 'morning', icon: '🌅', title: 'Ertalab (09:00)', subtitle: 'Kunni tetik mashq bilan boshlash' },
  { id: 'afternoon', icon: '☀️', title: 'Tushdan so‘ng (14:00)', subtitle: 'Tushlik tanaffusida shug‘ullanish' },
  { id: 'evening', icon: '🌙', title: 'Kechqurun (19:00)', subtitle: 'Kechki sokin vaqtda tahlil qilish' },
];

export default function Onboarding({ isModal = false, onClose, onSuccess }: OnboardingProps) {
  const navigate = useNavigate();
  const { user, updateUser } = useAuth();

  // 3-step streamlined flow:
  // Step 1: Fan va Imtihon yo'nalishi
  // Step 2: Asosiy maqsad va Tayyorgarlik darajasi
  // Step 3: Kunlik reja (savollar soni) va Eslatma vaqti
  const [step, setStep] = useState<number>(1);
  const [selectedTrack, setSelectedTrack] = useState<string>('milliy_sertifikat');
  const [mainGoal, setMainGoal] = useState<string>('certificate');
  const [level, setLevel] = useState<PrepLevel>('beginner');
  const [goalQuestions, setGoalQuestions] = useState<number>(30);
  const [reminderSlot, setReminderSlot] = useState<ReminderSlot>('evening');
  const [celebrating, setCelebrating] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);

  const trackObj = EXAM_TRACKS.find((t) => t.id === selectedTrack) || EXAM_TRACKS[0];

  const handleSkip = async () => {
    try {
      localStorage.setItem('onboarding_dismissed', 'true');
      localStorage.setItem('grandec_onboarding_done', 'true');
      localStorage.setItem('grand_ed_onboarding_done', 'true');
    } catch {
      /* ignore */
    }

    updateUser({
      ...(user || {}),
      onboarding_completed: true,
    });

    try {
      await api.post('/api/auth/onboarding/', {
        onboarding_completed: true,
        target_exam: selectedTrack || 'milliy_sertifikat',
        active_subject: trackObj.active_subject || 'uzbek',
        goal_questions: goalQuestions,
        daily_goal_minutes: goalQuestions,
      });
    } catch {
      /* ignore */
    }

    if (onClose) onClose();
    if (onSuccess) onSuccess();
    if (!isModal) {
      navigate('/dashboard', { replace: true });
    }
  };

  const handleBack = () => {
    if (celebrating || submitting) return;
    if (step > 1) {
      setStep((s) => s - 1);
      return;
    }
    handleSkip();
  };

  const submitOnboardingPayload = async (payload: Record<string, unknown>) => {
    const endpoints = [
      '/api/v1/users/onboarding/',
      '/v1/users/onboarding/',
      '/api/auth/onboarding/',
      '/auth/onboarding/',
    ];
    for (const ep of endpoints) {
      try {
        await api.post(ep, payload);
        return;
      } catch {
        /* try fallback */
      }
    }
  };

  const handleNextOrFinish = async () => {
    if (submitting || celebrating) return;

    if (step < 3) {
      setStep((s) => s + 1);
      return;
    }

    // Step 3 -> Finish & Celebrate
    setSubmitting(true);
    setCelebrating(true);

    try {
      confetti({
        particleCount: 80,
        spread: 70,
        origin: { y: 0.6 },
        colors: ['#C8922A', '#F59E0B', '#10B981', '#FBBF24'],
      });
    } catch {
      /* ignore */
    }

    const finalSubject: ActiveSubject = trackObj.active_subject;
    const finalExam: string = trackObj.target_exam;
    const selectedGoalObj = QUESTION_GOALS.find((q) => q.count === goalQuestions) || QUESTION_GOALS[1];

    const payload = {
      main_goal: mainGoal,
      active_subject: finalSubject,
      target_exam: finalExam,
      exam_target: finalExam,
      level: level || 'beginner',
      daily_goal_minutes: selectedGoalObj.minutes,
      goal_questions: goalQuestions,
      daily_goal_questions: goalQuestions,
      reminder_slot: reminderSlot || 'evening',
    };

    try {
      localStorage.setItem('active_subject', finalSubject);
      localStorage.setItem('lms_subject', finalSubject);
      localStorage.setItem('landing_subject', finalSubject);
      localStorage.setItem('grand_ed_onboarding_done', 'true');
      localStorage.setItem('grandec_onboarding_done', 'true');
      localStorage.setItem('onboarding_dismissed', 'true');
      localStorage.setItem(
        'grandec_user_plan',
        JSON.stringify({
          ...payload,
          completed_minutes: 0,
          updated_at: new Date().toISOString(),
        }),
      );
      window.dispatchEvent(new CustomEvent('subject-changed', { detail: finalSubject }));
    } catch {
      /* ignore */
    }

    void submitOnboardingPayload(payload);

    updateUser({
      ...(user || {}),
      onboarding_completed: true,
      active_subject: finalSubject,
      exam_target: finalExam,
      target_exam: finalExam,
      level: level || 'beginner',
      daily_goal_minutes: selectedGoalObj.minutes,
      reminder_slot: reminderSlot || 'evening',
      daily_plan_summary: {
        ...((user?.daily_plan_summary as Record<string, unknown>) || {}),
        goal_questions: goalQuestions,
        daily_minutes: selectedGoalObj.minutes,
        target_exam: finalExam,
        level: level || 'beginner',
        reminder_slot: reminderSlot || 'evening',
      },
    });

    await new Promise((resolve) => setTimeout(resolve, 900));

    setSubmitting(false);
    if (onSuccess) onSuccess();
    if (onClose) onClose();
    navigate('/dashboard', { replace: true });
  };

  const progressPercent = celebrating ? 100 : Math.round((step / 3) * 100);

  return (
    <div
      className="onb-root"
      style={{
        minHeight: isModal ? '100%' : '100dvh',
        width: '100%',
        background: 'var(--bg-page, var(--bg))',
        color: 'var(--text-primary, var(--ink))',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '20px 16px 28px',
        boxSizing: 'border-box',
      }}
    >
      <style>{`
        .onb-card {
          width: 100%;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
          padding: 14px 16px;
          border-radius: 14px;
          background: var(--bg-card, var(--card));
          border: 1.5px solid var(--border-default, var(--border));
          color: var(--text-primary, var(--ink));
          text-align: left;
          cursor: pointer;
          transition: transform 0.15s ease, border-color 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
        }
        .onb-card:hover {
          transform: translateY(-1px);
          border-color: rgba(200, 146, 42, 0.65);
        }
        .onb-card.is-selected {
          border: 2px solid #C8922A;
          background: rgba(200, 146, 42, 0.12);
          box-shadow: 0 6px 20px -6px rgba(200, 146, 42, 0.28);
        }
      `}</style>

      {/* TOP HEADER BAR */}
      <header
        style={{
          width: '100%',
          maxWidth: 620,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          {step > 1 ? (
            <button
              type="button"
              onClick={handleBack}
              aria-label="Orqaga"
              title="Orqaga"
              style={{
                width: 40,
                height: 40,
                borderRadius: 12,
                border: '1.5px solid var(--border-default, var(--border))',
                background: 'var(--bg-card, var(--card))',
                color: 'var(--text-primary, var(--ink))',
                fontSize: 18,
                fontWeight: 800,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              &lt;
            </button>
          ) : (
            <div style={{ width: 40 }} />
          )}

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              flexWrap: 'wrap',
              justifyContent: 'center',
            }}
          >
            <span
              style={{
                fontSize: 12,
                fontWeight: 800,
                letterSpacing: '0.08em',
                color: 'var(--text-secondary, var(--muted))',
                textTransform: 'uppercase',
              }}
            >
              {step}-QADAM / 3
            </span>
            <span
              style={{
                fontSize: 11,
                fontWeight: 900,
                letterSpacing: '0.1em',
                padding: '4px 10px',
                borderRadius: 999,
                background: 'rgba(200, 146, 42, 0.15)',
                color: '#C8922A',
                border: '1px solid rgba(200, 146, 42, 0.35)',
              }}
            >
              GRANDEC LMS
            </span>
          </div>

          {/* O'tkazib yuborish (Skip) Button */}
          <button
            type="button"
            onClick={handleSkip}
            aria-label="O‘tkazib yuborish"
            title="O‘tkazib yuborish"
            style={{
              padding: '6px 12px',
              borderRadius: 10,
              border: '1px solid var(--border-default, var(--border))',
              background: 'transparent',
              color: 'var(--text-secondary, var(--muted))',
              fontSize: 12.5,
              fontWeight: 700,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              transition: 'all 0.15s ease',
            }}
          >
            O‘tkazib yuborish ✕
          </button>
        </div>

        {/* PROGRESS BAR */}
        <div
          role="progressbar"
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          style={{
            width: '100%',
            height: 8,
            borderRadius: 999,
            background: 'var(--bg-card-2, rgba(148, 163, 184, 0.2))',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${progressPercent}%`,
              height: '100%',
              borderRadius: 999,
              background: 'linear-gradient(90deg, #C8922A 0%, #F59E0B 70%, #10B981 100%)',
              transition: 'width 0.35s cubic-bezier(0.22, 1, 0.36, 1)',
            }}
          />
        </div>
      </header>

      {/* MAIN CONTENT AREA */}
      <main
        style={{
          width: '100%',
          maxWidth: 620,
          margin: '20px 0',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 18,
          flex: 1,
        }}
      >
        {/* STEP 1: FAN VA IMTIHON */}
        {step === 1 && (
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ textAlign: 'center', marginBottom: 4 }}>
              <h1 style={{ margin: '0 0 6px 0', fontSize: '22px', fontWeight: 800 }}>
                Qaysi yo‘nalishga tayyorlanmoqchisiz?
              </h1>
              <p style={{ margin: 0, fontSize: '13.5px', color: 'var(--text-secondary, var(--muted))' }}>
                O‘zingiz topshiradigan asosiy imtihon yoki fanni tanlang
              </p>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {EXAM_TRACKS.map((t) => {
                const isSelected = selectedTrack === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setSelectedTrack(t.id)}
                    className={`onb-card ${isSelected ? 'is-selected' : ''}`}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{ fontSize: 24 }}>{t.icon}</span>
                      <div>
                        <div style={{ fontWeight: 800, fontSize: 14.5 }}>{t.title}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary, var(--muted))', marginTop: 2 }}>
                          {t.subtitle}
                        </div>
                      </div>
                    </div>
                    {isSelected && <span style={{ color: '#C8922A', fontWeight: 800 }}>✓</span>}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* STEP 2: MAQSAD VA DARAJA */}
        {step === 2 && (
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ textAlign: 'center', marginBottom: 2 }}>
              <h1 style={{ margin: '0 0 6px 0', fontSize: '22px', fontWeight: 800 }}>
                Maqsadingiz va joriy bilim darajangiz
              </h1>
              <p style={{ margin: 0, fontSize: '13.5px', color: 'var(--text-secondary, var(--muted))' }}>
                {trackObj.title} bo‘yicha shaxsiy reja tuzish uchun belgilang
              </p>
            </div>

            {/* Asosiy maqsad */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--ink, #0f172a)' }}>
                Asosiy maqsad
              </label>
              {GOAL_OPTIONS.map((g) => {
                const isSelected = mainGoal === g.id;
                return (
                  <button
                    key={g.id}
                    type="button"
                    onClick={() => setMainGoal(g.id)}
                    className={`onb-card ${isSelected ? 'is-selected' : ''}`}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{ fontSize: 22 }}>{g.icon}</span>
                      <div>
                        <div style={{ fontWeight: 800, fontSize: 14 }}>{g.title}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary, var(--muted))', marginTop: 2 }}>
                          {g.subtitle}
                        </div>
                      </div>
                    </div>
                    {isSelected && <span style={{ color: '#C8922A', fontWeight: 800 }}>✓</span>}
                  </button>
                );
              })}
            </div>

            {/* Tayyorgarlik darajasi */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--ink, #0f172a)' }}>
                Joriy tayyorgarlik darajangiz
              </label>
              {LEVEL_OPTIONS.map((l) => {
                const isSelected = level === l.id;
                return (
                  <button
                    key={l.id}
                    type="button"
                    onClick={() => setLevel(l.id)}
                    className={`onb-card ${isSelected ? 'is-selected' : ''}`}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{ fontSize: 22 }}>{l.icon}</span>
                      <div>
                        <div style={{ fontWeight: 800, fontSize: 14 }}>{l.title}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary, var(--muted))', marginTop: 2 }}>
                          {l.subtitle}
                        </div>
                      </div>
                    </div>
                    {isSelected && <span style={{ color: '#C8922A', fontWeight: 800 }}>✓</span>}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* STEP 3: KUNLIK REJA VA ESLATMA */}
        {step === 3 && (
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ textAlign: 'center', marginBottom: 2 }}>
              <h1 style={{ margin: '0 0 6px 0', fontSize: '22px', fontWeight: 800 }}>
                Kunlik maqsad va shug‘ullanish vaqti
              </h1>
              <p style={{ margin: 0, fontSize: '13.5px', color: 'var(--text-secondary, var(--muted))' }}>
                Muntazamlik — muvaffaqiyat garovi! Har kuni nechta savol yechmoqchisiz?
              </p>
            </div>

            {/* Kunlik savollar */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--ink, #0f172a)' }}>
                Kunlik maqsad
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                {QUESTION_GOALS.map((q) => {
                  const isSelected = goalQuestions === q.count;
                  return (
                    <button
                      key={q.count}
                      type="button"
                      onClick={() => setGoalQuestions(q.count)}
                      className={`onb-card ${isSelected ? 'is-selected' : ''}`}
                      style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 800, fontSize: 14 }}>
                        <span>{q.icon}</span>
                        <span>{q.title}</span>
                      </div>
                      <div style={{ fontSize: 11.5, color: 'var(--text-secondary, var(--muted))' }}>
                        {q.subtitle}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Eslatma vaqti */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--ink, #0f172a)' }}>
                Eslatma vaqti
              </label>
              {REMINDER_OPTIONS.map((r) => {
                const isSelected = reminderSlot === r.id;
                return (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setReminderSlot(r.id)}
                    className={`onb-card ${isSelected ? 'is-selected' : ''}`}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{ fontSize: 22 }}>{r.icon}</span>
                      <div>
                        <div style={{ fontWeight: 800, fontSize: 14 }}>{r.title}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary, var(--muted))', marginTop: 2 }}>
                          {r.subtitle}
                        </div>
                      </div>
                    </div>
                    {isSelected && <span style={{ color: '#C8922A', fontWeight: 800 }}>✓</span>}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </main>

      {/* BOTTOM ACTION BUTTON */}
      <footer style={{ width: '100%', maxWidth: 620, display: 'flex', justifyContent: 'center' }}>
        <button
          type="button"
          onClick={handleNextOrFinish}
          disabled={submitting}
          style={{
            width: '100%',
            height: 50,
            borderRadius: 14,
            border: 'none',
            background: 'linear-gradient(135deg, #C8922A 0%, #F59E0B 100%)',
            color: '#FFFFFF',
            fontSize: 15,
            fontWeight: 800,
            cursor: submitting ? 'not-allowed' : 'pointer',
            opacity: submitting ? 0.75 : 1,
            boxShadow: '0 8px 24px -4px rgba(200, 146, 42, 0.4)',
            transition: 'all 0.15s ease',
          }}
        >
          {submitting
            ? 'Reja tayyorlanmoqda...'
            : step < 3
            ? 'Davom etish →'
            : '🎉 Tayyor! LMS Dashboardga o‘tish'}
        </button>
      </footer>
    </div>
  );
}
