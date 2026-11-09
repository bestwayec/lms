import { useCallback, useEffect, useMemo, useState } from 'react';
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
import { formatDisplayName } from '../lib/displayName';
import { essayKind, essayStatus, scoreLabel } from '../lib/essays';
import { useSubject } from '../lib/useSubject';
import { daysLeft, useEntitlement, useTier } from '../lib/useTier';
import OnboardingModal from '../components/OnboardingModal';
import PlanBadge from '../components/PlanBadge';
import { Zap, Target, Flame, ArrowRight, ChevronRight, KeyRound, Award, Trophy } from 'lucide-react';
import { hapticSelect, hapticImpact, hapticNotify } from '../lib/haptics';
import ReferralCard from '../components/ReferralCard';

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
  const [pinCode, setPinCode] = useState('');
  const [pinBusy, setPinBusy] = useState(false);
  const [pinErr, setPinErr] = useState<string | null>(null);

  const handleJoinByPin = async (e: React.FormEvent) => {
    e.preventDefault();
    const clean = pinCode.trim();
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
    } catch (err: unknown) {
      setPinErr(err instanceof Error ? err.message : "Kiritilgan kod bo'yicha test topilmadi");
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
  const goalMinutes = useMemo(() => {
    const fromApi = Number(data?.daily_goal?.goal_minutes);
    if (Number.isFinite(fromApi) && fromApi > 0) return fromApi;
    const fromUser = Number(user?.daily_goal_minutes || (user?.daily_plan_summary as Record<string, unknown> | undefined)?.daily_minutes);
    if (Number.isFinite(fromUser) && fromUser > 0) return fromUser;
    const fromLocal = Number(storedPlan.daily_goal_minutes || storedPlan.daily_minutes);
    if (Number.isFinite(fromLocal) && fromLocal > 0) return fromLocal;
    return 15;
  }, [data?.daily_goal?.goal_minutes, user?.daily_goal_minutes, user?.daily_plan_summary, storedPlan]);

  const completedMinutes = useMemo(() => {
    const fromApi = Number(data?.daily_goal?.completed_minutes);
    const todayStr = new Date().toDateString();
    let mins = 0;
    if (data?.recent) {
      for (const r of data.recent) {
        if (r.finished_at && new Date(r.finished_at).toDateString() === todayStr) {
          mins += 15;
        }
      }
    }
    if (data?.indicators?.essays?.recent) {
      for (const e of data.indicators.essays.recent) {
        if (e.updated_at && new Date(e.updated_at).toDateString() === todayStr) {
          mins += 10;
        }
      }
    }
    const fromSummary = Number((user?.daily_plan_summary as Record<string, unknown> | undefined)?.completed_minutes || storedPlan.completed_minutes || 0);
    return Math.max(
      Number.isFinite(fromApi) ? fromApi : 0,
      mins,
      Number.isFinite(fromSummary) ? fromSummary : 0,
    );
  }, [data, user?.daily_plan_summary, storedPlan]);

  const dailyProgressPct = Math.min(100, Math.round((completedMinutes / Math.max(1, goalMinutes)) * 100));
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

  const firstName = user?.first_name || name.split(' ')[0] || 'O‘quvchi';
  const streakDays = streakData?.current_streak ?? data?.indicators?.streak ?? 1;
  const goalQuestions = 20;
  const completedQuestions = Math.min(
    goalQuestions,
    Math.max(12, Math.round((completedMinutes / Math.max(1, goalMinutes)) * goalQuestions))
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

  return (
    <div className="dsh">
      {/* 1. HERO STREAK CARD */}
      <section
        className="dsh-hero-streak rounded-2xl p-4 md:p-6 mb-5 border transition-all"
        style={{
          background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.92) 100%)',
          borderColor: 'rgba(245, 158, 11, 0.3)',
          boxShadow: '0 10px 32px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.08)',
        }}
        aria-label="Bugungi Maqsad va Olovli Zanjir"
      >
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
          <div>
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span className="text-xs font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider bg-amber-500/15 text-amber-400 border border-amber-500/30 inline-flex items-center gap-1.5 shadow-[0_0_10px_rgba(245,158,11,0.2)]">
                <Flame size={14} className="text-amber-400 animate-pulse" />
                <span>{streakDays} kunlik olovdasiz</span>
              </span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                {trackBadgeLabel}
              </span>
              <PlanBadge variant="chip" />
            </div>

            <h1 className="text-xl md:text-2xl font-extrabold text-white tracking-tight leading-snug">
              Bugungi kuningiz unumli o&apos;tsin, {firstName}! 🔥
            </h1>
            <p className="text-xs md:text-sm text-slate-300 mt-1 font-medium">
              <span className="text-amber-400 font-bold">{streakDays} kunlik olovdasiz.</span> BMB sertifikatiga yana 1 qadam qoldi!
            </p>
          </div>

          {/* Quick CTA or Resume */}
          {isStudent && (
            <div className="flex items-center gap-2 shrink-0">
              {data?.resume ? (
                <Link
                  to={data.resume.route}
                  className="w-full md:w-auto inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl font-bold text-sm bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 hover:from-amber-400 hover:to-amber-500 shadow-lg shadow-amber-500/25 active:scale-95 transition-all"
                >
                  <span>{t('dsh_resume', 'Davom ettirish')}</span>
                  <ArrowRight size={16} />
                </Link>
              ) : (
                <Link
                  to="/tests"
                  className="w-full md:w-auto inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl font-bold text-sm bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 hover:from-amber-400 hover:to-amber-500 shadow-lg shadow-amber-500/25 active:scale-95 transition-all"
                >
                  <span>{t('dsh_start_mock', 'Test boshlash')}</span>
                  <ArrowRight size={16} />
                </Link>
              )}
            </div>
          )}
        </div>

        {/* Daily Goal Progress Bar */}
        {isStudent && (
          <div className="pt-3 border-t border-slate-700/60">
            <div className="flex items-center justify-between text-xs font-semibold mb-2 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="text-slate-200">
                  🎯 Bugungi maqsad: <b className="text-amber-400 text-sm">{completedQuestions}/{goalQuestions}</b> ta savol yechildi
                </span>
                <span className="text-slate-400 font-normal">
                  ({dailyProgressPct}%)
                </span>
              </div>
              <Link
                to="/onboarding"
                className="text-amber-400/90 hover:text-amber-300 text-xs flex items-center gap-1 transition-colors"
              >
                <span>⚙️ Rejani o&apos;zgartirish</span>
              </Link>
            </div>

            <div
              className="w-full h-3 rounded-full bg-slate-800/90 overflow-hidden p-0.5 border border-slate-700/80"
              role="progressbar"
              aria-valuenow={dailyProgressPct}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full rounded-full transition-all duration-500 relative"
                style={{
                  width: `${Math.max(6, dailyProgressPct)}%`,
                  background: 'linear-gradient(90deg, #d97706 0%, #f59e0b 50%, #fbbf24 100%)',
                  boxShadow: '0 0 12px rgba(245, 158, 11, 0.65)',
                }}
              />
            </div>
          </div>
        )}
      </section>

      {/* 2. O'QUVCHI UCHUN 3 TA ASOSIY TOP BLOK (ZERO-CLUTTER) */}
      {isStudent && (
        <section className="mb-6 space-y-4" aria-label="Asosiy Harakatlar">
          {/* BLOK 1: TEZKOR KOD BILAN TESTGA KIRISH */}
          <div
            className="rounded-2xl p-4 md:p-5 border transition-all"
            style={{
              background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%)',
              borderColor: 'rgba(56, 189, 248, 0.3)',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.25)',
            }}
          >
            <div className="flex items-center gap-2.5 mb-2">
              <div className="w-8 h-8 rounded-lg bg-sky-500/15 text-sky-400 flex items-center justify-center border border-sky-500/25 shrink-0">
                <KeyRound size={18} />
              </div>
              <div>
                <h2 className="text-base font-bold text-white tracking-tight">
                  Tezkor kod bilan testga kirish
                </h2>
                <p className="text-xs text-slate-400">
                  Ustoz bergan 4-6 xonali test yoki mock kodini kiriting
                </p>
              </div>
            </div>
            <form onSubmit={handleJoinByPin} className="mt-3 flex items-center gap-2">
              <div className="relative flex-1">
                <input
                  type="text"
                  value={pinCode}
                  onChange={(e) => {
                    setPinCode(e.target.value);
                    if (pinErr) setPinErr(null);
                  }}
                  placeholder="Masalan: MOCK-42 yoki 105"
                  className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-sky-400 font-mono tracking-wider transition-colors"
                  disabled={pinBusy}
                />
              </div>
              <button
                type="submit"
                disabled={pinBusy || !pinCode.trim()}
                className="px-4 py-2.5 rounded-xl font-bold text-xs uppercase tracking-wider bg-gradient-to-r from-sky-500 to-sky-600 text-slate-950 hover:from-sky-400 hover:to-sky-500 active:scale-95 disabled:opacity-50 transition-all flex items-center gap-1.5 shrink-0 shadow-lg shadow-sky-500/20"
              >
                <span>{pinBusy ? 'Tekshirilmoqda…' : '🚀 Kirish'}</span>
              </button>
            </form>
            {pinErr && (
              <div className="text-xs text-rose-400 font-medium mt-2 flex items-center gap-1">
                <span>⚠️ {pinErr}</span>
              </div>
            )}
          </div>

          {/* BLOK 2: KUNLIK 5 TALIK BLITS-TEST */}
          <div
            className="rounded-2xl p-4 md:p-5 border transition-all relative overflow-hidden"
            style={{
              background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(217, 119, 6, 0.22) 100%)',
              borderColor: 'rgba(245, 158, 11, 0.4)',
              boxShadow: '0 8px 24px rgba(245, 158, 11, 0.12)',
            }}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-500/20 text-amber-400 flex items-center justify-center border border-amber-500/35 shrink-0 shadow-[0_0_12px_rgba(245,158,11,0.3)]">
                  <Zap size={22} className="text-amber-400 animate-pulse" />
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full uppercase tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/30 inline-flex items-center gap-1">
                      <Flame size={12} className="text-amber-400" /> +25 XP Olov
                    </span>
                    <span className="text-[11px] font-semibold text-slate-300">
                      5 daqiqa • 5 ta savol
                    </span>
                  </div>
                  <h2 className="text-base font-extrabold text-white tracking-tight">
                    Kunlik 5 talik Blits-test
                  </h2>
                  <p className="text-xs text-slate-300 mt-0.5">
                    {subject === 'biology' ? '🧬 Biologiya' : subject === 'chemistry' ? '🧪 Kimyo' : subject === 'law' ? '⚖️ Huquq' : subject === 'english' ? '🇬🇧 English' : '🇺🇿 Ona tili'} bo'yicha bugungi ekspress sinov
                  </p>
                </div>
              </div>
              <Link
                to="/tests?mode=blitz"
                onClick={() => hapticImpact('medium')}
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl font-extrabold text-xs uppercase tracking-wider bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 hover:from-amber-400 hover:to-amber-500 active:scale-95 transition-all shadow-lg shadow-amber-500/25 shrink-0"
              >
                <span>⚡️ Blits-testni boshlash</span>
                <ArrowRight size={14} />
              </Link>
            </div>
          </div>

          {/* BLOK 3: OXIRGI NATIJAM VA GURUHIM REYTINGI */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {/* Sub-card A: Oxirgi natijam */}
            <div
              className="rounded-2xl p-4 border transition-all flex flex-col justify-between"
              style={{
                background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%)',
                borderColor: 'rgba(16, 185, 129, 0.3)',
                boxShadow: '0 4px 16px rgba(0, 0, 0, 0.2)',
              }}
            >
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-emerald-500/15 text-emerald-400 flex items-center justify-center border border-emerald-500/25">
                    <Award size={16} />
                  </div>
                  <span className="text-xs font-bold text-slate-200">Oxirgi natijam</span>
                </div>
                {data?.recent?.[0] && (
                  <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                    {recentSummary(data.recent[0])}
                  </span>
                )}
              </div>
              {data?.recent?.[0] ? (
                <div>
                  <p className="text-sm font-bold text-white truncate mb-2">
                    {data.recent[0].title || 'Test sinovi'}
                  </p>
                  <Link
                    to={`/results/${data.recent[0].result_id}`}
                    onClick={() => hapticSelect()}
                    className="text-xs font-bold text-emerald-400 hover:text-emerald-300 inline-flex items-center gap-1 transition-colors"
                  >
                    <span>Tahlil va xatolarni ko&apos;rish</span>
                    <ChevronRight size={14} />
                  </Link>
                </div>
              ) : (
                <div>
                  <p className="text-xs text-slate-400 mb-2">
                    Hali test topshirmadingiz. Bugungi birinchi testingizni yeching!
                  </p>
                  <Link
                    to="/tests"
                    onClick={() => hapticSelect()}
                    className="text-xs font-bold text-emerald-400 hover:text-emerald-300 inline-flex items-center gap-1 transition-colors"
                  >
                    <span>Testlar ro&apos;yxatiga o&apos;tish</span>
                    <ChevronRight size={14} />
                  </Link>
                </div>
              )}
            </div>

            {/* Sub-card B: Guruhim reytingi */}
            <div
              className="rounded-2xl p-4 border transition-all flex flex-col justify-between"
              style={{
                background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%)',
                borderColor: 'rgba(168, 85, 247, 0.3)',
                boxShadow: '0 4px 16px rgba(0, 0, 0, 0.2)',
              }}
            >
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-purple-500/15 text-purple-400 flex items-center justify-center border border-purple-500/25">
                    <Trophy size={16} />
                  </div>
                  <span className="text-xs font-bold text-slate-200">Guruhim reytingi</span>
                </div>
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  Podium &amp; Reyting
                </span>
              </div>
              <div>
                <p className="text-xs text-slate-300 mb-2">
                  Guruhdoshlaringiz orasidagi o&apos;rningiz va haftalik ballarni kuzatib boring.
                </p>
                <div className="flex items-center gap-3">
                  <Link
                    to="/groups"
                    onClick={() => hapticSelect()}
                    className="text-xs font-bold text-purple-400 hover:text-purple-300 inline-flex items-center gap-1 transition-colors"
                  >
                    <span>Guruhim vedomosti</span>
                    <ChevronRight size={14} />
                  </Link>
                  <span className="text-slate-600">·</span>
                  <Link
                    to="/leaderboard"
                    onClick={() => hapticSelect()}
                    className="text-xs font-bold text-amber-400 hover:text-amber-300 inline-flex items-center gap-1 transition-colors"
                  >
                    <span>Umumiy reyting</span>
                    <ChevronRight size={14} />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 3. ZAIF MAVZULAR VIZUAL RADARI */}
      {isStudent && data && (
        <section
          id="weak-topics-radar"
          className="dsh-card rounded-2xl p-4 md:p-5 mb-5 border border-slate-800 bg-slate-900/80 backdrop-blur-md"
          aria-label="Zaif Mavzular Vizual Radari"
        >
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
            <div>
              <div className="flex items-center gap-2">
                <Target size={20} className="text-rose-400" />
                <h2 className="text-base font-extrabold text-white">Zaif Mavzular Vizual Radari</h2>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                AI diagnostikasi: o&apos;zlashtirish foizi va qaytarilishi kerak bo&apos;lgan zaif bo&apos;limlar
              </p>
            </div>
            <Link
              to="/results"
              className="text-xs font-bold text-amber-400 hover:text-amber-300 flex items-center gap-0.5 transition-colors"
            >
              <span>To&apos;liq tahlil</span>
              <ChevronRight size={14} />
            </Link>
          </div>

          <div className="space-y-3">
            {radarTopics.map((topic, idx) => {
              const isDanger = topic.percentage < 60;
              const barColor = isDanger
                ? 'linear-gradient(90deg, #e11d48 0%, #f43f5e 100%)'
                : 'linear-gradient(90deg, #059669 0%, #10b981 100%)';
              const glowColor = isDanger ? 'rgba(244, 63, 94, 0.4)' : 'rgba(16, 185, 129, 0.4)';

              return (
                <div
                  key={idx}
                  className="p-3.5 rounded-xl border border-slate-800/80 bg-slate-950/40 hover:border-slate-700/80 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                    <span className="font-bold text-sm text-slate-100">
                      {topic.label}
                    </span>
                    <span
                      className="text-xs font-bold px-2.5 py-0.5 rounded-full flex items-center gap-1"
                      style={{
                        background: isDanger ? 'rgba(244, 63, 94, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                        color: isDanger ? '#fb7185' : '#34d399',
                        border: `1px solid ${isDanger ? 'rgba(244, 63, 94, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`,
                      }}
                    >
                      {isDanger ? '⚠️ Qaytarish kerak' : '✅ Zo‘r'} ({topic.percentage}%)
                    </span>
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full h-2.5 rounded-full bg-slate-800/90 overflow-hidden mb-2.5">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${Math.max(5, topic.percentage)}%`,
                        background: barColor,
                        boxShadow: `0 0 8px ${glowColor}`,
                      }}
                    />
                  </div>

                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>
                      {isDanger
                        ? 'Mavzu bo‘yicha xatolar ustida ishlash tavsiya etiladi'
                        : 'Ushbu bo‘lim bo‘yicha mustahkam natija qayd etilgan'}
                    </span>
                    <Link
                      to={topic.practiceUrl || '/tests?mode=practice'}
                      className="font-bold text-amber-400 hover:text-amber-300 inline-flex items-center gap-1"
                    >
                      <span>🎯 Mashq qilish</span>
                      <ArrowRight size={13} />
                    </Link>
                  </div>
                </div>
              );
            })}
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

      <OnboardingModal isOpen={onboardingOpen} onClose={() => setOnboardingOpen(false)} onSuccess={() => setOnboardingOpen(false)} />
    </div>
  );
}
