import { useEffect, useRef, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  GraduationCap,
  Building2,
  BookOpen,
  Award,
  ArrowRight,
  CheckCircle2,
  Copy,
  Check,
  Phone,
  ArrowLeft,
  Flame,
  AlertCircle,
  Clock,
  Trophy,
  QrCode,
} from 'lucide-react';
import { StudentGroupDetailApi, type StudentGroupViewData } from '../lib/api';
import { useToast } from '../context/ToastContext';
import { useLang } from '../i18n/LangContext';
import ClassroomQrModal from '../components/ClassroomQrModal';

function getInitials(name: string): string {
  if (!name) return 'S';
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function formatDeadline(dueAt?: string | null): { text: string; urgent: boolean } {
  if (!dueAt) {
    return { text: "⏳ Keyingi darsgacha", urgent: false };
  }
  const due = new Date(dueAt).getTime();
  const now = Date.now();
  const diffMs = due - now;
  if (diffMs <= 0) {
    return { text: "⚠️ Muddati tugagan", urgent: true };
  }
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  if (hours < 24) {
    return { text: `⏳ ${Math.max(1, hours)} soat qoldi`, urgent: true };
  }
  const days = Math.floor(hours / 24);
  return { text: `📅 ${days} kun qoldi`, urgent: false };
}

export default function StudentGroupDetail() {
  const { groupId } = useParams<{ groupId: string }>();
  const navigate = useNavigate();
  const { t } = useLang();
  const [data, setData] = useState<StudentGroupViewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qrOpen, setQrOpen] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const toast = useToast();

  const loadData = async () => {
    if (!groupId) return;
    try {
      setLoading(true);
      setError(null);
      const res = await StudentGroupDetailApi.getStudentView(Number(groupId));
      setData(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('group_load_err');
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    return () => {
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
      }
    };
  }, [groupId]);

  const copyCode = () => {
    if (!data?.group.invite_code) return;
    navigator.clipboard.writeText(data.group.invite_code).catch(() => {});
    setCopied(true);
    toast.success(`${t('group_code_copied_toast')} ${data.group.invite_code}`);
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div style={{ maxWidth: 1000, margin: '0 auto', padding: '60px 16px', textAlign: 'center', color: '#94A3B8' }}>
        <div style={{ fontSize: 18, fontWeight: 600 }}>{t('group_env_loading')}</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ maxWidth: 600, margin: '60px auto', padding: 24, textAlign: 'center' }}>
        <AlertCircle size={48} color="#EF4444" style={{ marginBottom: 16 }} />
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: '0 0 8px' }}>{t('group_not_found_or_forbidden')}</h2>
        <p style={{ color: '#94A3B8', fontSize: 14, margin: '0 0 20px' }}>
          {error || t('group_not_a_member')}
        </p>
        <Link
          to="/dashboard"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 20px',
            borderRadius: 10,
            background: '#C8922A',
            color: '#fff',
            textDecoration: 'none',
            fontWeight: 600,
          }}
        >
          <ArrowLeft size={16} /> {t('group_back_home')}
        </Link>
      </div>
    );
  }

  const { group, branch, teacher, assigned_tests, leaderboard, my_rank } = data;

  const top1 = leaderboard[0];
  const top2 = leaderboard[1];
  const top3 = leaderboard[2];
  const restStudents = leaderboard.slice(3);
  const currentStudent = leaderboard.find((x) => x.is_me);
  const gapToPodium =
    top3 && currentStudent && my_rank && my_rank > 3
      ? Math.max(1, Math.round(top3.avg_test_pct - currentStudent.avg_test_pct + 1))
      : 0;

  return (
    <div style={{ maxWidth: 1050, margin: '0 auto', padding: '20px 16px 80px' }}>
      {/* Back button */}
      <div style={{ marginBottom: 16 }}>
        <button
          onClick={() => navigate(-1)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            background: 'none',
            border: 'none',
            color: '#94A3B8',
            cursor: 'pointer',
            fontSize: 14,
            fontWeight: 500,
          }}
        >
          <ArrowLeft size={16} /> {t('group_back')}
        </button>
      </div>

      {/* Main Group Header Card */}
      <div
        style={{
          background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.9) 0%, rgba(15, 23, 42, 0.95) 100%)',
          borderRadius: 22,
          padding: '24px 28px',
          border: '1px solid rgba(200, 146, 42, 0.25)',
          boxShadow: '0 10px 30px rgba(0,0,0,0.25)',
          marginBottom: 24,
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
          <div>
            {/* Branch and Code Badges */}
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              {branch && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '4px 10px',
                    borderRadius: 8,
                    background: 'rgba(59, 130, 246, 0.15)',
                    color: '#60A5FA',
                    fontSize: 12,
                    fontWeight: 600,
                    border: '1px solid rgba(59, 130, 246, 0.3)',
                  }}
                >
                  <Building2 size={13} />
                  {branch.name} [{branch.branch_code}]
                </span>
              )}

              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '4px 10px',
                  borderRadius: 8,
                  background: 'rgba(200, 146, 42, 0.15)',
                  color: '#F59E0B',
                  fontSize: 12,
                  fontWeight: 700,
                  border: '1px solid rgba(200, 146, 42, 0.3)',
                }}
              >
                {t('group_code_label')} {group.invite_code}
              </span>
            </div>

            <h1 style={{ fontSize: 24, fontWeight: 800, margin: '0 0 6px', color: '#F8FAFC' }}>
              {group.name}
            </h1>

            {group.description && (
              <p style={{ margin: '0 0 12px', color: '#94A3B8', fontSize: 14 }}>
                {group.description}
              </p>
            )}

            {/* Teacher Details */}
            <div
              style={{
                display: 'inline-flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                gap: 12,
                background: 'rgba(255,255,255,0.04)',
                padding: '8px 14px',
                borderRadius: 12,
                marginTop: 6,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: 'rgba(200, 146, 42, 0.2)',
                    color: '#F59E0B',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <GraduationCap size={18} />
                </span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#F8FAFC' }}>
                    {teacher.name}
                  </div>
                  <div style={{ fontSize: 11, color: '#94A3B8' }}>
                    {teacher.subject_label} • {teacher.qualification}
                  </div>
                </div>
              </div>

              {teacher.phone && (
                <a
                  href={`tel:${teacher.phone}`}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    fontSize: 12,
                    color: '#10B981',
                    textDecoration: 'none',
                    padding: '4px 8px',
                    borderRadius: 6,
                    background: 'rgba(16, 185, 129, 0.1)',
                  }}
                >
                  <Phone size={12} /> {teacher.phone}
                </a>
              )}
            </div>
          </div>

          {/* Quick Code Share Action */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <button
                onClick={copyCode}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '9px 16px',
                  borderRadius: 10,
                  background: 'rgba(255,255,255,0.08)',
                  border: '1px solid rgba(255,255,255,0.15)',
                  color: '#fff',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {copied ? <Check size={16} color="#10B981" /> : <Copy size={16} />}
                {copied ? (t('copied') || 'Nusxalandi!') : t('group_share_code')}
              </button>

              <button
                type="button"
                onClick={() => setQrOpen(true)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '9px 16px',
                  borderRadius: 10,
                  background: 'rgba(245, 158, 11, 0.15)',
                  border: '1px solid rgba(245, 158, 11, 0.35)',
                  color: '#F59E0B',
                  fontSize: 13,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
                title="Sinfxona proyektorida QR-kodni ko'rsatish"
              >
                <QrCode size={16} />
                <span>📱 Katta QR-Kod</span>
              </button>
            </div>

            {my_rank && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 14px',
                  borderRadius: 10,
                  background: 'rgba(200,146,42,0.15)',
                  border: '1px solid rgba(200,146,42,0.3)',
                  color: '#F59E0B',
                  fontSize: 13,
                  fontWeight: 700,
                }}
              >
                <Flame size={16} />
                {t('group_my_rank').replace('{rank}', String(my_rank))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Content: 2-column on desktop */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))', gap: 24 }}>
        {/* Left Column: Assigned Homework Tests */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
              <BookOpen size={20} color="#C8922A" />
              {t('group_active_homework')} ({assigned_tests.length})
            </h2>
          </div>

          {assigned_tests.length === 0 ? (
            <div
              style={{
                background: 'var(--card-bg, #1E293B)',
                borderRadius: 16,
                padding: '30px 20px',
                textAlign: 'center',
                color: '#94A3B8',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <CheckCircle2 size={36} color="#10B981" style={{ marginBottom: 10 }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: '#F8FAFC' }}>
                {t('group_no_active_tasks')}
              </div>
              <p style={{ fontSize: 13, margin: '6px 0 0' }}>
                {t('group_no_active_tasks_desc')}
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {assigned_tests.map((testItem) => {
                const deadlineInfo = formatDeadline(testItem.due_at);
                const isCompleted = testItem.status === 'completed' && testItem.result;
                const isInProgress = testItem.status === 'in_progress' && testItem.attempt_id;

                return (
                  <div
                    key={testItem.id}
                    style={{
                      background: 'var(--card-bg, #1E293B)',
                      borderRadius: 16,
                      padding: '18px',
                      border: '1px solid rgba(255,255,255,0.08)',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      gap: 12,
                      boxShadow: '0 4px 14px rgba(0,0,0,0.1)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                      <div>
                        <h3 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 6px', color: '#F8FAFC' }}>
                          {testItem.title}
                        </h3>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: '#94A3B8' }}>
                          <span>📝 {t('group_questions_count').replace('{n}', String(testItem.total_questions))}</span>
                          <span>⏱ {t('group_duration_minutes').replace('{n}', String(testItem.duration_minutes))}</span>
                        </div>
                      </div>

                      {/* Status and Deadline Badge */}
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                        {isCompleted ? (
                          <span
                            style={{
                              padding: '4px 10px',
                              borderRadius: 8,
                              background: 'rgba(16, 185, 129, 0.15)',
                              color: '#10B981',
                              fontSize: 12,
                              fontWeight: 700,
                              border: '1px solid rgba(16, 185, 129, 0.3)',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            ✅ {testItem.result?.percentage}% ({testItem.result?.grade})
                          </span>
                        ) : isInProgress ? (
                          <span
                            style={{
                              padding: '4px 10px',
                              borderRadius: 8,
                              background: 'rgba(2, 132, 199, 0.15)',
                              color: '#38BDF8',
                              fontSize: 12,
                              fontWeight: 700,
                              border: '1px solid rgba(2, 132, 199, 0.3)',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            ⚡️ Jarayonda
                          </span>
                        ) : (
                          <span
                            style={{
                              padding: '4px 10px',
                              borderRadius: 8,
                              background: 'rgba(200, 146, 42, 0.15)',
                              color: '#F59E0B',
                              fontSize: 12,
                              fontWeight: 700,
                              border: '1px solid rgba(200, 146, 42, 0.3)',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            ⏳ Topshiriq
                          </span>
                        )}

                        {!isCompleted && (
                          <span
                            className={deadlineInfo.urgent ? 'urgent-pulse' : ''}
                            style={{
                              fontSize: 11,
                              fontWeight: 700,
                              color: deadlineInfo.urgent ? '#F87171' : '#FBBF24',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 4,
                            }}
                          >
                            <Clock size={12} />
                            {deadlineInfo.text}
                          </span>
                        )}
                      </div>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 6, flexWrap: 'wrap', gap: 10 }}>
                      {isCompleted ? (
                        <div style={{ fontSize: 12, color: '#94A3B8' }}>
                          {t('date') || 'Sana'}: {testItem.result?.date} • {t('score') || 'Ball'}: {testItem.result?.score}/{testItem.result?.max_score}
                        </div>
                      ) : (
                        <div style={{ fontSize: 12, color: '#94A3B8' }}>
                          O'tish bali: <b>{testItem.passing_score}%</b>
                        </div>
                      )}

                      <Link
                        to={
                          isCompleted
                            ? `/results/${testItem.result?.score ? testItem.id : testItem.id}`
                            : isInProgress
                            ? `/take/${testItem.attempt_id}`
                            : `/tests/${testItem.id}`
                        }
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          minHeight: 40,
                          padding: '8px 18px',
                          borderRadius: 12,
                          background: isCompleted
                            ? 'rgba(255,255,255,0.08)'
                            : isInProgress
                            ? 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)'
                            : 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                          color: isCompleted || isInProgress ? '#fff' : '#0F172A',
                          fontWeight: 800,
                          fontSize: 13,
                          textDecoration: 'none',
                          boxShadow: !isCompleted && !isInProgress ? '0 4px 14px rgba(245, 158, 11, 0.3)' : 'none',
                        }}
                      >
                        {isCompleted ? (
                          <>
                            <span>{t('group_view_result') || "Natijani ko'rish"}</span>
                            <ArrowRight size={14} />
                          </>
                        ) : isInProgress ? (
                          <>
                            <span>Davom ettirish ⚡️</span>
                            <ArrowRight size={14} />
                          </>
                        ) : (
                          <>
                            <span>{t('group_start_test') || 'Boshlash 🚀'}</span>
                            <ArrowRight size={14} />
                          </>
                        )}
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: Live Group Atmosphere & 3D Podium */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Award size={20} color="#F59E0B" />
              {t('group_live_leaderboard')}
            </h2>
            <span style={{ fontSize: 12, color: '#94A3B8' }}>
              {t('group_total_students').replace('{count}', String(leaderboard.length))}
            </span>
          </div>

          {leaderboard.length === 0 ? (
            <div
              style={{
                background: 'var(--card-bg, #1E293B)',
                borderRadius: 18,
                padding: '30px 20px',
                textAlign: 'center',
                color: '#94A3B8',
                fontSize: 14,
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              {t('group_no_one_tested')}
            </div>
          ) : (
            <div>
              {/* 3D Group Podium (Top 3 Students) */}
              <div
                style={{
                  background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.85) 0%, rgba(15, 23, 42, 0.95) 100%)',
                  borderRadius: 22,
                  padding: '22px 14px 0',
                  border: '1.5px solid rgba(245, 158, 11, 0.3)',
                  boxShadow: '0 12px 35px rgba(0, 0, 0, 0.3)',
                  marginBottom: 16,
                  overflow: 'hidden',
                }}
              >
                <div style={{ textAlign: 'center', marginBottom: 16 }}>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 800, color: '#FBBF24', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    <Trophy size={14} color="#F59E0B" />
                    <span>Guruh Shohsupasi</span>
                  </div>
                  <h3 style={{ margin: '3px 0 0', fontSize: 17, fontWeight: 800, color: '#FFFFFF' }}>
                    Top-3 Yetakchilar
                  </h3>
                </div>

                {/* Podium Columns */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'flex-end',
                    justifyContent: 'center',
                    gap: 10,
                    maxWidth: 420,
                    margin: '0 auto',
                  }}
                >
                  {/* 2nd Place: Left (Silver) */}
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
                    {top2 ? (
                      <>
                        <div style={{ fontSize: 20, marginBottom: 2 }}>🥈</div>
                        <div
                          style={{
                            width: 50,
                            height: 50,
                            borderRadius: '50%',
                            background: 'linear-gradient(135deg, #475569, #334155)',
                            border: '2.5px solid #94A3B8',
                            boxShadow: '0 0 15px rgba(148, 163, 184, 0.45)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: 16,
                            fontWeight: 800,
                            color: '#F8FAFC',
                            marginBottom: 6,
                          }}
                        >
                          {getInitials(top2.student_name)}
                        </div>
                        <div
                          style={{
                            fontSize: 12,
                            fontWeight: 800,
                            color: top2.is_me ? '#FBBF24' : '#F1F5F9',
                            maxWidth: 90,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            marginBottom: 2,
                          }}
                          title={top2.student_name}
                        >
                          {top2.student_name.split(' ')[0]} {top2.is_me && '(Siz)'}
                        </div>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#38BDF8', marginBottom: 8 }}>
                          {top2.avg_test_pct}% ({top2.bmb_grade})
                        </div>
                      </>
                    ) : (
                      <div style={{ height: 110, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748B', fontSize: 12 }}>—</div>
                    )}

                    {/* 2nd Pedestal Pillar */}
                    <div
                      style={{
                        width: '100%',
                        height: 90,
                        background: 'linear-gradient(180deg, rgba(148, 163, 184, 0.45) 0%, rgba(71, 85, 105, 0.7) 100%)',
                        border: '2px solid #94A3B8',
                        borderBottom: 'none',
                        borderRadius: '14px 14px 0 0',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        boxShadow: '0 -4px 12px rgba(148, 163, 184, 0.2)',
                      }}
                    >
                      <span style={{ fontSize: 24, fontWeight: 900, color: '#F1F5F9' }}>2</span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: '#CBD5E1', textTransform: 'uppercase' }}>O'rin</span>
                    </div>
                  </div>

                  {/* 1st Place: Center (Gold, Tallest) */}
                  <div style={{ flex: 1.15, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
                    {top1 ? (
                      <>
                        <div className="gold-crown-anim" style={{ fontSize: 28, marginBottom: 2 }}>👑</div>
                        <div
                          style={{
                            width: 62,
                            height: 62,
                            borderRadius: '50%',
                            background: 'linear-gradient(135deg, #B45309, #78350F)',
                            border: '3px solid #F59E0B',
                            boxShadow: '0 0 25px rgba(245, 158, 11, 0.7)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: 18,
                            fontWeight: 900,
                            color: '#FEF08A',
                            marginBottom: 6,
                          }}
                        >
                          {getInitials(top1.student_name)}
                        </div>
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: 900,
                            color: top1.is_me ? '#FBBF24' : '#FFFFFF',
                            maxWidth: 105,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            marginBottom: 2,
                          }}
                          title={top1.student_name}
                        >
                          {top1.student_name.split(' ')[0]} {top1.is_me && '(Siz)'}
                        </div>
                        <div style={{ fontSize: 12, fontWeight: 800, color: '#F59E0B', marginBottom: 8 }}>
                          🔥 {top1.avg_test_pct}% ({top1.bmb_grade})
                        </div>
                      </>
                    ) : (
                      <div style={{ height: 125, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748B', fontSize: 12 }}>—</div>
                    )}

                    {/* 1st Pedestal Pillar */}
                    <div
                      style={{
                        width: '100%',
                        height: 125,
                        background: 'linear-gradient(180deg, rgba(245, 158, 11, 0.55) 0%, rgba(180, 83, 9, 0.85) 100%)',
                        border: '2.5px solid #F59E0B',
                        borderBottom: 'none',
                        borderRadius: '16px 16px 0 0',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        boxShadow: '0 -6px 20px rgba(245, 158, 11, 0.35)',
                      }}
                    >
                      <span style={{ fontSize: 30, fontWeight: 900, color: '#FEF08A' }}>1</span>
                      <span style={{ fontSize: 11, fontWeight: 800, color: '#FDE68A', textTransform: 'uppercase' }}>G'olib</span>
                    </div>
                  </div>

                  {/* 3rd Place: Right (Bronze) */}
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
                    {top3 ? (
                      <>
                        <div style={{ fontSize: 20, marginBottom: 2 }}>🥉</div>
                        <div
                          style={{
                            width: 48,
                            height: 48,
                            borderRadius: '50%',
                            background: 'linear-gradient(135deg, #78350F, #451A03)',
                            border: '2.5px solid #D97706',
                            boxShadow: '0 0 15px rgba(217, 119, 6, 0.45)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: 15,
                            fontWeight: 800,
                            color: '#FED7AA',
                            marginBottom: 6,
                          }}
                        >
                          {getInitials(top3.student_name)}
                        </div>
                        <div
                          style={{
                            fontSize: 12,
                            fontWeight: 800,
                            color: top3.is_me ? '#FBBF24' : '#F1F5F9',
                            maxWidth: 90,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            marginBottom: 2,
                          }}
                          title={top3.student_name}
                        >
                          {top3.student_name.split(' ')[0]} {top3.is_me && '(Siz)'}
                        </div>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#F97316', marginBottom: 8 }}>
                          {top3.avg_test_pct}% ({top3.bmb_grade})
                        </div>
                      </>
                    ) : (
                      <div style={{ height: 95, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748B', fontSize: 12 }}>—</div>
                    )}

                    {/* 3rd Pedestal Pillar */}
                    <div
                      style={{
                        width: '100%',
                        height: 70,
                        background: 'linear-gradient(180deg, rgba(217, 119, 6, 0.35) 0%, rgba(120, 53, 15, 0.65) 100%)',
                        border: '2px solid #D97706',
                        borderBottom: 'none',
                        borderRadius: '14px 14px 0 0',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        boxShadow: '0 -4px 12px rgba(217, 119, 6, 0.2)',
                      }}
                    >
                      <span style={{ fontSize: 22, fontWeight: 900, color: '#FED7AA' }}>3</span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: '#FDBA74', textTransform: 'uppercase' }}>O'rin</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Motivational Gap Banner */}
              {my_rank && (
                <div
                  style={{
                    padding: '14px 18px',
                    borderRadius: 14,
                    background:
                      my_rank <= 3
                        ? 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(16, 185, 129, 0.15) 100%)'
                        : 'linear-gradient(135deg, rgba(56, 189, 248, 0.15) 0%, rgba(245, 158, 11, 0.15) 100%)',
                    border:
                      my_rank <= 3
                        ? '1.5px solid rgba(245, 158, 11, 0.45)'
                        : '1.5px solid rgba(56, 189, 248, 0.35)',
                    marginBottom: 16,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                  }}
                >
                  <div style={{ fontSize: 24 }}>{my_rank <= 3 ? '👑' : '🎯'}</div>
                  <div style={{ fontSize: 13, color: '#F8FAFC', lineHeight: 1.5 }}>
                    {my_rank <= 3 ? (
                      <>
                        <b>Ajoyib g'alaba!</b> Siz hozirda shohsupadasiz (<b>{my_rank}-o'rin</b>)!
                        O'rningizni mustahkam saqlang va keyingi testlarda ham rekord ko'rsating!
                      </>
                    ) : (
                      <>
                        Siz hozirda <b>{my_rank}-o'rindasiz</b>. Shohsupaga (3-o'ringa) yetish uchun yana{' '}
                        <b style={{ color: '#FBBF24' }}>{gapToPodium}% ball</b> kerak! Qani, yangi test yechib o'rningizni oshiring! 🚀
                      </>
                    )}
                  </div>
                </div>
              )}

              {/* Remaining Students List (Ranks 4+) */}
              {restStudents.length > 0 && (
                <div
                  style={{
                    background: 'var(--card-bg, #1E293B)',
                    borderRadius: 18,
                    border: '1px solid rgba(255,255,255,0.08)',
                    overflow: 'hidden',
                    boxShadow: '0 4px 14px rgba(0,0,0,0.1)',
                  }}
                >
                  <div
                    style={{
                      padding: '12px 18px',
                      background: 'rgba(255, 255, 255, 0.03)',
                      borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                      fontSize: 12,
                      fontWeight: 700,
                      color: '#94A3B8',
                    }}
                  >
                    Barcha O'quvchilar Ro'yxati ({leaderboard.length} ta)
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    {restStudents.map((item) => (
                      <div
                        key={item.student_id}
                        className={item.is_me ? 'neon-rank-highlight' : ''}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '13px 18px',
                          borderBottom: '1px solid rgba(255,255,255,0.05)',
                          background: item.is_me
                            ? 'linear-gradient(90deg, rgba(245, 158, 11, 0.22) 0%, rgba(245, 158, 11, 0.08) 100%)'
                            : undefined,
                          borderLeft: item.is_me ? '3px solid #F59E0B' : undefined,
                        }}
                      >
                        {/* Rank & Name */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          <span
                            style={{
                              width: 28,
                              height: 28,
                              borderRadius: 8,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontWeight: 800,
                              fontSize: 13,
                              background: 'rgba(255,255,255,0.06)',
                              color: item.is_me ? '#FBBF24' : '#94A3B8',
                            }}
                          >
                            #{item.rank}
                          </span>

                          <div>
                            <div style={{ fontSize: 14, fontWeight: 700, color: item.is_me ? '#F59E0B' : '#F8FAFC' }}>
                              {item.student_name}{' '}
                              {item.is_me && (
                                <span
                                  style={{
                                    fontSize: 11,
                                    background: '#F59E0B',
                                    color: '#0F172A',
                                    padding: '1px 6px',
                                    borderRadius: 6,
                                    fontWeight: 800,
                                    marginLeft: 6,
                                  }}
                                >
                                  Siz
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: 11, color: '#94A3B8' }}>
                              {t('group_tests_taken').replace('{n}', String(item.tests_taken))} • BMB: <b>{item.bmb_grade}</b>
                            </div>
                          </div>
                        </div>

                        {/* Percentage & Grade */}
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: 14, fontWeight: 800, color: '#10B981' }}>
                            {item.avg_test_pct > 0 ? `${item.avg_test_pct}%` : '0%'}
                          </div>
                          <div style={{ fontSize: 11, color: '#94A3B8' }}>
                            {item.last_active}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Classroom Projector QR Modal */}
      <ClassroomQrModal
        isOpen={qrOpen}
        onClose={() => setQrOpen(false)}
        title={group.name}
        code={group.invite_code}
        webUrl={`${window.location.origin}/groups/${group.id}`}
        tmaUrl={`https://t.me/grandec_bot/app?startapp=group_${group.id}`}
        subtitle="Sinfxona proyektorida yoki telefonda o'quvchilarga ko'rsating — guruhga qo'shilish va vazifalarni ochish uchun"
      />
    </div>
  );
}
