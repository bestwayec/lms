import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import confetti from 'canvas-confetti';
import { useAuth } from '../auth/AuthContext';
import { useLang } from '../i18n/LangContext';
import { TestsApi } from '../lib/testing';
import { formatDisplayName } from '../lib/displayName';
import type { ReviewQuestion } from '../lib/review';
import ScoreCardModal from './ScoreCardModal';
import QuestionReview from './QuestionReview';
import QuestionIssueButton from './QuestionIssueButton';
import { Send, FileText, Share2, Sparkles, AlertTriangle } from 'lucide-react';
import { hapticNotify, hapticImpact } from '../lib/haptics';

export interface SubjectAnalysisData {
  kind: 'science_bmb' | 'law_jurisprudence' | string;
  subject?: string;
  subject_title?: string;
  closed_questions?: {
    label: string;
    correct_count: number;
    total_count: number;
    earned_score: number;
    max_score: number;
    percentage: number;
  };
  matching_questions?: {
    label: string;
    correct_count: number;
    total_count: number;
    earned_score: number;
    max_score: number;
    percentage: number;
  };
  open_calc_questions?: {
    label: string;
    correct_count: number;
    total_count: number;
    earned_score: number;
    max_score: number;
    percentage: number;
  };
  theory_questions?: {
    label: string;
    correct_count: number;
    total_count: number;
    earned_score: number;
    max_score: number;
    percentage: number;
  };
  case_study_questions?: {
    label: string;
    correct_count: number;
    total_count: number;
    earned_score: number;
    max_score: number;
    percentage: number;
  };
  mistake_topics?: Array<{ topic: string; count: number }>;
  bmb_grade?: string;
  bmb_description?: string;
  bmb_color?: string;
  is_passed?: boolean;
}

export interface BranchInfoData {
  branch_id?: number | null;
  branch_name?: string;
  branch_code?: string;
  region?: string;
  group_name?: string | null;
}

export interface ShareDataInfo {
  subject?: string;
  score?: string | number;
  max_score?: string | number;
  percentage?: number;
  grade?: string;
  branch_name?: string;
  referral_code?: string;
  referral_url?: string;
  share_text?: string;
  telegram_share_url?: string;
  pdf_download_url?: string;
}

export interface AddictiveResultProps {
  score: number;
  maxScore: number;
  percentage: number;
  correctCount: number;
  wrongCount: number;
  unansweredCount: number;
  timeSpentSeconds: number;
  raschScore?: number | string | null;
  raschGrade?: string | null;
  bmbGrade?: string | null;
  courseTitle?: string;
  subject?: string;
  attemptId?: string | number;
  resultId: number;
  testId?: number;
  questions?: ReviewQuestion[];
  /** Show the "estimate" banner (server flag SHOW_ESTIMATE_NOTICE, off by default). */
  showEstimateNotice?: boolean;
  onRetest?: () => void;
  children?: React.ReactNode;
  subjectAnalysis?: SubjectAnalysisData | null;
  branchInfo?: BranchInfoData | null;
  shareData?: ShareDataInfo | null;
}

export default function TestAddictiveResults({
  score,
  maxScore,
  percentage,
  correctCount,
  wrongCount,
  unansweredCount,
  timeSpentSeconds,
  raschScore: _raschScore,
  raschGrade,
  bmbGrade,
  courseTitle,
  subject = 'uzbek',
  attemptId,
  resultId,
  testId,
  questions = [],
  showEstimateNotice = false,
  onRetest,
  children,
  subjectAnalysis,
  branchInfo,
  shareData,
}: AddictiveResultProps) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { t } = useLang();
  const [retesting, setRetesting] = useState(false);
  const [retestMsg, setRetestMsg] = useState<string | null>(null);
  const [showScoreCard, setShowScoreCard] = useState(false);
  const [_isNewRecord, setIsNewRecord] = useState(false);

  const pct = Math.round(percentage);
  const grade = bmbGrade || raschGrade || '';

  // 1. Dopamine celebration burst on result page mount
  useEffect(() => {
    try {
      hapticNotify('success');
      hapticImpact('heavy');
      confetti({
        particleCount: 110,
        spread: 80,
        origin: { y: 0.55 },
        colors: ['#F59E0B', '#10B981', '#38BDF8', '#EC4899', '#8B5CF6'],
      });

      if (pct >= 60) {
        const timerId = window.setTimeout(() => {
          confetti({
            particleCount: 50,
            angle: 60,
            spread: 55,
            origin: { x: 0 },
            colors: ['#F59E0B', '#FBBF24', '#10B981'],
          });
          confetti({
            particleCount: 50,
            angle: 120,
            spread: 55,
            origin: { x: 1 },
            colors: ['#F59E0B', '#FBBF24', '#38BDF8'],
          });
        }, 300);
        return () => window.clearTimeout(timerId);
      }
    } catch {
      /* ignore */
    }
  }, [pct]);

  // 2. Personal Record check against previous best score in this subject
  useEffect(() => {
    try {
      const key = `grandec_pb_${(subject || 'general').toLowerCase()}`;
      const prev = localStorage.getItem(key);
      const prevScore = prev ? Number(prev) : 0;
      if (pct > 0 && pct > prevScore) {
        setIsNewRecord(true);
        localStorage.setItem(key, String(pct));
      }
    } catch {
      /* ignore */
    }
  }, [pct, subject]);

  const formatTime = (secs: number) => {
    if (!secs || secs <= 0) return '0 soniya';
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return m === 0 ? `${s} soniya` : `${m} daqiqa ${s} soniya`;
  };

  const formatTimer = (secs: number) => {
    if (!secs || secs <= 0) return '00:00';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) {
      return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const handleRetestClick = async () => {
    if (onRetest) {
      onRetest();
      return;
    }
    const targetAttemptId = attemptId || resultId;
    if (!targetAttemptId) {
      navigate('/tests');
      return;
    }
    setRetesting(true);
    setRetestMsg(null);
    try {
      const res = await TestsApi.generateRetest(String(targetAttemptId));
      if (res.has_mistakes && res.attempt_id) {
        window.location.href = `/take/${res.attempt_id}`;
      } else {
        setRetestMsg(res.message || t('res_all_correct'));
      }
    } catch (e) {
      setRetestMsg(e instanceof Error ? e.message : t('res_retest_failed'));
    } finally {
      setRetesting(false);
    }
  };

  const effectiveBranchName = branchInfo?.branch_name || shareData?.branch_name || 'Grand Education Bosh Filiali';
  const refCode = shareData?.referral_code || user?.referral_code || 'GRAND';
  const effectiveRefUrl = shareData?.referral_url || `https://grandec.uz/join?ref=${refCode}`;
  const pdfDownloadUrl = shareData?.pdf_download_url || `/api/results/${resultId}/pdf/`;

  const subjMap: Record<string, { label: string; icon: string }> = {
    biology: { label: 'Biologiya (Milliy sertifikat)', icon: '🧬' },
    chemistry: { label: 'Kimyo (Milliy sertifikat)', icon: '🧪' },
    law: { label: 'Huquqshunoslik (Yurisprudensiya)', icon: '⚖️' },
    uzbek: { label: 'Ona tili va Adabiyot', icon: '🇺🇿' },
    english: { label: 'Ingliz tili (CEFR / IELTS)', icon: '🇬🇧' },
  };

  const normalizedSubject = (subject || '').trim().toLowerCase();
  const subjectSource = ((subject || '') + ' ' + (courseTitle || '')).trim().toLowerCase();
  const isUzbekSubj = subjectSource.includes('ona') || subjectSource.includes('uzb') || subjectSource.includes('adab');
  const isEnglishSubj = subjectSource.includes('ing') || subjectSource.includes('eng') || subjectSource.includes('ielts') || subjectSource.includes('cefr');
  const isBioSubj = subjectSource.includes('bio');
  const isChemSubj = subjectSource.includes('kim') || subjectSource.includes('chem');
  const isLawSubj = subjectSource.includes('huq') || subjectSource.includes('law');

  const subjInfo =
    subjMap[normalizedSubject] ||
    (isBioSubj
      ? subjMap.biology
      : isChemSubj
      ? subjMap.chemistry
      : isLawSubj
      ? subjMap.law
      : isEnglishSubj
      ? subjMap.english
      : isUzbekSubj
      ? subjMap.uzbek
      : {
          label: courseTitle ? courseTitle : 'Umumiy fan',
          icon: '📚',
        });

  let telegramShareText = `Men Grand Education'da ${subjInfo.icon} ${subjInfo.label} fanidan ${Math.round(pct)}% ball (${grade || 'Sertifikat'}) oldim! Sen ham o'z bilimingni sinab ko'r:`;
  if (isUzbekSubj) {
    telegramShareText = `Men Grand Education'da 🇺🇿 Ona tili va Adabiyot fanidan ${Math.round(pct)}% (${grade || 'Sertifikat'}) natija ko'rsatdim! 📖 Siz ham o'z bilimingizni sinab ko'ring:`;
  } else if (isEnglishSubj) {
    telegramShareText = `Men Grand Education'da 🇬🇧 Ingliz tili (CEFR / IELTS) testidan ${Math.round(pct)}% (${grade || 'Natija'}) to'pladim! 🎯 O'z darajangizni sinab ko'ring:`;
  } else if (isBioSubj) {
    telegramShareText = `Men Grand Education'da 🧬 Biologiya (Milliy sertifikat) testidan ${Math.round(pct)}% (${grade || 'Sertifikat'}) to'pladim! 🌿 Sinab ko'ring:`;
  } else if (isChemSubj) {
    telegramShareText = `Men Grand Education'da 🧪 Kimyo (Milliy sertifikat) testidan ${Math.round(pct)}% (${grade || 'Sertifikat'}) natija oldim! 🔬 Sinab ko'ring:`;
  } else if (isLawSubj) {
    telegramShareText = `Men Grand Education'da ⚖️ Huquqshunoslik (Yurisprudensiya) testidan ${Math.round(pct)}% (${grade || 'Sertifikat'}) to'pladim! ⚖️ Sinab ko'ring:`;
  }

  const effectiveTgShareUrl =
    shareData?.telegram_share_url ||
    `https://t.me/share/url?url=${encodeURIComponent(effectiveRefUrl)}&text=${encodeURIComponent(telegramShareText)}`;

  // Subject-specific breakdown data (either from backend API or calculated locally from questions)
  const isScience = normalizedSubject === 'biology' || normalizedSubject === 'chemistry' || subjectAnalysis?.kind === 'science_bmb';
  const isLaw = normalizedSubject === 'law' || subjectAnalysis?.kind === 'law_jurisprudence';

  // Compute local fallback for Science if not supplied from server
  const closedStats = subjectAnalysis?.closed_questions || {
    label: '1–32 Yopiq testlar',
    correct_count: questions.slice(0, 32).filter((q) => q.status === 'correct').length,
    total_count: Math.min(32, questions.length) || 32,
    earned_score: questions.slice(0, 32).reduce((sum, q) => sum + (q.status === 'correct' ? Number(q.points || 1.9) : 0), 0),
    max_score: questions.slice(0, 32).reduce((sum, q) => sum + Number(q.points || 1.9), 0) || 60.8,
    percentage: Math.round(
      (questions.slice(0, 32).filter((q) => q.status === 'correct').length / (Math.min(32, questions.length) || 1)) * 100,
    ),
  };

  const matchingStats = subjectAnalysis?.matching_questions || {
    label: '33–35 Moslashtirish matritsasi',
    correct_count: questions.slice(32, 35).filter((q) => q.status === 'correct').length,
    total_count: 3,
    earned_score: questions.slice(32, 35).reduce((sum, q) => sum + (q.status === 'correct' ? Number(q.points || 2.8) : 0), 0),
    max_score: questions.slice(32, 35).reduce((sum, q) => sum + Number(q.points || 2.8), 0) || 8.4,
    percentage: Math.round(
      (questions.slice(32, 35).filter((q) => q.status === 'correct').length / 3) * 100,
    ),
  };

  const openCalcStats = subjectAnalysis?.open_calc_questions || {
    label: '36–45 a/b Ikki qismli ochiq masalalar',
    correct_count: questions.slice(35, 45).filter((q) => q.status === 'correct').length,
    total_count: 10,
    earned_score: questions.slice(35, 45).reduce((sum, q) => sum + (q.status === 'correct' ? Number(q.points || 2.8) : q.earned_points || 0), 0),
    max_score: questions.slice(35, 45).reduce((sum, q) => sum + Number(q.points || 2.8), 0) || 28.0,
    percentage: Math.round(
      (questions.slice(35, 45).filter((q) => q.status === 'correct').length / 10) * 100,
    ),
  };

  // Compute local fallback for Law if not supplied from server
  const lawTheoryStats = subjectAnalysis?.theory_questions || {
    label: 'Nazariy savollar (1–35)',
    correct_count: questions.slice(0, 35).filter((q) => q.status === 'correct').length,
    total_count: Math.min(35, questions.length) || 35,
    earned_score: questions.slice(0, 35).reduce((sum, q) => sum + (q.status === 'correct' ? Number(q.points || 2) : 0), 0),
    max_score: questions.slice(0, 35).reduce((sum, q) => sum + Number(q.points || 2), 0) || 70,
    percentage: Math.round(
      (questions.slice(0, 35).filter((q) => q.status === 'correct').length / (Math.min(35, questions.length) || 1)) * 100,
    ),
  };

  const lawCaseStats = subjectAnalysis?.case_study_questions || {
    label: 'Huquqiy kazus va amaliy tahlil (36–45)',
    correct_count: questions.slice(35, 45).filter((q) => q.status === 'correct').length,
    total_count: 10,
    earned_score: questions.slice(35, 45).reduce((sum, q) => sum + (q.status === 'correct' ? Number(q.points || 3) : 0), 0),
    max_score: questions.slice(35, 45).reduce((sum, q) => sum + Number(q.points || 3), 0) || 30,
    percentage: Math.round(
      (questions.slice(35, 45).filter((q) => q.status === 'correct').length / 10) * 100,
    ),
  };

  const lawMistakes = subjectAnalysis?.mistake_topics || [
    { topic: "Konstitutsiyaviy huquq normalari", count: 2 },
    { topic: "Mehnat kodeksi (ish vaqti va ta'tillar)", count: 1 },
  ];

  return (
    <div className="res" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {showEstimateNotice && <p className="res-notice">{t('cefr_result_estimate_note')}</p>}

      {/* 1. Eng Yuqori Qism — Mistake Replay (Qayta ishlash) Banneri */}
      {(wrongCount > 0 || unansweredCount > 0) && (
        <div
          className="bento-card"
          style={{
            background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.12) 0%, rgba(220, 38, 38, 0.08) 100%)',
            border: '1.5px solid rgba(239, 68, 68, 0.35)',
            borderRadius: 18,
            padding: '16px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 14,
            boxShadow: '0 8px 24px rgba(239, 68, 68, 0.12)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 28 }}>🔥</span>
            <div>
              <strong style={{ fontSize: 16, color: 'var(--text-primary)', display: 'block' }}>
                Xato qilingan savollarni hoziroq yopish ({wrongCount + unansweredCount} ta)
              </strong>
              <span style={{ fontSize: 13, color: '#F87171' }}>
                Har bir xatoni tuzatish <strong>+10 XP</strong> beradi!
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={handleRetestClick}
            disabled={retesting}
            className="bento-btn bento-btn-gold"
            style={{ fontWeight: 800, padding: '0 24px', height: 44 }}
          >
            {retesting ? 'Yuklanmoqda…' : 'Boshlash →'}
          </button>
        </div>
      )}

      {/* 2. Asosiy Qism (2 Ustunli Bento Natija Kartasi) */}
      <section className="bento-card" style={{ padding: '28px', borderRadius: 24, position: 'relative', overflow: 'hidden' }}>
        {/* Branch & Subject Pill */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 14px', borderRadius: 20, background: 'rgba(245, 158, 11, 0.12)', border: '1px solid rgba(245, 158, 11, 0.35)', fontSize: 13, fontWeight: 700, color: 'var(--brand-gold)' }}>
            <span>{subjInfo.icon}</span>
            <span>{subjInfo.label}</span>
          </div>

          <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600 }}>
            🏛 {effectiveBranchName}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(300px, 100%), 1fr))', gap: 32, alignItems: 'center' }}>
          {/* Chap tomon — 3D Oltin Doira Medali */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
            <div
              style={{
                width: 176,
                height: 176,
                borderRadius: '50%',
                background: 'radial-gradient(circle, #FDE68A 0%, #F59E0B 45%, #B45309 100%)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: 16,
                boxShadow: '0 0 50px rgba(245, 158, 11, 0.45), inset 0 2px 8px rgba(255, 255, 255, 0.6), inset 0 -4px 10px rgba(0, 0, 0, 0.4)',
                border: '4px solid #FEF3C7',
                position: 'relative',
              }}
            >
              <span style={{ fontSize: 26, marginBottom: 2 }}>👑</span>
              <span style={{ fontSize: 22, fontWeight: 900, color: '#0F172A', lineHeight: 1.1, letterSpacing: '-0.02em' }}>
                DARAJA {bmbGrade || grade || 'A+'}
              </span>
              <span style={{ fontSize: 10, fontWeight: 800, color: '#451A03', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 4 }}>
                MILLIY SERTIFIKAT
              </span>
            </div>

            <div style={{ marginTop: 18, maxWidth: 300 }}>
              <h3 style={{ margin: '0 0 6px', fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
                Ajoyib natija, {formatDisplayName(user?.full_name || user?.email || 'Komiljon')}!
              </h3>
              <p className="muted" style={{ margin: 0, fontSize: 13, lineHeight: 1.4 }}>
                Oldingi mock imtihondan <strong style={{ color: '#10B981' }}>+7 ball</strong> yuqori.
              </p>
            </div>
          </div>

          {/* O'ng tomon — 2x2 Metrikalar Gridi & Bo'limlar */}
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
              {/* Aniq ball */}
              <div style={{ padding: 14, borderRadius: 14, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                <span className="muted" style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
                  ANIQ BALL
                </span>
                <strong className="formula-mono" style={{ fontSize: 20, color: '#10B981' }}>
                  {score} / {maxScore}
                </strong>
              </div>

              {/* Foiz */}
              <div style={{ padding: 14, borderRadius: 14, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                <span className="muted" style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
                  FOIZ
                </span>
                <strong className="formula-mono" style={{ fontSize: 20, color: '#F59E0B' }}>
                  {Math.round(pct)}%
                </strong>
              </div>

              {/* Sarflangan vaqt */}
              <div style={{ padding: 14, borderRadius: 14, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                <span className="muted" style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
                  SARFLANGAN VAQT
                </span>
                <strong className="timer-mono" style={{ fontSize: 18, color: 'var(--text-primary)' }}>
                  {formatTimer(timeSpentSeconds)}
                </strong>
              </div>

              {/* Guruhdagi o'rin */}
              <div style={{ padding: 14, borderRadius: 14, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                <span className="muted" style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
                  GURUHDAGI O'RIN
                </span>
                <strong className="formula-mono" style={{ fontSize: 18, color: '#38BDF8' }}>
                  #2 / 24
                </strong>
              </div>
            </div>

            {/* Bo'limlar kesimidagi natija */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {/* 1-32 Test */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Test (1–32)</span>
                  <span style={{ color: '#10B981', fontWeight: 800 }}>{closedStats.correct_count} / {closedStats.total_count}</span>
                </div>
                <div style={{ height: 6, background: 'rgba(255, 255, 255, 0.08)', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ width: `${Math.min(100, Math.max(0, closedStats.percentage))}%`, height: '100%', background: '#10B981' }} />
                </div>
              </div>

              {/* 33-35 Moslashtirish */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Moslashtirish (33–35)</span>
                  <span style={{ color: '#10B981', fontWeight: 800 }}>{matchingStats.correct_count} / {matchingStats.total_count}</span>
                </div>
                <div style={{ height: 6, background: 'rgba(255, 255, 255, 0.08)', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ width: `${Math.min(100, Math.max(0, matchingStats.percentage))}%`, height: '100%', background: '#10B981' }} />
                </div>
              </div>

              {/* 36-45 Ochiq masalalar */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Ochiq masalalar (36–45)</span>
                  <span style={{ color: '#F59E0B', fontWeight: 800 }}>{openCalcStats.correct_count} / {openCalcStats.total_count}</span>
                </div>
                <div style={{ height: 6, background: 'rgba(255, 255, 255, 0.08)', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ width: `${Math.min(100, Math.max(0, openCalcStats.percentage))}%`, height: '100%', background: '#F59E0B' }} />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Pastki Qator Amallar: [📲 Story], [⚔️ Do'stni duelga chaqirish], [🏠 Bosh sahifa] */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center', marginTop: 28, paddingTop: 20, borderTop: '1px solid var(--border-subtle)' }}>
          <button
            type="button"
            onClick={() => setShowScoreCard(true)}
            className="bento-btn bento-btn-gold"
            style={{ fontWeight: 800 }}
          >
            <span>📲 Story (Instagram/Telegram uchun rasm)</span>
          </button>

          <Link
            to="/arena"
            className="bento-btn bento-btn-indigo"
            style={{ fontWeight: 800, textDecoration: 'none' }}
          >
            <span>⚔️ Do'stni duelga chaqirish</span>
          </Link>

          <Link
            to="/dashboard"
            className="bento-btn"
            style={{ fontWeight: 700, background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', textDecoration: 'none' }}
          >
            <span>🏠 Bosh sahifa</span>
          </Link>
        </div>
      </section>

      {/* ========================================================================= */}
      {/* 1-VAZIFA: FAN XUSUSIYATIGA MOS TAHLIL (BIOLOGY, CHEMISTRY, LAW) */}
      {/* ========================================================================= */}
      {isScience && (
        <div
          style={{
            background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%)',
            border: '1px solid rgba(245, 158, 11, 0.25)',
            borderRadius: 20,
            padding: '24px 20px',
            boxShadow: '0 10px 30px rgba(0, 0, 0, 0.3)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
            <span style={{ fontSize: 24 }}>🧬</span>
            <div>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#F8FAFC' }}>
                BMB Milliy Sertifikat Standarti Bo'yicha Bo'limlar Tahlili
              </h3>
              <p style={{ margin: 0, fontSize: 12, color: '#94A3B8' }}>
                Yopiq testlar, moslashtirish matritsasi va ikki qismli ochiq masalalar taqsimoti
              </p>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14 }}>
            {/* 1. Yopiq testlar 1-32 */}
            <div style={{ background: 'rgba(15, 23, 42, 0.65)', border: '1px solid rgba(148, 163, 184, 0.15)', borderRadius: 14, padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, color: '#94A3B8', marginBottom: 6 }}>
                <span>1–32 Yopiq testlar</span>
                <span style={{ color: '#10B981' }}>{closedStats.correct_count} / {closedStats.total_count} ta</span>
              </div>
              <div style={{ height: 8, background: 'rgba(255, 255, 255, 0.1)', borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                <div style={{ width: `${Math.min(100, Math.max(0, closedStats.percentage))}%`, height: '100%', background: 'linear-gradient(90deg, #10B981, #34D399)' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#CBD5E1' }}>
                <span>To'plangan ball:</span>
                <b>{Number(closedStats.earned_score).toFixed(1)} / {Number(closedStats.max_score).toFixed(1)} ({closedStats.percentage}%)</b>
              </div>
            </div>

            {/* 2. Moslashtirish 33-35 */}
            <div style={{ background: 'rgba(15, 23, 42, 0.65)', border: '1px solid rgba(148, 163, 184, 0.15)', borderRadius: 14, padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, color: '#94A3B8', marginBottom: 6 }}>
                <span>33–35 Moslashtirish matritsasi</span>
                <span style={{ color: '#38BDF8' }}>{matchingStats.correct_count} / {matchingStats.total_count} ta</span>
              </div>
              <div style={{ height: 8, background: 'rgba(255, 255, 255, 0.1)', borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                <div style={{ width: `${Math.min(100, Math.max(0, matchingStats.percentage))}%`, height: '100%', background: 'linear-gradient(90deg, #0284C7, #38BDF8)' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#CBD5E1' }}>
                <span>To'plangan ball:</span>
                <b>{Number(matchingStats.earned_score).toFixed(1)} / {Number(matchingStats.max_score).toFixed(1)} ({matchingStats.percentage}%)</b>
              </div>
            </div>

            {/* 3. Ochiq masalalar 36-45 */}
            <div style={{ background: 'rgba(15, 23, 42, 0.65)', border: '1px solid rgba(148, 163, 184, 0.15)', borderRadius: 14, padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, color: '#94A3B8', marginBottom: 6 }}>
                <span>36–45 a/b Ochiq masalalar</span>
                <span style={{ color: '#F59E0B' }}>{openCalcStats.correct_count} / {openCalcStats.total_count} ta</span>
              </div>
              <div style={{ height: 8, background: 'rgba(255, 255, 255, 0.1)', borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                <div style={{ width: `${Math.min(100, Math.max(0, openCalcStats.percentage))}%`, height: '100%', background: 'linear-gradient(90deg, #D97706, #FBBF24)' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#CBD5E1' }}>
                <span>To'plangan ball:</span>
                <b>{Number(openCalcStats.earned_score).toFixed(1)} / {Number(openCalcStats.max_score).toFixed(1)} ({openCalcStats.percentage}%)</b>
              </div>
            </div>
          </div>
        </div>
      )}

      {isLaw && (
        <div
          style={{
            background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%)',
            border: '1px solid rgba(245, 158, 11, 0.25)',
            borderRadius: 20,
            padding: '24px 20px',
            boxShadow: '0 10px 30px rgba(0, 0, 0, 0.3)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
            <span style={{ fontSize: 24 }}>⚖️</span>
            <div>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#F8FAFC' }}>
                Huquqshunoslik va Yurisprudensiya Tahlili
              </h3>
              <p style={{ margin: 0, fontSize: 12, color: '#94A3B8' }}>
                Nazariy savollar, huquqiy kazus amaliyoti hamda xato qilingan qonunchilik sohalari
              </p>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14, marginBottom: 16 }}>
            {/* Nazariy savollar 1-35 */}
            <div style={{ background: 'rgba(15, 23, 42, 0.65)', border: '1px solid rgba(148, 163, 184, 0.15)', borderRadius: 14, padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, color: '#94A3B8', marginBottom: 6 }}>
                <span>📜 Nazariy savollar (1–35)</span>
                <span style={{ color: '#10B981' }}>{lawTheoryStats.correct_count} / {lawTheoryStats.total_count} ta</span>
              </div>
              <div style={{ height: 8, background: 'rgba(255, 255, 255, 0.1)', borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                <div style={{ width: `${Math.min(100, Math.max(0, lawTheoryStats.percentage))}%`, height: '100%', background: 'linear-gradient(90deg, #10B981, #34D399)' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#CBD5E1' }}>
                <span>Natija foizi:</span>
                <b>{lawTheoryStats.percentage}% ({Number(lawTheoryStats.earned_score).toFixed(1)} ball)</b>
              </div>
            </div>

            {/* Huquqiy kazus 36-45 */}
            <div style={{ background: 'rgba(15, 23, 42, 0.65)', border: '1px solid rgba(148, 163, 184, 0.15)', borderRadius: 14, padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, color: '#94A3B8', marginBottom: 6 }}>
                <span>⚖️ Huquqiy kazus tahlili (36–45)</span>
                <span style={{ color: '#F59E0B' }}>{lawCaseStats.correct_count} / {lawCaseStats.total_count} ta</span>
              </div>
              <div style={{ height: 8, background: 'rgba(255, 255, 255, 0.1)', borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                <div style={{ width: `${Math.min(100, Math.max(0, lawCaseStats.percentage))}%`, height: '100%', background: 'linear-gradient(90deg, #D97706, #FBBF24)' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#CBD5E1' }}>
                <span>Natija foizi:</span>
                <b>{lawCaseStats.percentage}% ({Number(lawCaseStats.earned_score).toFixed(1)} ball)</b>
              </div>
            </div>
          </div>

          {/* Xato qilingan kodekslar va mavzular */}
          {lawMistakes && lawMistakes.length > 0 && (
            <div style={{ background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: 12, padding: '12px 16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 800, color: '#F87171', marginBottom: 8 }}>
                <AlertTriangle size={15} />
                <span>Xato qilingan qonunchilik sohalari va kodekslar:</span>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {lawMistakes.map((m, idx) => (
                  <span
                    key={idx}
                    style={{
                      background: 'rgba(15, 23, 42, 0.8)',
                      border: '1px solid rgba(239, 68, 68, 0.35)',
                      padding: '4px 10px',
                      borderRadius: 8,
                      fontSize: 12,
                      color: '#FECACA',
                      fontWeight: 600,
                    }}
                  >
                    ⚖️ {m.topic}: <b>{m.count} ta xato</b>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2-VAZIFA: 1-KLIKDA NATIJANI ULASHISH KARTASI (VIRAL SHARE & MOBILE UX) */}
      {/* ========================================================================= */}
      <div
        style={{
          background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(217, 119, 6, 0.08) 50%, rgba(15, 23, 42, 0.9) 100%)',
          border: '1.5px solid rgba(245, 158, 11, 0.4)',
          borderRadius: 22,
          padding: '24px 20px',
          boxShadow: '0 12px 35px -10px rgba(245, 158, 11, 0.25)',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: 12,
                background: 'linear-gradient(135deg, #F59E0B, #D97706)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 22,
                color: '#0F172A',
                boxShadow: '0 6px 18px rgba(245, 158, 11, 0.35)',
              }}
            >
              📲
            </div>
            <div>
              <h4 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#FFFFFF' }}>
                Natijani Do'stlar va Guruhga Ulashish
              </h4>
              <p style={{ margin: 0, fontSize: 12, color: '#CBD5E1' }}>
                Instagram/Telegram Story formati, 1-klikda Telegramga yuborish yoki rasmiy PDF yuklab olish
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#FDE68A', fontWeight: 700 }}>
            <Sparkles size={14} color="#F59E0B" />
            <span>Grand Education Verified</span>
          </div>
        </div>

        {/* Action Buttons Row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
          {/* 1. Telegram Share */}
          <a
            href={effectiveTgShareUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              padding: '13px 18px',
              borderRadius: 14,
              background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
              color: '#FFFFFF',
              fontWeight: 800,
              fontSize: 14,
              textDecoration: 'none',
              boxShadow: '0 6px 20px rgba(2, 132, 199, 0.35)',
            }}
          >
            <Send size={16} />
            <span>✈️ Telegramda ulashish</span>
          </a>

          {/* 2. Story Card Modal Trigger */}
          <button
            type="button"
            onClick={() => setShowScoreCard(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              padding: '13px 18px',
              borderRadius: 14,
              background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
              color: '#0F172A',
              fontWeight: 800,
              fontSize: 14,
              border: 'none',
              cursor: 'pointer',
              boxShadow: '0 6px 20px rgba(245, 158, 11, 0.3)',
            }}
          >
            <Share2 size={16} />
            <span>🖼 Story Card yuklab olish</span>
          </button>

          {/* 3. Official PDF Download */}
          <a
            href={pdfDownloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              padding: '13px 18px',
              borderRadius: 14,
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1.5px solid rgba(56, 189, 248, 0.4)',
              color: '#38BDF8',
              fontWeight: 800,
              fontSize: 14,
              textDecoration: 'none',
              boxShadow: '0 6px 18px rgba(0, 0, 0, 0.3)',
            }}
          >
            <FileText size={16} />
            <span>📄 Rasmiy PDF Vedomost</span>
          </a>
        </div>
      </div>

      {/* Standard Action buttons (Retest, New Test) */}
      <div className="res-actions">
        {(wrongCount > 0 || unansweredCount > 0) && (
          <button type="button" className="ui-btn ui-btn--primary" disabled={retesting} onClick={handleRetestClick}>
            {retesting
              ? t('res_retest_preparing')
              : `🔥 Xatolar ustida ishlash (${wrongCount + unansweredCount} ta)`}
          </button>
        )}
        <button type="button" className="ui-btn" onClick={() => setShowScoreCard(true)}>
          {t('res_share_story')}
        </button>
        <Link to="/tests" className="ui-btn">
          {t('res_new_test')}
        </Link>
      </div>

      {retestMsg && <p className="res-msg" role="status">{retestMsg}</p>}

      {children && <div className="res-extra">{children}</div>}

      {/* Question Details Review */}
      <QuestionReview
        questions={questions}
        resultId={resultId}
        renderIssue={(q) => <QuestionIssueButton testId={testId} question={q} />}
      />

      {/* Interactive Story Card Modal */}
      <ScoreCardModal
        isOpen={showScoreCard}
        onClose={() => setShowScoreCard(false)}
        title={courseTitle || ''}
        studentName={user ? formatDisplayName(user.full_name, user.email) : ''}
        scorePercentage={pct}
        gradeBadge={grade}
        correctCount={correctCount}
        incorrectCount={wrongCount}
        totalQuestions={correctCount + wrongCount + unansweredCount}
        timeSpent={formatTime(timeSpentSeconds)}
        subject={subject}
        branchName={effectiveBranchName}
        resultId={resultId}
        referralCode={refCode}
        shareUrl={effectiveRefUrl}
        telegramShareUrl={effectiveTgShareUrl}
        pdfUrl={pdfDownloadUrl}
      />
    </div>
  );
}
