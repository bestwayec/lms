import { useCallback, useEffect, useMemo, useState, useRef, lazy, Suspense } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useLang } from '../i18n/LangContext';
import {
  AuthExpiredError,
  DashboardApi,
  GamificationApi,
  PaymentsApi,
  MockTests,
  type DashboardData,
  type DashboardRecent,
  type DashboardWeakPart,
  type PaymentReceiptItem,
  type StreakInfoResponse,
} from '../lib/api';
import { formatDisplayName, initialsOf } from '../lib/displayName';
import { essayKind, essayStatus, scoreLabel } from '../lib/essays';
import { useSubject } from '../lib/useSubject';
import { daysLeft, useEntitlement, useTier } from '../lib/useTier';
import { Target, KeyRound, Trophy, Settings } from 'lucide-react';
import { hapticImpact, hapticNotify } from '../lib/haptics';
import ReferralCard from '../components/ReferralCard';

const GoalModal = lazy(() => import('../components/GoalModal'));
const OnboardingModal = lazy(() => import('../components/OnboardingModal'));
const DailyBlitzModal = lazy(() => import('../components/DailyBlitzModal'));

const CURATED_RADAR_TOPICS: Record<string, { label: string; percentage: number; needsReview: boolean }[]> = {
  biology: [
    { label: 'Mitoz va Meyoz bosqichlari', percentage: 42, needsReview: true },
    { label: 'Genetika va irsiyat masalalari', percentage: 88, needsReview: false },
    { label: 'Hujayra nafas olishi va ATF sintezi', percentage: 54, needsReview: true },
    { label: 'Evolutsiya va biogeosenoz', percentage: 76, needsReview: false },
  ],
  chemistry: [
    { label: 'Eritmalar konsentratsiyasi va eruvchanlik', percentage: 46, needsReview: true },
    { label: 'Organik kimyo reaksiyalari', percentage: 85, needsReview: false },
    { label: 'Elektroliz va oksidlanish-qaytarilish', percentage: 52, needsReview: true },
    { label: 'Davriy qonun va atom tuzilishi', percentage: 80, needsReview: false },
  ],
  law: [
    { label: 'Konstitutsiyaviy huquq normalari', percentage: 86, needsReview: false },
    { label: 'Jinoyat va maʼmuriy javobgarlik', percentage: 48, needsReview: true },
    { label: 'Mehnat shartnomasi va kafolatlar', percentage: 58, needsReview: true },
    { label: 'Fuqarolik huquqi va shartnomalar', percentage: 79, needsReview: false },
  ],
  uzbek: [
    { label: 'Morfologiya va soʻz yasalishi', percentage: 84, needsReview: false },
    { label: 'Tinish belgilari va murakkab sintaksis', percentage: 45, needsReview: true },
    { label: 'Matn ustida ishlash va tahlil', percentage: 55, needsReview: true },
    { label: 'Leksikologiya va iboralar', percentage: 82, needsReview: false },
  ],
  english: [
    { label: 'Reading: True / False / Not Given', percentage: 48, needsReview: true },
    { label: 'Listening: Section 3 Multiple Choice', percentage: 52, needsReview: true },
    { label: 'Lexical Resource & Collocations', percentage: 82, needsReview: false },
    { label: 'Grammar: Complex Clauses', percentage: 68, needsReview: false },
  ],
};

function getStoredPlan(): Record<string, unknown> {
  try {
    const raw = localStorage.getItem('grandec_user_plan');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') return parsed as Record<string, unknown>;
    }
  } catch {
    /* ignore */
  }
  return {};
}

function resolveTrackBadge(userExamTarget?: string, storedPlan?: Record<string, unknown>, subject?: string): string {
  const target = String(userExamTarget || storedPlan?.target_exam || storedPlan?.exam_target || storedPlan?.target || '');
  const sub = String(storedPlan?.sub_subject || '');
  if (target === 'milliy_sertifikat' || target === 'national_certificate') {
    if (subject === 'biology') return '🧬 Biologiya (Milliy sertifikat & DTM)';
    if (subject === 'chemistry') return '🧪 Kimyo (Milliy sertifikat & DTM)';
    if (subject === 'law') return '⚖️ Huquqshunoslik (Yurisprudensiya)';
    return '🇺🇿 Milliy Sertifikat';
  }
  if (target === 'cefr' || target === 'multilevel') return '🇬🇧 CEFR Multi-level';
  if (target === 'ielts') return '🎓 IELTS Academic';
  if (target === 'attestatsiya' || target === 'attestation') return '📜 Attestatsiya 2026';
  if (target === 'other') return sub ? `📚 ${sub}` : '📚 Umumiy fanlar';
  if (subject === 'biology') return '🧬 Biologiya (Milliy sertifikat & DTM)';
  if (subject === 'chemistry') return '🧪 Kimyo (Milliy sertifikat & DTM)';
  if (subject === 'law') return '⚖️ Huquqshunoslik (Yurisprudensiya)';
  return subject === 'english' ? '🇬🇧 Ingliz tili (CEFR / IELTS)' : '🇺🇿 Ona tili (Milliy sertifikat)';
}

/** Student dashboard: one main action, daily goal, real indicators, recent results, weak parts, goal. */
export default function Dashboard() {
  const { user } = useAuth();
  const { t, lang } = useLang();
  const navigate = useNavigate();
  const subject = useSubject();
  const tier = useTier();
  const entitlement = useEntitlement();

  const [data, setData] = useState<DashboardData | null>(null);
  const [failed, setFailed] = useState(false);
  const [pendingReceipt, setPendingReceipt] = useState<PaymentReceiptItem | null>(null);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [streakData, setStreakData] = useState<StreakInfoResponse | null>(null);
  const [blitzModalOpen, setBlitzModalOpen] = useState(false);
  const [goalModalOpen, setGoalModalOpen] = useState(false);
  const [pinCode, setPinCode] = useState('');
  const [pinBoxes, setPinBoxes] = useState<string[]>(['', '', '', '', '', '']);
  const pinRefs = useRef<(HTMLInputElement | null)[]>([]);
  const [pinBusy, setPinBusy] = useState(false);
  const [pinErr, setPinErr] = useState<string | null>(null);

  const handlePinBoxChange = (idx: number, val: string) => {
    const char = val.slice(-1).toUpperCase();
    const next = [...pinBoxes];
    next[idx] = char;
    setPinBoxes(next);
    setPinCode(next.join(''));
    if (pinErr) setPinErr(null);
    if (char && idx < 5) {
      pinRefs.current[idx + 1]?.focus();
    }
  };

  const handlePinKeyDown = (idx: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !pinBoxes[idx] && idx > 0) {
      pinRefs.current[idx - 1]?.focus();
    }
  };

  const handlePinPaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\s+/g, '').slice(0, 6).toUpperCase();
    const next = [...pinBoxes];
    for (let i = 0; i < 6; i++) {
      next[i] = pasted[i] || '';
    }
    setPinBoxes(next);
    setPinCode(next.join(''));
    if (pinErr) setPinErr(null);
    const focusIdx = Math.min(5, pasted.length);
    pinRefs.current[focusIdx]?.focus();
  };

  const handleJoinByPin = async (e: React.FormEvent) => {
    e.preventDefault();
    const clean = (pinCode || pinBoxes.join('')).replace(/\s+/g, '').toUpperCase();
    if (!clean) return;
    setPinBusy(true);
    setPinErr(null);
    hapticImpact('light');
    try {
      if (clean.toLowerCase().startsWith('group_')) {
        navigate(`/groups/${clean.replace(/group_/i, '')}`);
        return;
      }
      if (/^\d+$/.test(clean)) {
        navigate(`/tests/${clean}`);
        return;
      }
      const res = await MockTests.join(clean);
      if (res && res.attempt_id) {
        hapticNotify('success');
        navigate(`/take/${res.attempt_id}`);
        return;
      }
      navigate(`/tests?code=${encodeURIComponent(clean)}`);
    } catch {
      setPinErr("Bunday kodli test topilmadi");
      hapticNotify('error');
    } finally {
      setPinBusy(false);
    }
  };

  const role = (user?.role || '').toLowerCase();
  const isStudent = !(role === 'teacher' || role === 'admin' || role === 'superadmin' || role === 'center_admin' || user?.is_superuser);

  useEffect(() => {
    if (!isStudent || !user) {
      setOnboardingOpen(false);
      return;
    }
    const done =
      localStorage.getItem('onboarding_dismissed') === 'true' ||
      localStorage.getItem('grandec_onboarding_done') === 'true' ||
      localStorage.getItem('grand_ed_onboarding_done') === 'true' ||
      user.onboarding_completed === true;
    setOnboardingOpen(!done && user.onboarding_completed === false);
  }, [user, isStudent]);

  useEffect(() => {
    let alive = true;
    PaymentsApi.myReceipts()
      .then(({ results }) => alive && setPendingReceipt(results.find((r) => r.status === 'pending') ?? null))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [user?.id]);

  const load = useCallback(() => {
    let alive = true;
    setFailed(false);
    DashboardApi.get(subject)
      .then((d) => alive && setData(d))
      .catch((e) => {
        if (!alive) return;
        if (e instanceof AuthExpiredError) navigate('/login');
        else setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [subject, navigate]);

  useEffect(() => {
    setData(null);
    GamificationApi.streak().then(setStreakData).catch(() => {});
    return load();
  }, [load]);

  const name = formatDisplayName(user?.full_name, user?.email) || t('user_default');
  const days = tier.isPaid && !tier.isAdmin ? daysLeft(entitlement?.expires_at) : null;
  const expiring = days !== null && days <= 5 && entitlement?.source === 'subscription';
  const ind = data?.indicators;
  const hasActivity = Boolean(ind && (ind.tests_taken > 0 || ind.essays.count > 0));

  // Daily Goal calculation
  const storedPlan = useMemo(() => getStoredPlan(), [user?.onboarding_completed, user?.daily_goal_minutes]);
  const trackBadgeLabel = resolveTrackBadge(data?.daily_goal?.target_exam || user?.exam_target || user?.target_exam, storedPlan, subject);

  const dateOf = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(lang) : '');
  const sectionName = (code: string, fallback: string) => t(`omr_section_${code}`, fallback || code);

  const partLabel = (w: DashboardWeakPart) => {
    if (w.label) return w.label;
    return (
      [
        w.section_code ? sectionName(w.section_code, w.section_name) : '',
        w.part ? `${t('rv_part')} ${w.part}` : '',
      ]
        .filter(Boolean)
        .join(', ') + ` (${t(`rv_type_${w.question_type}`, w.question_type)})`
    );
  };

  const weakPracticeUrl = (w: DashboardWeakPart) =>
    `/tests?skill=${encodeURIComponent(w.section_code || '')}&type=${encodeURIComponent(w.question_type || '')}&mode=practice`;

  const recentSummary = (r: DashboardRecent): string => {
    if (r.trial) return `${t('dsh_trial_tag')}: ${r.correct}/${r.total}`;
    if (r.sections.length > 1) {
      return r.sections.map((s) => `${sectionName(s.code, s.name)} ${Math.round(s.score)}/${s.max}`).join(' · ');
    }
    if (r.kind === 'bmb') {
      return `${Math.round(r.percentage)}%${r.grade ? ` · ${t('dsh_grade')} ${r.grade}` : ''}`;
    }
    return `${r.correct}/${r.total}`;
  };

  const indicators: { label: string; value: string; note?: string }[] = [];
  if (ind) {
    indicators.push({ label: t('dsh_ind_tests'), value: String(ind.tests_taken) });
    if (subject === 'english') {
      indicators.push({
        label: t('dsh_ind_listening'),
        value: ind.best_sections.LISTENING != null ? String(ind.best_sections.LISTENING) : '—',
        note: ind.best_sections.LISTENING != null ? t('dsh_ind_of_75') : undefined,
      });
      indicators.push({
        label: t('dsh_ind_reading'),
        value: ind.best_sections.READING != null ? String(ind.best_sections.READING) : '—',
        note: ind.best_sections.READING != null ? t('dsh_ind_of_75') : undefined,
      });
    } else {
      indicators.push({
        label: t('dsh_ind_avg'),
        value: ind.average_percentage != null ? `${Math.round(ind.average_percentage)}%` : '—',
      });
      indicators.push({ label: t('dsh_ind_best_grade'), value: ind.best_grade || '—' });
    }
    indicators.push({
      label: t('dsh_ind_essays'),
      value: String(ind.essays.count),
      note:
        ind.essays.last_score != null && ind.essays.last_max
          ? t('dsh_ind_essay_last').replace('{score}', String(Math.round(ind.essays.last_score))).replace('{max}', String(ind.essays.last_max))
          : undefined,
    });
  }

  const rawFirstName = user?.first_name || name.split(' ')[0] || 'O‘quvchi';
  const firstName = rawFirstName.charAt(0).toUpperCase() + rawFirstName.slice(1);
  const streakDays = streakData?.current_streak ?? data?.indicators?.streak ?? 1;

  const goalQuestions = useMemo(() => {
    const fromApi = Number(data?.daily_goal?.goal_questions);
    if (Number.isFinite(fromApi) && fromApi > 0) return fromApi;
    const fromSummary = (user?.daily_plan_summary as Record<string, unknown> | undefined)?.goal_questions;
    if (Number.isFinite(Number(fromSummary)) && Number(fromSummary) > 0) return Number(fromSummary);
    const fromStored = Number(storedPlan.goal_questions || storedPlan.daily_goal_questions);
    if (Number.isFinite(fromStored) && fromStored > 0) return fromStored;
    const fromMins = Number(user?.daily_goal_minutes);
    if (Number.isFinite(fromMins) && fromMins > 0) return fromMins;
    return 30;
  }, [data?.daily_goal?.goal_questions, user?.daily_plan_summary, storedPlan, user?.daily_goal_minutes]);

  const completedQuestions = useMemo(() => {
    const fromApi = Number(data?.daily_goal?.completed_questions);
    if (Number.isFinite(fromApi)) return fromApi;
    return 0;
  }, [data?.daily_goal?.completed_questions]);

  const questionsProgressPct = Math.min(
    100,
    Math.round((completedQuestions / Math.max(1, goalQuestions)) * 100)
  );


  const radarTopics = useMemo(() => {
    if (data?.weak_parts && data.weak_parts.length > 0) {
      return data.weak_parts.map((w) => {
        const pct = w.total ? Math.round(((w.correct || 0) / w.total) * 100) : 42;
        return {
          label: partLabel(w),
          percentage: pct,
          needsReview: pct < 60,
          practiceUrl: weakPracticeUrl(w),
        };
      });
    }
    const curated = CURATED_RADAR_TOPICS[subject] || CURATED_RADAR_TOPICS.biology;
    return curated.map((c) => ({
      ...c,
      practiceUrl: `/tests?skill=${encodeURIComponent(c.label)}&mode=practice`,
    }));
  }, [data?.weak_parts, subject, t, lang]);

  const now = new Date();
  const monthNames = ['YANVAR', 'FEVRAL', 'MART', 'APREL', 'MAY', 'IYUN', 'IYUL', 'AVGUST', 'SENTYABR', 'OKTYABR', 'NOYABR', 'DEKABR'];
  const todayBadgeText = `BOSHQARUV • ${now.getDate()}-${monthNames[now.getMonth()]}`;
  const currentHour = now.getHours();
  const greetingPrefix = currentHour < 11 ? 'Xayrli tong' : currentHour < 18 ? 'Xayrli kun' : 'Xayrli kech';
  const targetGoalText = trackBadgeLabel ? `${trackBadgeLabel} / ${subject === 'english' ? 'IELTS 7.0' : 'A+'}` : (subject === 'english' ? 'C1 / IELTS 7.0' : subject === 'chemistry' ? 'Milliy Sertifikat A+' : subject === 'biology' ? 'Milliy Sertifikat A+' : subject === 'law' ? 'Huquqshunoslik A+' : 'Ona tili A+');
  const remainingQuestions = Math.max(0, goalQuestions - completedQuestions);

  const ringRadius = 38;
  const ringCircumference = 2 * Math.PI * ringRadius;
  const ringOffset = ringCircumference - (Math.min(100, Math.max(0, questionsProgressPct)) / 100) * ringCircumference;

  const weekDays = [
    { label: 'Du', active: true },
    { label: 'Se', active: true },
    { label: 'Ch', active: streakDays >= 3 },
    { label: 'Pa', active: streakDays >= 4 },
    { label: 'Ju', active: streakDays >= 5 },
    { label: 'Sh', active: streakDays >= 6 },
    { label: 'Ya', active: streakDays >= 7 },
  ];

  const radarData = useMemo(() => {
    const categories = [
      { name: 'Grammar', score: 75 },
      { name: 'Reading', score: 64 },
      { name: 'Listening', score: 80 },
      { name: 'Writing', score: 58 },
      { name: 'Vocabulary', score: 71 },
    ];
    const cx = 100;
    const cy = 100;
    const r = 68;
    const points = categories.map((cat, i) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
      const dist = (cat.score / 100) * r;
      return {
        x: cx + dist * Math.cos(angle),
        y: cy + dist * Math.sin(angle),
        labelX: cx + (r + 18) * Math.cos(angle),
        labelY: cy + (r + 14) * Math.sin(angle),
        name: cat.name,
        score: cat.score,
      };
    });
    const polygonStr = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    return { categories, points, polygonStr };
  }, []);

  const userInitials = initialsOf(user?.full_name, user?.email) || 'KR';

  return (
    <div className="dsh max-w-[1440px] mx-auto w-full px-2 sm:px-4 py-2">
      {/* ======================================================================
          GRANDEC 2.0 BENTO GRID (2x2 Layout)
          ====================================================================== */}
      {isStudent && (
        <section className="bento-grid grid grid-cols-1 lg:grid-cols-2 gap-5 mb-8" aria-label="Bento Boshqaruv Paneli">
          {/* BENTO BOX 1: Yuqori Chap — Katta Salomlashuv va Kunlik Reja Kartasi */}
          <div className="bento-card p-5 sm:p-6 flex flex-col justify-between relative overflow-hidden">
            {/* Header row: badge and settings icon */}
            <div className="flex items-center justify-between mb-4">
              <span className="pill-badge font-mono text-[11px] uppercase tracking-wider text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/30">
                {todayBadgeText}
              </span>
              <button
                type="button"
                onClick={() => {
                  hapticImpact('light');
                  setGoalModalOpen(true);
                }}
                className="w-8 h-8 rounded-xl flex items-center justify-center text-slate-400 hover:text-slate-100 hover:bg-slate-800/50 transition-colors"
                title="Maqsad sozlamalari"
                aria-label="Maqsad sozlamalari"
              >
                <Settings size={17} />
              </button>
            </div>

            {/* Greeting and Goal Subtitle */}
            <div className="mb-5">
              <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight leading-snug">
                {greetingPrefix}, {firstName}!
              </h1>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                <span className="text-xs sm:text-sm font-semibold text-slate-500 dark:text-slate-400">
                  Maqsadingiz:
                </span>
                <span className="text-xs sm:text-sm font-bold text-blue-600 dark:text-blue-400 px-2.5 py-0.5 rounded-md bg-blue-500/10 border border-blue-500/20">
                  {targetGoalText}
                </span>
              </div>
            </div>

            {/* Center Section: Progress Ring + Streak & CTA */}
            <div className="grid grid-cols-1 sm:grid-cols-12 gap-5 items-center pt-3 border-t border-slate-200 dark:border-slate-800">
              {/* Circular SVG Progress Ring */}
              <div className="sm:col-span-5 flex items-center justify-center">
                <div className="relative flex items-center justify-center w-28 h-28">
                  <svg className="w-28 h-28 transform -rotate-90" viewBox="0 0 100 100">
                    <circle
                      cx="50"
                      cy="50"
                      r={ringRadius}
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="8"
                      className="text-slate-200 dark:text-slate-800"
                    />
                    <circle
                      cx="50"
                      cy="50"
                      r={ringRadius}
                      fill="none"
                      stroke="url(#ringGold)"
                      strokeWidth="8"
                      strokeDasharray={ringCircumference}
                      strokeDashoffset={ringOffset}
                      strokeLinecap="round"
                      className="transition-all duration-700 ease-out"
                    />
                    <defs>
                      <linearGradient id="ringGold" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#F59E0B" />
                        <stop offset="100%" stopColor="#D97706" />
                      </linearGradient>
                    </defs>
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                    <span className="font-mono font-extrabold text-sm text-slate-900 dark:text-white leading-none">
                      {completedQuestions}/{goalQuestions}
                    </span>
                    <span className="text-[10px] text-slate-500 dark:text-slate-400 font-medium mt-0.5">
                      savol bugun
                    </span>
                  </div>
                </div>
              </div>

              {/* Text, Week Flames, and Golden CTA */}
              <div className="sm:col-span-7 flex flex-col justify-between">
                <p className="text-xs font-medium text-slate-600 dark:text-slate-300 mb-2.5">
                  <span className="font-bold text-amber-600 dark:text-amber-400">{remainingQuestions} ta savol qoldi</span> — bugungi seriyani saqlab qolish uchun rejani bajaring.
                </p>

                {/* Hafta kunlari olovchalari */}
                <div className="flex items-center gap-1.5 mb-3.5">
                  {weekDays.map((d) => (
                    <div
                      key={d.label}
                      className={`flex flex-col items-center justify-center w-7 h-9 rounded-lg border text-[10px] font-bold transition-all ${
                        d.active
                          ? 'border-amber-500/40 bg-amber-500/15 text-amber-500 shadow-sm shadow-amber-500/10'
                          : 'border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-900/60 text-slate-400'
                      }`}
                    >
                      <span>{d.label}</span>
                      <span className="text-[11px] leading-none mt-0.5">{d.active ? '🔥' : '·'}</span>
                    </div>
                  ))}
                </div>

                <Link
                  to={data?.resume?.route || '/tests'}
                  className="bento-btn bento-btn-gold text-xs h-10 w-full sm:w-auto font-bold tracking-tight inline-flex items-center justify-center gap-2"
                >
                  <span>Rejani davom ettirish →</span>
                </Link>
              </div>
            </div>
          </div>

          {/* BENTO BOX 2: Yuqori O'ng — 2 ta Ixcham Karta Ustma-ust */}
          <div className="flex flex-col gap-5">
            {/* Yuqori qism — "TEZKOR KIRISH • Test kodini kiriting" */}
            <div className="bento-card p-5 flex flex-col justify-between flex-1">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <KeyRound size={16} className="text-indigo-600 dark:text-indigo-400" />
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 font-mono">
                    TEZKOR KIRISH • Test kodini kiriting
                  </span>
                </div>
                <p className="text-xs text-slate-600 dark:text-slate-400 mb-3.5">
                  Ustoz yoki markaz bergan 6 xonali MOCK yoki PIN kodni kiriting
                </p>
              </div>

              <form onSubmit={handleJoinByPin} className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
                {/* 6 ta alohida katakchali PIN-kod Inputi */}
                <div className="flex items-center justify-between gap-1.5 flex-1">
                  {[0, 1, 2, 3, 4, 5].map((idx) => {
                    const char = pinBoxes[idx] || '';
                    return (
                      <input
                        key={idx}
                        ref={(el) => {
                          pinRefs.current[idx] = el;
                        }}
                        type="text"
                        maxLength={1}
                        value={char}
                        onChange={(e) => handlePinBoxChange(idx, e.target.value)}
                        onKeyDown={(e) => handlePinKeyDown(idx, e)}
                        onPaste={handlePinPaste}
                        aria-label={`PIN raqam ${idx + 1}`}
                        placeholder="•"
                        disabled={pinBusy}
                        className="w-10 sm:w-11 h-11 text-center font-bold text-base rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none uppercase font-mono transition-all"
                      />
                    );
                  })}
                </div>
                <button
                  type="submit"
                  disabled={pinBusy || !(pinCode || pinBoxes.join('')).trim()}
                  className="bento-btn bento-btn-indigo shrink-0 text-xs font-bold h-11 px-5"
                >
                  <span>{pinBusy ? '…' : '🚀 Boshlash'}</span>
                </button>
              </form>
              {pinErr && (
                <p className="text-xs text-rose-500 font-bold mt-2">⚠️ {pinErr}</p>
              )}
            </div>

            {/* Pastki qism — "⚡ Kunlik Blits (60 soniya ichida 5 ta savol)" */}
            <div
              className="bento-card p-5 flex flex-col justify-between flex-1 border relative overflow-hidden"
              style={{
                borderColor: 'rgba(251, 191, 36, 0.4)',
                background: 'linear-gradient(135deg, rgba(251, 191, 36, 0.05) 0%, rgba(217, 119, 6, 0.08) 100%)',
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-extrabold text-amber-600 dark:text-amber-400 tracking-wide uppercase">
                  ⚡ Kunlik Blits (60 soniya ichida 5 ta savol)
                </span>
                <span className="pill-badge text-[11px] font-mono font-bold" style={{ borderColor: 'rgba(251, 191, 36, 0.4)', background: 'rgba(251, 191, 36, 0.2)', color: '#d97706' }}>
                  +25 XP
                </span>
              </div>
              <p className="text-xs text-slate-600 dark:text-slate-300 mb-4 font-medium">
                Vaqtga qarshi tezkor sinov — barcha savollarga to‘g‘ri javob berib, olovli seriyangizni mustahkamlang!
              </p>
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => {
                    hapticImpact('medium');
                    setBlitzModalOpen(true);
                  }}
                  className="bento-btn bento-btn-gold text-xs h-9 px-4 font-bold"
                >
                  <span>Boshlash →</span>
                </button>
              </div>
            </div>
          </div>

          {/* BENTO BOX 3: Pastki Chap — "TAHLIL • AI Zaif mavzular radari" */}
          <div className="bento-card p-5 sm:p-6 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Target size={17} className="text-indigo-600 dark:text-indigo-400" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 font-mono">
                  TAHLIL • AI Zaif mavzular radari
                </h2>
              </div>
              <Link to="/results" className="text-xs font-bold text-amber-600 dark:text-amber-400 hover:underline">
                To‘liq tahlil →
              </Link>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-12 gap-5 items-center">
              {/* 5-burchakli SVG Spider/Radar Chart */}
              <div className="sm:col-span-6 flex items-center justify-center">
                <div className="w-52 h-52 relative flex items-center justify-center">
                  <svg className="w-full h-full" viewBox="0 0 200 200">
                    <defs>
                      <linearGradient id="spiderFill" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#6366F1" stopOpacity="0.45" />
                        <stop offset="100%" stopColor="#4F46E5" stopOpacity="0.15" />
                      </linearGradient>
                    </defs>
                    {/* Concentric Pentagons */}
                    {[0.25, 0.5, 0.75, 1.0].map((scale) => {
                      const pts = [0, 1, 2, 3, 4]
                        .map((i) => {
                          const a = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
                          const x = 100 + 68 * scale * Math.cos(a);
                          const y = 100 + 68 * scale * Math.sin(a);
                          return `${x.toFixed(1)},${y.toFixed(1)}`;
                        })
                        .join(' ');
                      return (
                        <polygon
                          key={scale}
                          points={pts}
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1"
                          className="text-slate-200 dark:text-slate-800"
                        />
                      );
                    })}

                    {/* Spokes */}
                    {[0, 1, 2, 3, 4].map((i) => {
                      const a = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
                      const x = 100 + 68 * Math.cos(a);
                      const y = 100 + 68 * Math.sin(a);
                      return (
                        <line
                          key={i}
                          x1="100"
                          y1="100"
                          x2={x}
                          y2={y}
                          stroke="currentColor"
                          strokeWidth="1"
                          className="text-slate-200 dark:text-slate-800"
                        />
                      );
                    })}

                    {/* Data Polygon */}
                    <polygon
                      points={radarData.polygonStr}
                      fill="url(#spiderFill)"
                      stroke="#6366F1"
                      strokeWidth="2.5"
                    />

                    {/* Vertices Dots & Labels */}
                    {radarData.points.map((p, idx) => (
                      <g key={idx}>
                        <circle cx={p.x} cy={p.y} r="3.5" fill="#6366F1" stroke="#ffffff" strokeWidth="1.5" />
                        <text
                          x={p.labelX}
                          y={p.labelY}
                          textAnchor="middle"
                          dominantBaseline="central"
                          className="text-[9px] font-bold fill-slate-700 dark:fill-slate-300 font-mono"
                        >
                          {p.name}
                        </text>
                      </g>
                    ))}
                  </svg>
                </div>
              </div>

              {/* 3 ta zaif mavzu qatori */}
              <div className="sm:col-span-6 space-y-3">
                {radarTopics.slice(0, 3).map((item) => (
                  <div key={item.label} className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <span className="font-bold text-slate-800 dark:text-slate-200 truncate max-w-[180px]">{item.label}</span>
                      <span className="font-mono font-bold text-rose-500">{item.percentage}%</span>
                    </div>
                    <div className="w-full h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden mb-2">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-rose-500 to-amber-500"
                        style={{ width: `${item.percentage}%` }}
                      />
                    </div>
                    <div className="flex justify-end">
                      <Link
                        to={item.practiceUrl}
                        className="text-[11px] font-bold text-amber-600 dark:text-amber-400 hover:underline inline-flex items-center gap-1"
                      >
                        <span>🎯 Xatoni yopish</span>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* BENTO BOX 4: Pastki O'ng — "GURUH • Haftalik podium" */}
          <div className="bento-card p-5 sm:p-6 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Trophy size={17} className="text-amber-500" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 font-mono">
                  GURUH • Haftalik podium
                </h2>
              </div>
              <Link to="/groups" className="text-xs font-bold text-amber-600 dark:text-amber-400 hover:underline">
                Batafsil →
              </Link>
            </div>

            {/* 3D Vizual Podium Ustunlari */}
            <div className="flex items-end justify-center gap-3 sm:gap-6 my-auto pt-6 pb-2">
              {/* 2-o'rin (Kumush ustun) */}
              <div className="flex flex-col items-center">
                <div className="w-9 h-9 rounded-full bg-slate-300 dark:bg-slate-700 text-slate-800 dark:text-white font-bold text-xs flex items-center justify-center border-2 border-slate-400 mb-1.5 shadow-sm">
                  SA
                </div>
                <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 truncate max-w-[70px]">Sardor A.</span>
                <span className="text-[10px] font-mono text-slate-500 dark:text-slate-400 mb-1">264 b.</span>
                <div
                  className="w-16 sm:w-20 rounded-t-xl flex flex-col items-center justify-center font-black text-lg text-white"
                  style={{
                    height: '80px',
                    background: 'linear-gradient(180deg, #94A3B8 0%, #475569 100%)',
                    boxShadow: '0 8px 16px -4px rgba(71, 85, 105, 0.4)',
                  }}
                >
                  2
                </div>
              </div>

              {/* 1-o'rin (Oltin ustun) */}
              <div className="flex flex-col items-center">
                <span className="text-lg animate-bounce leading-none mb-1">👑</span>
                <div className="w-11 h-11 rounded-full bg-gradient-to-tr from-amber-500 to-yellow-300 text-slate-950 font-black text-sm flex items-center justify-center border-2 border-yellow-200 mb-1.5 shadow-md shadow-amber-500/30">
                  MR
                </div>
                <span className="text-[11px] font-extrabold text-amber-600 dark:text-amber-400 truncate max-w-[80px]">Madina R.</span>
                <span className="text-[10px] font-mono font-bold text-amber-600 dark:text-amber-400 mb-1">285 b.</span>
                <div
                  className="w-20 sm:w-24 rounded-t-xl flex flex-col items-center justify-center font-black text-2xl text-slate-950"
                  style={{
                    height: '110px',
                    background: 'linear-gradient(180deg, #F59E0B 0%, #B45309 100%)',
                    boxShadow: '0 10px 24px -4px rgba(245, 158, 11, 0.5)',
                  }}
                >
                  1
                </div>
              </div>

              {/* 3-o'rin (Bronza ustun) */}
              <div className="flex flex-col items-center">
                <div className="w-9 h-9 rounded-full bg-amber-800 text-amber-100 font-bold text-xs flex items-center justify-center border-2 border-amber-700 mb-1.5 shadow-sm">
                  JK
                </div>
                <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 truncate max-w-[70px]">Javohir K.</span>
                <span className="text-[10px] font-mono text-slate-500 dark:text-slate-400 mb-1">251 b.</span>
                <div
                  className="w-16 sm:w-20 rounded-t-xl flex flex-col items-center justify-center font-black text-lg text-amber-100"
                  style={{
                    height: '60px',
                    background: 'linear-gradient(180deg, #B45309 0%, #78350F 100%)',
                    boxShadow: '0 6px 14px -4px rgba(180, 83, 9, 0.4)',
                  }}
                >
                  3
                </div>
              </div>
            </div>

            {/* Pastki qismda foydalanuvchining o'z qatori */}
            <div className="mt-3 p-3 rounded-xl border border-amber-500/30 bg-amber-500/10 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 truncate">
                <span className="w-6 h-6 rounded-full bg-amber-500 text-slate-950 font-bold text-[10px] flex items-center justify-center shrink-0">
                  {userInitials}
                </span>
                <span className="font-semibold text-slate-900 dark:text-white truncate">
                  <b className="text-amber-600 dark:text-amber-400">{userInitials} • Siz</b> — 247 ball <span className="text-slate-400">|</span> 3-o‘ringa chiqishga 4 ball qoldi!
                </span>
              </div>
              <Link to="/groups" className="font-bold text-amber-600 dark:text-amber-400 hover:underline shrink-0 ml-2">
                [To‘liq →]
              </Link>
            </div>
          </div>
        </section>
      )}

      {pendingReceipt && (
        <div className="dsh-banner" role="status">
          <span>
            <b>{t('dsh_receipt_title')}</b> · {pendingReceipt.plan.toUpperCase()}
          </span>
          <Link to="/subscribe" className="ui-btn ui-btn--sm">
            {t('dsh_receipt_view')}
          </Link>
        </div>
      )}
      {expiring && days !== null && (
        <div className="dsh-banner" role="status">
          <span>{t('dsh_expiry').replace('{n}', String(days))}</span>
          <Link to="/subscribe" className="ui-btn ui-btn--sm">
            {t('dsh_expiry_renew')}
          </Link>
        </div>
      )}

      {failed && (
        <div className="dsh-card dsh-empty" role="alert">
          <p>{t('dsh_error')}</p>
          <button type="button" className="ui-btn" onClick={() => load()}>
            {t('error_retry')}
          </button>
        </div>
      )}

      {/* Structured Multi-Card Shimmer Skeleton */}
      {!data && !failed && (
        <div className="dsh-skeleton-grid" aria-busy="true" aria-label="Yuklanmoqda">
          {/* Hero Skeleton */}
          <div className="dsh-skeleton" style={{ padding: 20, minHeight: 88, display: 'grid', gap: 10 }}>
            <div className="dsh-skeleton-line" style={{ width: '48%', height: 18 }} />
            <div className="dsh-skeleton-line" style={{ width: '75%', height: 12 }} />
          </div>

          {/* 4 Metric Card Skeletons */}
          <div className="dsh-stats">
            {[0, 1, 2, 3].map((idx) => (
              <div key={idx} className="dsh-skeleton" style={{ padding: 16, minHeight: 84, display: 'grid', gap: 8 }}>
                <div className="dsh-skeleton-line" style={{ width: '55%', height: 12 }} />
                <div className="dsh-skeleton-line" style={{ width: '40%', height: 26 }} />
              </div>
            ))}
          </div>

          {/* 2 Panel Skeletons */}
          <div className="dsh-skeleton-panels">
            {[0, 1].map((idx) => (
              <div key={idx} className="dsh-skeleton" style={{ padding: 18, minHeight: 150, display: 'grid', gap: 12 }}>
                <div className="dsh-skeleton-line" style={{ width: '42%', height: 16 }} />
                <div className="dsh-skeleton-line" style={{ width: '90%', height: 14 }} />
                <div className="dsh-skeleton-line" style={{ width: '82%', height: 14 }} />
                <div className="dsh-skeleton-line" style={{ width: '65%', height: 14 }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {data && !hasActivity && !failed && (
        <section className="dsh-card dsh-empty">
          <h2>{t('dsh_empty_title')}</h2>
          <p>{t(subject === 'english' ? 'dsh_empty_english' : 'dsh_empty_uzbek')}</p>
        </section>
      )}

      {data && hasActivity && (
        <>
          <section className="dsh-stats" aria-label={t('dsh_ind_tests')}>
            {indicators.map((i) => (
              <div key={i.label} className="dsh-stat">
                <span className="dsh-stat__label">{i.label}</span>
                <strong className="dsh-stat__value">{i.value}</strong>
                {i.note && <span className="dsh-stat__note">{i.note}</span>}
              </div>
            ))}
          </section>

          {data.recent.length > 0 && (
            <section className="dsh-card">
              <div className="dsh-card__head">
                <h2>{t('dsh_recent_title')}</h2>
                <Link to="/results">{t('dsh_recent_all')}</Link>
              </div>
              <ul className="dsh-list">
                {data.recent.map((r) => (
                  <li key={r.result_id}>
                    <div className="dsh-list__main">
                      <strong>{r.title}</strong>
                      <span>{recentSummary(r)}</span>
                      <small>{dateOf(r.finished_at)}</small>
                    </div>
                    <Link to={`/results/${r.result_id}`} className="ui-btn ui-btn--sm">
                      {t('details')}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {data.goal && (
            <section className="dsh-card">
              <div className="dsh-card__head">
                <h2>{t('dsh_goal_title')}</h2>
              </div>
              <p className="dsh-goal">
                <b>{t('dsh_goal_target').replace('{target}', data.goal.target)}</b>
                <span>
                  {data.goal.current
                    ? t('dsh_goal_current').replace('{current}', data.goal.current)
                    : t('dsh_goal_none')}
                </span>
                {data.goal.reached === true && <span className="dsh-goal__ok">{t('dsh_goal_reached')}</span>}
                {data.goal.reached === false && <span>{t('dsh_goal_gap')}</span>}
              </p>
            </section>
          )}
        </>
      )}

      {data && isStudent && !hasActivity && (data.recommended_practice || []).length > 0 && (
        <section className="dsh-card">
          <div className="dsh-card__head">
            <h2>{t('dsh_weak_title')}</h2>
            <small>Yo&apos;nalishingiz bo&apos;yicha tavsiya etilgan mashqlar</small>
          </div>
          <ul className="dsh-list">
            {(data.recommended_practice || []).map((w) => {
              const targetUrl = weakPracticeUrl(w);
              return (
                <li
                  key={`${w.section_code}|${w.part}|${w.question_type}`}
                  className="dsh-weak-item"
                  onClick={() => navigate(targetUrl)}
                >
                  <div className="dsh-list__main">
                    <strong>{partLabel(w)}</strong>
                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                      Diagnostik mashq · Bo&apos;lim bo&apos;yicha amaliyot
                    </span>
                  </div>
                  <Link
                    to={targetUrl}
                    className="dsh-weak-pill"
                    onClick={(e) => e.stopPropagation()}
                  >
                    🎯 Mashq qilish →
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {data && isStudent && (
        <section className="dsh-card">
          <div className="dsh-card__head">
            <h2>{t('dsh_essays_title')}</h2>
            <Link to="/essays">{t('dsh_essays_all')}</Link>
          </div>
          {data.indicators.essays.recent.length === 0 ? (
            <div className="dsh-empty-row">
              <p>{t('dsh_essays_empty')}</p>
              <Link to="/essays" className="ui-btn ui-btn--sm">
                {t('es_write')}
              </Link>
            </div>
          ) : (
            <ul className="dsh-list">
              {data.indicators.essays.recent.map((e) => {
                const st = essayStatus(e.status);
                const href = st === 'draft' && e.topic_id ? `/essays/write/${e.topic_id}` : `/essays/result/${e.id}`;
                return (
                  <li key={e.id}>
                    <div className="dsh-list__main">
                      <strong className="clamp-2">{e.title || t('es_untitled')}</strong>
                      <span>
                        {t(`es_kind_${essayKind(e)}`)} · {t(`es_status_${st}`)}
                        {st === 'graded' && scoreLabel(e, t) ? ` · ${scoreLabel(e, t)}` : ''}
                      </span>
                    </div>
                    <Link to={href} className="ui-btn ui-btn--sm">
                      {t('details')}
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}

      {isStudent && <ReferralCard variant="compact" />}

      {onboardingOpen && (
        <Suspense fallback={null}>
          <OnboardingModal isOpen={onboardingOpen} onClose={() => setOnboardingOpen(false)} onSuccess={() => setOnboardingOpen(false)} />
        </Suspense>
      )}

      {blitzModalOpen && (
        <Suspense fallback={null}>
          <DailyBlitzModal
            isOpen={blitzModalOpen}
            onClose={() => setBlitzModalOpen(false)}
            subject={subject}
            onCompleted={() => {
              GamificationApi.streak().then(setStreakData).catch(() => {});
              load();
            }}
          />
        </Suspense>
      )}

      {goalModalOpen && (
        <Suspense fallback={null}>
          <GoalModal
            isOpen={goalModalOpen}
            onClose={() => setGoalModalOpen(false)}
            onSaved={() => load()}
            currentExam={data?.daily_goal?.target_exam || user?.target_exam || user?.exam_target}
            currentGrade={data?.daily_goal?.target_grade || user?.target_grade}
            currentQuestions={goalQuestions}
          />
        </Suspense>
      )}
    </div>
  );
}
