import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useLang } from '../i18n/LangContext';
import {
  MockTests,
  type MockLeaderboardResponse,
  type MockTestCreateResponse,
  School,
  type WeeklyReportRow,
} from '../lib/api';
import AnalyticsChart from '../components/AnalyticsChart';
import AttendancePanel from '../components/AttendancePanel';
import { UsersIcon } from '../components/icons';
import {
  Send,
  PlusCircle,
  QrCode,
  Download,
  Sparkles,
  Radio,
  ChevronRight,
  Clock,
  Calendar,
  CheckSquare,
  Trash2,
  BookOpen,
} from 'lucide-react';
import ClassroomQrModal from '../components/ClassroomQrModal';
import TeacherHomeworkWizard from '../components/TeacherHomeworkWizard';
import HomeworkLiveBoard from '../components/HomeworkLiveBoard';
import type {
  AnalyticsData,
  EssayBoard,
  GroupMember,
  RecentResult,
  SchoolGroup,
  TeacherOverview,
} from '../lib/school';
import { errMessage } from '../lib/school';

const EMPTY_GROUPS: SchoolGroup[] = [];
const EMPTY_RECENT_RESULTS: RecentResult[] = [];

export default function TeacherDashboard() {
  const { t } = useLang();
  const [liveHomeworkId, setLiveHomeworkId] = useState<number | null>(null);
  const [data, setData] = useState<TeacherOverview | null>(null);
  const [activity, setActivity] = useState<AnalyticsData | null>(null);
  const [board, setBoard] = useState<EssayBoard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [weeklyReports, setWeeklyReports] = useState<WeeklyReportRow[]>([]);

  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const activeMode = tabParam === 'live' || tabParam === 'vedomost' ? tabParam : 'converter';

  const setTab = (mode: 'converter' | 'live' | 'vedomost') => {
    setSearchParams({ tab: mode });
  };

  const openClassroomModal = (mock: MockTestCreateResponse) => {
    setQrModalData({
      isOpen: true,
      title: mock.title,
      code: mock.mock_code,
      webUrl: `${window.location.origin}/tests/${mock.test_id}`,
      subtitle: t('teacher_live_ready'),
    });
  };

  // Quick Mock Creator state
  const [mockTitle, setMockTitle] = useState('');
  const [mockKeys, setMockKeys] = useState('');
  const [mockTime, setMockTime] = useState(60);
  const [mockBusy, setMockBusy] = useState(false);
  const [mockCreated, setMockCreated] = useState<MockTestCreateResponse | null>(null);
  const [mockErr, setMockErr] = useState<string | null>(null);
  const [copiedMock, setCopiedMock] = useState(false);

  // Quick Mock Leaderboard View
  const [activeMockId, setActiveMockId] = useState<number | null>(null);
  const [leaderboardData, setLeaderboardData] = useState<MockLeaderboardResponse | null>(null);
  const [leaderboardLoading, setLeaderboardLoading] = useState(false);
  const [leaderboardErr, setLeaderboardErr] = useState<string | null>(null);

  // Classroom QR Modal state
  const [qrModalData, setQrModalData] = useState<{
    isOpen: boolean;
    title: string;
    code?: string;
    webUrl: string;
    tmaUrl?: string;
    subtitle?: string;
  } | null>(null);

  const createQuickMock = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mockKeys.trim()) return;
    setMockBusy(true);
    setMockErr(null);
    setMockCreated(null);
    try {
      const res = await MockTests.create({
        title: mockTitle.trim() || undefined,
        keys: mockKeys.trim(),
        time_limit: mockTime,
      });
      setMockCreated(res);
      setMockKeys('');
      setMockTitle('');
    } catch (e2) {
      setMockErr(e2 instanceof Error ? e2.message : 'Mock test yaratishda xatolik yuz berdi.');
    } finally {
      setMockBusy(false);
    }
  };

  const viewMockLeaderboard = async (testId: number) => {
    setActiveMockId(testId);
    setLeaderboardLoading(true);
    setLeaderboardErr(null);
    try {
      const res = await MockTests.leaderboard(testId);
      setLeaderboardData(res);
    } catch (e2) {
      setLeaderboardErr(e2 instanceof Error ? e2.message : 'Reytingni yuklab bo‘lmadi.');
    } finally {
      setLeaderboardLoading(false);
    }
  };

  const copyMockCode = (code: string) => {
    void navigator.clipboard.writeText(code);
    setCopiedMock(true);
    setTimeout(() => setCopiedMock(false), 2500);
  };

  // Stage 4: Teacher Workspace 3.0 — Homework Wizard Modal state
  const [hwModalOpen, setHwModalOpen] = useState(false);
  const [hwGroupId, setHwGroupId] = useState<number | null>(null);

  const refreshOverview = useCallback(() => {
    School.teacher()
      .then((r) => {
        setData(r as unknown as TeacherOverview);
      })
      .catch((e: unknown) => {
        setErr(errMessage(e));
      });
  }, []);

  const handleDeleteHomework = async (homeworkId: number) => {
    if (!window.confirm(t('td_delete_hw_confirm'))) return;
    try {
      await School.deleteHomework(homeworkId);
      refreshOverview();
    } catch (e2) {
      alert(e2 instanceof Error ? e2.message : 'Vazifani o‘chirishda xatolik yuz berdi.');
    }
  };

  useEffect(() => {
    let alive = true;
    School.weeklyReports().then(({ results }) => {
      if (alive) setWeeklyReports(results);
    }).catch(() => { /* report archive is supplementary */ });
    // GET /api/v1/school/teacher/ — groups, student_count,
    // published_tests, active_topics, recent_results.
    School.teacher()
      .then((r) => {
        if (alive) { setData(r as unknown as TeacherOverview); setLoading(false); }
      })
      .catch((e: unknown) => {
        if (alive) { setErr(errMessage(e)); setLoading(false); }
      });
    // GET /api/v1/school/analytics/?days=14 — activity strip for the dashboard.
    School.analytics(14)
      .then((r) => {
        if (alive) setActivity(r as unknown as AnalyticsData);
      })
      .catch(() => {
        /* activity is supplementary — dashboard works without it */
      });
    // GET /api/v1/school/essay-leaderboard/ — essay totals + top writers.
    School.essayLeaderboard()
      .then((r) => {
        if (alive) setBoard(r as unknown as EssayBoard);
      })
      .catch(() => {
        /* supplementary */
      });
    return () => {
      alive = false;
    };
  }, []);

  const groups = data?.groups ?? EMPTY_GROUPS;
  const recent = data?.recent_results ?? EMPTY_RECENT_RESULTS;

  const todayStr = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const todaySubmissions = useMemo(
    () => recent.filter((r) => r.date && r.date.startsWith(todayStr)),
    [recent, todayStr],
  );
  const todayAvgPct = useMemo(() => {
    if (todaySubmissions.length === 0) return 0;
    const sum = todaySubmissions.reduce((acc, r) => acc + (Number(r.percentage) || 0), 0);
    return Math.round(sum / todaySubmissions.length);
  }, [todaySubmissions]);

  // Aggregate unique students across the teacher's groups (students lists).
  const students: GroupMember[] = useMemo(() => {
    const seen = new Map<number, GroupMember>();
    for (const g of groups) {
      for (const s of g.students ?? []) seen.set(s.id, s);
    }
    return [...seen.values()].sort((a, b) => a.full_name.localeCompare(b.full_name));
  }, [groups]);

  const exportVedomostCsv = () => {
    const headers = ['FIO', 'Email', 'Tarif', 'Testlar soni', 'Esselar soni', 'Guruhlar'];
    const rows = students.map((s) => [
      `"${s.full_name}"`,
      `"${s.email}"`,
      `"${s.pro_status_label ?? 'PRO'}"`,
      s.tests_count ?? 0,
      s.essays_count ?? 0,
      `"${groups.filter((g) => (g.students ?? []).some((m) => m.id === s.id)).map((g) => g.name).join(', ')}"`,
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,\uFEFF' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `grandec-vedomost-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loading && !err) return <p className="muted" role="status" aria-live="polite">{t('loading')}</p>;

  return (
    <div>
      <h1>
        <UsersIcon size={24} className="ico" /> {t('teacher_dashboard')}
      </h1>
      {err && <p className="error" role="alert">{err}</p>}

      {/* 3 Asosiy Rejim Tablari (Stage 5) */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          background: 'var(--bg-surface)',
          padding: 6,
          borderRadius: 16,
          border: '1px solid var(--border-subtle)',
          margin: '16px 0 24px',
          maxWidth: 620,
        }}
      >
        <button
          type="button"
          onClick={() => setTab('converter')}
          style={{
            flex: 1,
            padding: '10px 16px',
            borderRadius: 12,
            border: activeMode === 'converter' ? '1px solid rgba(99, 102, 241, 0.5)' : '1px solid transparent',
            background: activeMode === 'converter' ? 'linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(99, 102, 241, 0.08) 100%)' : 'transparent',
            color: activeMode === 'converter' ? '#818cf8' : 'var(--text-secondary)',
            fontWeight: 800,
            fontSize: '0.92rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            transition: 'all 0.2s ease',
          }}
        >
          <Sparkles size={16} /> AI Konvertor
        </button>

        <button
          type="button"
          onClick={() => setTab('live')}
          style={{
            flex: 1,
            padding: '10px 16px',
            borderRadius: 12,
            border: activeMode === 'live' ? '1px solid rgba(245, 158, 11, 0.5)' : '1px solid transparent',
            background: activeMode === 'live' ? 'linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(245, 158, 11, 0.08) 100%)' : 'transparent',
            color: activeMode === 'live' ? '#F59E0B' : 'var(--text-secondary)',
            fontWeight: 800,
            fontSize: '0.92rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            transition: 'all 0.2s ease',
          }}
        >
          <Radio size={16} /> Jonli tablo
        </button>

        <button
          type="button"
          onClick={() => setTab('vedomost')}
          style={{
            flex: 1,
            padding: '10px 16px',
            borderRadius: 12,
            border: activeMode === 'vedomost' ? '1px solid rgba(14, 165, 233, 0.5)' : '1px solid transparent',
            background: activeMode === 'vedomost' ? 'linear-gradient(135deg, rgba(14, 165, 233, 0.15) 0%, rgba(14, 165, 233, 0.08) 100%)' : 'transparent',
            color: activeMode === 'vedomost' ? '#0ea5e9' : 'var(--text-secondary)',
            fontWeight: 800,
            fontSize: '0.92rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            transition: 'all 0.2s ease',
          }}
        >
          <span>📊</span> Vedomost
        </button>
      </div>

      {/* 🌟 4 ASOSIY AMAL (Teacher Workspace 3.0 Action Hub) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: 16,
          margin: '20px 0 24px',
        }}
      >
        {/* AMAL 1: DAVOMAT OLISH */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => {
            const attElem = document.getElementById('attendance-workspace');
            if (attElem) attElem.scrollIntoView({ behavior: 'smooth' });
          }}
          className="card"
          style={{
            margin: 0,
            cursor: 'pointer',
            background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(5, 150, 105, 0.22) 100%)',
            border: '1.5px solid rgba(16, 185, 129, 0.45)',
            borderRadius: 18,
            padding: '20px',
            boxShadow: '0 8px 24px rgba(16, 185, 129, 0.12)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 24, background: 'rgba(16, 185, 129, 0.2)', padding: '6px 10px', borderRadius: 12 }}>
                  📋
                </span>
                <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 900, color: '#10B981' }}>
                  1. {t('td_action_attendance')}
                </h3>
              </div>
              <ChevronRight size={18} color="#10B981" />
            </div>
            <p className="muted small" style={{ margin: '0 0 12px', lineHeight: 1.5 }}>
              Bugungi darslar davomati va o&apos;quvchilar ro&apos;yxati (4-darajali tezkor qayd).
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span
              style={{
                fontSize: 12,
                fontWeight: 800,
                padding: '4px 10px',
                borderRadius: 8,
                background: 'rgba(16, 185, 129, 0.2)',
                color: '#10B981',
              }}
            >
              {data?.attendance_today_summary
                ? `${data.attendance_today_summary.finalized_count}/${data.attendance_today_summary.total_groups} guruh yakunlangan`
                : 'Davomat tizimi'}
            </span>
            <span style={{ fontSize: 13, fontWeight: 800, color: '#10B981' }}>Boshlash →</span>
          </div>
        </div>

        {/* AMAL 2: UY VAZIFASI BERISH */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => {
            if (groups.length > 0 && !hwGroupId) setHwGroupId(groups[0].id);
            setHwModalOpen(true);
          }}
          className="card"
          style={{
            margin: 0,
            cursor: 'pointer',
            background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(217, 119, 6, 0.22) 100%)',
            border: '1.5px solid rgba(245, 158, 11, 0.45)',
            borderRadius: 18,
            padding: '20px',
            boxShadow: '0 8px 24px rgba(245, 158, 11, 0.12)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 24, background: 'rgba(245, 158, 11, 0.2)', padding: '6px 10px', borderRadius: 12 }}>
                  📝
                </span>
                <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 900, color: '#F59E0B' }}>
                  2. {t('td_action_homework')}
                </h3>
              </div>
              <ChevronRight size={18} color="#F59E0B" />
            </div>
            <p className="muted small" style={{ margin: '0 0 12px', lineHeight: 1.5 }}>
              Guruhlarga test, esse yoki topshiriq biriktirish va muddat belgilash.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span
              style={{
                fontSize: 12,
                fontWeight: 800,
                padding: '4px 10px',
                borderRadius: 8,
                background: 'rgba(245, 158, 11, 0.2)',
                color: '#F59E0B',
              }}
            >
              {data?.assignments ? `${data.assignments.length} ta faol vazifa` : '+ Yangi vazifa'}
            </span>
            <span style={{ fontSize: 13, fontWeight: 800, color: '#F59E0B' }}>Vazifa berish →</span>
          </div>
        </div>

        {/* AMAL 3: GURUHLARIM */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => {
            const grpElem = document.getElementById('groups-workspace');
            if (grpElem) grpElem.scrollIntoView({ behavior: 'smooth' });
          }}
          className="card"
          style={{
            margin: 0,
            cursor: 'pointer',
            background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(79, 70, 229, 0.22) 100%)',
            border: '1.5px solid rgba(99, 102, 241, 0.45)',
            borderRadius: 18,
            padding: '20px',
            boxShadow: '0 8px 24px rgba(99, 102, 241, 0.12)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 24, background: 'rgba(99, 102, 241, 0.2)', padding: '6px 10px', borderRadius: 12 }}>
                  👥
                </span>
                <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 900, color: '#818cf8' }}>
                  3. {t('td_action_groups')}
                </h3>
              </div>
              <ChevronRight size={18} color="#818cf8" />
            </div>
            <p className="muted small" style={{ margin: '0 0 12px', lineHeight: 1.5 }}>
              Sinfxona guruhlari, a&apos;zolar ro&apos;yxati, taklif kodlari va QR proyektor.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span
              style={{
                fontSize: 12,
                fontWeight: 800,
                padding: '4px 10px',
                borderRadius: 8,
                background: 'rgba(99, 102, 241, 0.2)',
                color: '#818cf8',
              }}
            >
              {groups.length} ta guruh · {data?.student_count ?? 0} o&apos;quvchi
            </span>
            <span style={{ fontSize: 13, fontWeight: 800, color: '#818cf8' }}>Boshqarish →</span>
          </div>
        </div>

        {/* AMAL 4: NATIJALAR */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => {
            const resElem = document.getElementById('results-workspace');
            if (resElem) resElem.scrollIntoView({ behavior: 'smooth' });
          }}
          className="card"
          style={{
            margin: 0,
            cursor: 'pointer',
            background: 'linear-gradient(135deg, rgba(14, 165, 233, 0.12) 0%, rgba(2, 132, 199, 0.22) 100%)',
            border: '1.5px solid rgba(14, 165, 233, 0.45)',
            borderRadius: 18,
            padding: '20px',
            boxShadow: '0 8px 24px rgba(14, 165, 233, 0.12)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 24, background: 'rgba(14, 165, 233, 0.2)', padding: '6px 10px', borderRadius: 12 }}>
                  📊
                </span>
                <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 900, color: '#0ea5e9' }}>
                  4. {t('td_action_results')}
                </h3>
              </div>
              <ChevronRight size={18} color="#0ea5e9" />
            </div>
            <p className="muted small" style={{ margin: '0 0 12px', lineHeight: 1.5 }}>
              O&apos;quvchilar natijalari, ballar jurnali (Vedomost) va CSV eksport.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span
              style={{
                fontSize: 12,
                fontWeight: 800,
                padding: '4px 10px',
                borderRadius: 8,
                background: 'rgba(14, 165, 233, 0.2)',
                color: '#0ea5e9',
              }}
            >
              {recent.length} ta topshirilgan · O&apos;rtacha: {todayAvgPct}%
            </span>
            <span style={{ fontSize: 13, fontWeight: 800, color: '#0ea5e9' }}>Ko&apos;rish →</span>
          </div>
        </div>
      </div>

      {/* 📅 BUGUNGI DARSLAR (Today's Lessons Schedule) */}
      {data?.today_lessons && data.today_lessons.length > 0 && (
        <section style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
            <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8, fontSize: '1.25rem', fontWeight: 800 }}>
              <Calendar size={20} className="ico" />
              <span>{t('td_today_lessons')} ({data.today_lessons.length})</span>
            </h2>
            <span className="muted small">
              {todayStr} · {data.attendance_today_summary?.finalized_count ?? 0} yakunlandi, {data.attendance_today_summary?.not_started_count ?? 0} kutilmoqda
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
            {data.today_lessons.map((lesson) => {
              const isFinal = lesson.status === 'finalized';
              const isDraft = lesson.status === 'draft';
              const statusBg = isFinal
                ? 'rgba(16, 185, 129, 0.15)'
                : isDraft
                  ? 'rgba(245, 158, 11, 0.15)'
                  : 'rgba(99, 102, 241, 0.12)';
              const statusColor = isFinal ? '#10B981' : isDraft ? '#F59E0B' : '#818cf8';
              const statusLabel = isFinal
                ? `${t('td_lesson_finalized')} (${lesson.present_count} keldi, ${lesson.absent_count} kelmadi)`
                : isDraft
                  ? `${t('td_lesson_continue_att')} (${lesson.present_count} belgilandi)`
                  : t('td_lesson_start_att');

              return (
                <div
                  key={`${lesson.group_id}-${lesson.session_id ?? 'new'}`}
                  className="card"
                  style={{
                    margin: 0,
                    padding: '16px',
                    borderRadius: 14,
                    border: `1px solid ${isFinal ? 'rgba(16, 185, 129, 0.3)' : 'var(--border)'}`,
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    gap: 12,
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <strong style={{ fontSize: 16 }}>{lesson.group_name}</strong>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          padding: '2px 8px',
                          borderRadius: 6,
                          background: statusBg,
                          color: statusColor,
                        }}
                      >
                        {isFinal ? 'Yakunlangan' : isDraft ? 'Qoralama' : 'Olinmagan'}
                      </span>
                    </div>
                    <p className="muted small" style={{ margin: 0 }}>
                      {lesson.student_count} ta talaba · {lesson.start_time ? `${lesson.start_time} - ${lesson.end_time || ''}` : 'Bugungi dars'}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      const attElem = document.getElementById('attendance-workspace');
                      if (attElem) attElem.scrollIntoView({ behavior: 'smooth' });
                    }}
                    className={`btn sm ${isFinal ? '' : 'primary'}`}
                    style={{ width: '100%', justifyContent: 'center', fontWeight: 700 }}
                  >
                    <CheckSquare size={14} />
                    <span>{statusLabel}</span>
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 🕒 YAQINLASHAYOTGAN MUDDATLAR VA VAZIFALAR (Assignments & Upcoming Deadlines) */}
      <section id="homework-workspace" style={{ marginBottom: 26 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 10 }}>
          <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8, fontSize: '1.25rem', fontWeight: 800 }}>
            <Clock size={20} className="ico" />
            <span>{t('td_assignments_title')} ({data?.assignments?.length ?? 0})</span>
          </h2>
          <button
            type="button"
            onClick={() => {
              if (groups.length > 0 && !hwGroupId) setHwGroupId(groups[0].id);
              setHwModalOpen(true);
            }}
            className="btn primary sm"
            style={{ fontWeight: 800, display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <PlusCircle size={15} />
            <span>+ {t('td_action_homework')}</span>
          </button>
        </div>

        {(!data?.assignments || data.assignments.length === 0) ? (
          <div className="card" style={{ padding: 20, textAlign: 'center' }}>
            <p className="muted" style={{ margin: '0 0 12px' }}>{t('td_no_assignments')}</p>
            <button
              type="button"
              onClick={() => {
                if (groups.length > 0 && !hwGroupId) setHwGroupId(groups[0].id);
                setHwModalOpen(true);
              }}
              className="btn primary sm"
            >
              + {t('td_action_homework')}
            </button>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
            {data.assignments.slice(0, 8).map((hw) => {
              const due = new Date(hw.due_date);
              const isOverdue = hw.is_overdue;
              const dueLabel = due.toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              });

              return (
                <div
                  key={hw.id}
                  className="card"
                  style={{
                    margin: 0,
                    padding: 16,
                    borderRadius: 14,
                    border: isOverdue ? '1px solid rgba(239, 68, 68, 0.35)' : '1px solid var(--border)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    gap: 12,
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
                      <strong style={{ fontSize: 15 }}>{hw.title}</strong>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          padding: '2px 7px',
                          borderRadius: 6,
                          background: isOverdue ? 'rgba(239, 68, 68, 0.15)' : 'rgba(59, 130, 246, 0.15)',
                          color: isOverdue ? '#EF4444' : '#3B82F6',
                        }}
                      >
                        {isOverdue ? t('td_overdue_badge') : hw.type.toUpperCase()}
                      </span>
                    </div>
                    <p className="muted small" style={{ margin: '0 0 8px' }}>
                      {hw.group_name} · Muddat: {dueLabel}
                    </p>
                    {hw.description ? (
                      <p className="small" style={{ margin: '0 0 10px', color: 'var(--ink-soft)', lineHeight: 1.4 }}>
                        {hw.description}
                      </p>
                    ) : null}
                  </div>

                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12, marginBottom: 4 }}>
                      <span className="muted">Topshirildi:</span>
                      <strong>
                        {hw.submissions_count} / {hw.total_students} {t('td_completed_badge')}
                      </strong>
                    </div>
                    <div
                      style={{
                        height: 6,
                        background: 'rgba(255,255,255,0.08)',
                        borderRadius: 3,
                        overflow: 'hidden',
                        marginBottom: 10,
                      }}
                    >
                      <div
                        style={{
                          height: '100%',
                          width: `${hw.total_students > 0 ? Math.min(100, Math.round((hw.submissions_count / hw.total_students) * 100)) : 0}%`,
                          background: isOverdue ? '#EF4444' : 'linear-gradient(90deg, #10B981, #059669)',
                          borderRadius: 3,
                        }}
                      />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                      <button
                        type="button"
                        onClick={() => setLiveHomeworkId(hw.id)}
                        className="btn sm"
                        style={{ padding: '4px 10px', fontSize: 11, minHeight: 32 }}
                      >
                        {t('hw_live_open', 'Kuzatish')}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteHomework(hw.id)}
                        className="btn sm"
                        style={{
                          padding: '4px 8px',
                          fontSize: 11,
                          color: '#EF4444',
                          border: '1px solid rgba(239, 68, 68, 0.25)',
                          background: 'transparent',
                        }}
                        title="Vazifani bekor qilish"
                      >
                        <Trash2 size={12} />
                        <span>O&apos;chirish</span>
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {liveHomeworkId !== null && (
        <HomeworkLiveBoard homeworkId={liveHomeworkId} onClose={() => setLiveHomeworkId(null)} />
      )}

      {/* 📬 TEKSHIRISH NAVBATI (Review Queue: Essays & Submissions) */}
      {data?.review_queue && data.review_queue.length > 0 && (
        <section style={{ marginBottom: 26 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
            <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8, fontSize: '1.25rem', fontWeight: 800 }}>
              <BookOpen size={20} className="ico" />
              <span>{t('td_review_queue')} ({data.review_queue_count ?? data.review_queue.length})</span>
            </h2>
            <Link to="/teacher/essays" className="btn sm" style={{ fontWeight: 700 }}>
              {t('view_all')} ({data.review_queue_count ?? data.review_queue.length}) →
            </Link>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>{t('th_student')}</th>
                  <th>Mavzu</th>
                  <th>So&apos;zlar soni</th>
                  <th>Topshirilgan vaqt</th>
                  <th style={{ textAlign: 'right' }}>Amal</th>
                </tr>
              </thead>
              <tbody>
                {data.review_queue.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.student_name}</strong></td>
                    <td>{item.topic_title}</td>
                    <td>{item.word_count} so&apos;z</td>
                    <td className="muted small">{item.submitted_at ? item.submitted_at.slice(0, 16).replace('T', ' ') : '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <Link
                        to={`/teacher/essays/${item.id}/review`}
                        className="btn primary sm"
                        style={{ padding: '4px 10px', fontWeight: 700 }}
                      >
                        {t('td_review_now')} →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* 🌟 USTOZ BOSHQARUV PANELINING ASOSIY 2 TA FOKUSI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(300px, 100%), 1fr))', gap: '16px', marginBottom: '20px', marginTop: '16px' }}>
        {/* FOKUS 1: YANGI TEST YARATISH */}
        <div
          className="card"
          style={{
            margin: 0,
            background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(217, 119, 6, 0.2) 100%)',
            border: '1.5px solid rgba(245, 158, 11, 0.4)',
            borderRadius: '16px',
            padding: '20px',
            boxShadow: '0 8px 24px rgba(245, 158, 11, 0.12)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 24 }}>✨</span>
              <h2 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 800 }}>Yangi Test Yaratish</h2>
            </div>
            <p className="muted small" style={{ margin: '0 0 16px', lineHeight: 1.5 }}>
              Qog&apos;oz/PDF rasmidan 1 soniyada AI yordamida test tuzing yoki Smart Konstruktorda erkin yarating.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Link
              to="/teacher/ai-converter"
              className="btn primary sm"
              style={{ fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <span>✨</span> AI Vision Konvertor
            </Link>
            <Link
              to="/smart-create"
              className="btn sm"
              style={{ fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <span>🛠</span> Test Konstruktori
            </Link>
          </div>
        </div>

        {/* FOKUS 2: GURUHLARIM NATIJASI (VEDOMOST) */}
        <div
          className="card"
          style={{
            margin: 0,
            background: 'linear-gradient(135deg, rgba(14, 165, 233, 0.12) 0%, rgba(2, 132, 199, 0.2))',
            border: '1.5px solid rgba(14, 165, 233, 0.4)',
            borderRadius: '16px',
            padding: '20px',
            boxShadow: '0 8px 24px rgba(14, 165, 233, 0.12)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 24 }}>📊</span>
              <h2 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 800 }}>Guruhlarim Natijasi (Vedomost)</h2>
            </div>
            <p className="muted small" style={{ margin: '0 0 16px', lineHeight: 1.5 }}>
              O&apos;quvchilar natijalari, BMB foizlari va interaktiv davomat jurnali (Vedomost).
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Link
              to="/groups"
              className="btn primary sm"
              style={{
                fontWeight: 700,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: 'linear-gradient(135deg, #0ea5e9, #0284c7)',
                borderColor: '#0284c7',
              }}
            >
              <span>📊</span> Guruhlar Vedomosti
            </Link>
            <Link
              to="/tests"
              className="btn sm"
              style={{ fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <span>📑</span> Testlar Ro&apos;yxati
            </Link>
          </div>
        </div>
      </div>

      {/* Stat cards — parity with teacher_dashboard.html stat cards that the
          /teacher/ endpoint exposes (students, published tests, essay topics). */}
      <div className="grid">
        <div className="card stat stat-gradient-blue">
          <span className="stat-label">{t('students_count')}</span>
          <span className="stat-value">{data ? data.student_count : '…'}</span>
          <span className="muted small">{t('active_students_hint')}</span>
        </div>
        <div className="card stat stat-gradient-green">
          <span className="stat-label">{t('groups')}</span>
          <span className="stat-value">{groups.length}</span>
          <Link to="/groups">{t('view_all')} →</Link>
        </div>
        <div className="card stat stat-gradient-amber">
          <span className="stat-label">{t('stat_tests_created')}</span>
          <span className="stat-value">{data ? data.published_tests : '…'}</span>
          <span className="muted small">{t('active_status')}</span>
        </div>
        <div className="card stat stat-gradient-purple">
          <span className="stat-label">{t('essay_topics')}</span>
          <span className="stat-value">{data ? data.active_topics : '…'}</span>
          <Link to="/essays">{t('view_all')} →</Link>
        </div>
        <div className="card stat" style={{ background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(217, 119, 6, 0.08) 100%)', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
          <span className="stat-label">Bugun topshirildi</span>
          <span className="stat-value" style={{ color: '#F59E0B' }}>
            {todaySubmissions.length > 0 ? `${todaySubmissions.length} ta` : `${recent.length} ta`}
          </span>
          <span className="muted small">
            {todaySubmissions.length > 0 ? `O'rtacha: ${todayAvgPct}%` : 'So\'nggi natijalar'}
          </span>
        </div>
      </div>

      {/* 📡 Jonli Tablo & Classroom QR Proyektor (Stage 5) */}
      {(activeMode === 'live' || activeMode === 'converter') && (
        <div
          className="card bento-card"
          style={{
            marginTop: 18,
            background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, rgba(99, 102, 241, 0.08) 100%)',
            border: '1.5px solid rgba(245, 158, 11, 0.35)',
            borderRadius: '20px',
            padding: '24px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <span style={{ fontSize: 28 }}>📡</span>
              <h2 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 900 }}>
                Jonli Tablo & Sinfxona Proyektori
              </h2>
            </div>
            <p className="muted" style={{ margin: 0, fontSize: '0.92rem', maxWidth: 540 }}>
              {t('teacher_live_hint')}
            </p>
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={() => mockCreated && openClassroomModal(mockCreated)}
              disabled={!mockCreated}
              className="bento-btn bento-btn-gold"
              style={{ fontWeight: 800, padding: '0 22px', height: 46 }}
            >
              <QrCode size={18} />
              <span>{t('teacher_live_qr')}</span>
            </button>
            <button
              type="button"
              onClick={() => {
                if (mockCreated) {
                  viewMockLeaderboard(mockCreated.test_id);
                }
              }}
              disabled={!mockCreated}
              className="bento-btn bento-btn-indigo"
              style={{ fontWeight: 800, padding: '0 20px', height: 46 }}
            >
              <Radio size={18} />
              <span>Jonli Natijalar Tablosi</span>
            </button>
          </div>
        </div>
      )}

      {/* 🚀 Tezkor Mock Test Yaratish & BMB Reyting */}
      <div
        className="card"
        style={{
          marginTop: 18,
          background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.05) 0%, rgba(16, 185, 129, 0.05) 100%)',
          border: '1px solid rgba(59, 130, 246, 0.25)',
          borderRadius: '14px',
          padding: '20px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>🚀</span> Tezkor Mock Test & Vision AI Konvertor
            </h2>
            <p className="muted small" style={{ margin: '4px 0 0' }}>
              Qog‘ozdagi yoki PDF test kalitlarini kiritishingiz yoki fotosurat/PDF yuklab AI orqali 1-soniyada test yasashingiz mumkin!
            </p>
          </div>
          <Link
            to="/teacher/ai-converter"
            className="btn primary sm"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 700 }}
          >
            <span>✨</span> Qog'oz/PDF dan AI Konvertor
          </Link>
        </div>

        <form onSubmit={createQuickMock} style={{ marginTop: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(240px, 100%), 1fr))', gap: 12 }}>
            <label className="small">
              Mock Test Nomi (ixtiyoriy):
              <input
                value={mockTitle}
                onChange={(e) => setMockTitle(e.target.value)}
                placeholder="Milliy Sertifikat Mock Test #1"
              />
            </label>
            <label className="small">
              Vaqt chegarasi (daqiqa):
              <input
                type="number"
                min="5"
                max="300"
                value={mockTime}
                onChange={(e) => setMockTime(Number(e.target.value))}
              />
            </label>
          </div>

          <label className="small" style={{ marginTop: 10, display: 'block' }}>
            To‘g‘ri javoblar kaliti:
            <textarea
              rows={2}
              value={mockKeys}
              onChange={(e) => setMockKeys(e.target.value)}
              placeholder="Masalan: 1a2b3c4d5a...40b yoki 1:A, 2:B, 3:C... yoki ABCDABCD..."
              required
              style={{ fontFamily: 'monospace', fontSize: '0.9rem', marginTop: 4 }}
            />
          </label>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
            <button className="btn primary sm" disabled={mockBusy}>
              {mockBusy ? 'Yaratilmoqda…' : '⚡ 1-soniyada Mock Test Yaratish'}
            </button>
            {mockErr && <span className="error small">{mockErr}</span>}
          </div>
        </form>

        {/* Mock Created Success Banner */}
        {mockCreated && (
          <div
            style={{
              marginTop: 16,
              background: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              borderRadius: '10px',
              padding: '14px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div>
                <strong style={{ color: '#10b981', display: 'block', fontSize: '1rem' }}>
                  🎉 Mock Test Muvaffaqiyatli Yaratildi!
                </strong>
                <p style={{ margin: '4px 0 0', fontSize: '0.88rem' }}>
                  {mockCreated.title} · {mockCreated.questions_count} ta savol · {mockCreated.time_limit} daqiqa
                </p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span
                  style={{
                    padding: '4px 12px',
                    borderRadius: '6px',
                    background: 'rgba(16, 185, 129, 0.2)',
                    color: '#10b981',
                    fontWeight: 800,
                    fontSize: '1.05rem',
                    letterSpacing: '0.5px',
                  }}
                >
                  {mockCreated.mock_code}
                </span>
                <button
                  type="button"
                  className="btn sm"
                  onClick={() => copyMockCode(mockCreated.mock_code)}
                >
                  {copiedMock ? '✓ Nusxalandi' : '📋 Kodni nusxalash'}
                </button>
                <button
                  type="button"
                  className="btn sm"
                  style={{
                    background: 'rgba(245, 158, 11, 0.15)',
                    border: '1px solid rgba(245, 158, 11, 0.4)',
                    color: '#F59E0B',
                    fontWeight: 800,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                  }}
                  onClick={() => openClassroomModal(mockCreated)}
                >
                  <QrCode size={14} />
                  <span>📱 Katta QR-Kod</span>
                </button>
                <button
                  type="button"
                  className="btn sm ghost"
                  onClick={() => viewMockLeaderboard(mockCreated.test_id)}
                >
                  🏆 Reytingni ko‘rish
                </button>
              </div>
            </div>
            <p className="muted small" style={{ margin: '8px 0 0' }}>
              💡 O‘quvchilaringiz ushbu kodni saytda yoki Telegram botda (@grandec_bot) kiritib, 1 bosishda testni boshlashlari mumkin!
            </p>
          </div>
        )}

        {/* Mock Leaderboard Modal/Panel */}
        {activeMockId && (
          <div style={{ marginTop: 18, borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <h3 style={{ margin: 0 }}>
                🏆 Guruh Mock Reytingi & BMB Darajalari
              </h3>
              <button
                type="button"
                className="btn sm ghost"
                onClick={() => {
                  setActiveMockId(null);
                  setLeaderboardData(null);
                }}
              >
                ✕ Yopish
              </button>
            </div>

            {leaderboardLoading && <p className="muted small">Reyting hisoblanmoqda…</p>}
            {leaderboardErr && <p className="error small">{leaderboardErr}</p>}
            {leaderboardData && (
              <div>
                <p className="muted small" style={{ marginBottom: 10 }}>
                  <strong>{leaderboardData.title}</strong> ({leaderboardData.mock_code}) · Jami qatnashchilar: {leaderboardData.total_participants} ta
                </p>

                {/* BMB Grade summary pill strip */}
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
                  {Object.entries(leaderboardData.bmb_summary).map(([gr, count]) => (
                    <span
                      key={gr}
                      style={{
                        padding: '3px 8px',
                        borderRadius: '4px',
                        fontSize: '0.8rem',
                        fontWeight: 700,
                        background: gr.startsWith('A') ? 'rgba(16, 185, 129, 0.15)' : gr.startsWith('B') ? 'rgba(59, 130, 246, 0.15)' : gr.startsWith('C') ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                        color: gr.startsWith('A') ? '#10b981' : gr.startsWith('B') ? '#3b82f6' : gr.startsWith('C') ? '#f59e0b' : '#ef4444',
                      }}
                    >
                      {gr}: {count} ta
                    </span>
                  ))}
                </div>

                {leaderboardData.leaderboard.length === 0 ? (
                  <p className="muted small">Hozircha hech kim ushbu mock testni yakunlamadi.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="data" style={{ fontSize: '0.84rem' }}>
                      <thead>
                        <tr>
                          <th>O‘rin</th>
                          <th>O‘quvchi</th>
                          <th>Ball</th>
                          <th>Foiz</th>
                          <th>BMB Daraja</th>
                          <th>Vaqt</th>
                        </tr>
                      </thead>
                      <tbody>
                        {leaderboardData.leaderboard.map((item) => (
                          <tr key={item.rank}>
                            <td><strong>#{item.rank}</strong></td>
                            <td>{item.student_name}</td>
                            <td>{item.score} / {item.max_score}</td>
                            <td><strong>{item.percentage}%</strong></td>
                            <td>
                              <span className={`badge ${item.bmb_grade.startsWith('A') ? 'green' : item.bmb_grade.startsWith('B') ? 'blue' : 'rose'}`}>
                                {item.bmb_grade} ({item.bmb_title})
                              </span>
                            </td>
                            <td className="muted small">{item.date ? new Date(item.date).toLocaleDateString() : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Analytics quick link — mirrors the legacy detailed-analytics banner. */}
      <Link to="/analytics" className="card" style={{ display: 'block', marginTop: 16 }}>
        <strong><UsersIcon size={14} className="ico" /> {t('detailed_analytics')}</strong>
        <p className="muted small">{t('detailed_analytics_hint')}</p>
      </Link>

      {/* Recent activity (last 14 days) from /analytics/. */}
      {activity && activity.labels.length > 0 && (
        <>
          <h2>{t('td_activity')}</h2>
          <div className="card">
            <AnalyticsChart
              data={activity.labels.map((label, i) => ({
                date: label,
                attempts: activity.attempts[i] ?? 0,
                avg: activity.avg_percentage[i] ?? 0,
              }))}
            />
          </div>
        </>
      )}

      {weeklyReports.length > 0 && (
        <section className="card" aria-label="Weekly reports">
          <h2>📊 {t('weekly_group_reports_title')}</h2>
          {weeklyReports.map((report) => <article key={report.id}>
            <h3>{report.group_name} · {report.period_label} · v{report.version}</h3>
            <p className="muted small">{report.text.replace(/\*/g, '')}</p>
          </article>)}
        </section>
      )}

      {/* Attendance workspace — group roster, 4-way marking, finalization. */}
      <div id="attendance-workspace" style={{ scrollMarginTop: 24, marginBottom: 28 }}>
        <h2>{t('attendance_title')}</h2>
        <AttendancePanel />
      </div>

      {/* Groups Command Center — parity with group_list.html cards with 3 quick teacher action buttons */}
      <div id="groups-workspace" style={{ scrollMarginTop: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '24px 0 14px', flexWrap: 'wrap', gap: 10 }}>
        <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <UsersIcon size={20} className="ico" />
          <span>{t('groups')} ({groups.length})</span>
        </h2>
        <Link
          to="/smart-test-create"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 16px',
            borderRadius: 10,
            background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
            color: '#0F172A',
            fontWeight: 800,
            fontSize: 13,
            textDecoration: 'none',
            boxShadow: '0 4px 12px rgba(245, 158, 11, 0.25)',
          }}
        >
          <PlusCircle size={15} />
          <span>+ Yangi Test Yaratish</span>
        </Link>
      </div>

      {groups.length === 0 ? (
        <div className="card" style={{ padding: 24, textAlign: 'center' }}>
          <p className="muted">{t('td_no_groups_hint')}</p>
          <Link className="btn primary sm" to="/groups">
            {t('gf_new_short')}
          </Link>
        </div>
      ) : (
        <div className="grid">
          {groups.map((g) => {
            const memberCount = g.student_count ?? (g.students ?? []).length;
            const tgShareText = `📢 Hurmatli "${g.name}" guruhi o'quvchilari! Yangi topshiriq va testlar yuklandi. O'z natijangizni tekshirish uchun guruh sahifasiga kiring:`;
            const tgShareUrl = `https://t.me/share/url?url=${encodeURIComponent(`https://grandec.uz/groups/${g.id}`)}&text=${encodeURIComponent(tgShareText)}`;

            return (
              <div
                key={g.id}
                className="card"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: 14,
                  borderRadius: 16,
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                  boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
                  padding: 20,
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
                    <strong style={{ fontSize: 16, color: 'var(--ink)' }}>{g.name}</strong>
                    <span
                      style={{
                        padding: '3px 8px',
                        borderRadius: 6,
                        background: 'rgba(59, 130, 246, 0.15)',
                        color: '#3B82F6',
                        fontSize: 11,
                        fontWeight: 700,
                      }}
                    >
                      {memberCount} {t('an_talaba_full')}
                    </span>
                  </div>

                  {g.description ? <p className="muted small" style={{ margin: '0 0 10px' }}>{g.description}</p> : null}

                  {/* Student preview */}
                  {(g.students ?? []).length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                      {(g.students ?? []).slice(0, 4).map((s) => (
                        <span
                          key={s.id}
                          style={{
                            fontSize: 11,
                            padding: '2px 8px',
                            borderRadius: 6,
                            background: 'rgba(255, 255, 255, 0.06)',
                            color: 'var(--ink-soft)',
                            border: '1px solid var(--border)',
                          }}
                        >
                          {s.full_name.split(' ')[0]}
                        </span>
                      ))}
                      {(g.students ?? []).length > 4 && (
                        <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                          +{(g.students ?? []).length - 4} yana
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* 3 Essential Teacher Quick Actions */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 8,
                    paddingTop: 10,
                    borderTop: '1px solid var(--border)',
                  }}
                >
                  {/* 1. Vazifa Yuklash */}
                  <Link
                    to={`/smart-test-create?groupId=${g.id}`}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6,
                      padding: '8px 10px',
                      borderRadius: 10,
                      background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(217, 119, 6, 0.15) 100%)',
                      border: '1px solid rgba(245, 158, 11, 0.4)',
                      color: '#F59E0B',
                      fontSize: 12,
                      fontWeight: 800,
                      textDecoration: 'none',
                    }}
                    title="Ushbu guruhga yangi test yoki vazifa biriktirish"
                  >
                    <span>📢 Vazifa yuklash</span>
                  </Link>

                  {/* 2. Natijalar / Vedomost */}
                  <Link
                    to={`/groups/${g.id}`}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6,
                      padding: '8px 10px',
                      borderRadius: 10,
                      background: 'rgba(16, 185, 129, 0.12)',
                      border: '1px solid rgba(16, 185, 129, 0.35)',
                      color: '#10B981',
                      fontSize: 12,
                      fontWeight: 800,
                      textDecoration: 'none',
                    }}
                    title="Guruh jonli reytingi va o'quvchilar natijalarini ko'rish"
                  >
                    <span>📊 Vedomost</span>
                  </Link>

                  {/* 3. Katta QR-Kod */}
                  <button
                    type="button"
                    onClick={() => {
                      const webUrl = `${window.location.origin}/groups/${g.id}`;
                      const tmaUrl = `https://t.me/grandec_bot/app?startapp=group_${g.id}`;
                      setQrModalData({
                        isOpen: true,
                        title: g.name,
                        code: g.invite_code || g.group_code || `GRP-${g.id}`,
                        webUrl,
                        tmaUrl,
                        subtitle: `"${g.name}" guruhi dars xonasiga qo'shilish va vazifalarni ochish uchun QR-kod`,
                      });
                    }}
                    style={{
                      gridColumn: '1 / -1',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6,
                      padding: '8px 12px',
                      borderRadius: 10,
                      background: 'rgba(99, 102, 241, 0.12)',
                      border: '1px solid rgba(99, 102, 241, 0.35)',
                      color: '#818cf8',
                      fontSize: 12,
                      fontWeight: 800,
                      cursor: 'pointer',
                    }}
                    title="Sinfxonada proyektor yoki telefonda ko'rsatish"
                  >
                    <QrCode size={14} />
                    <span>📱 Sinfxona QR-Kodi</span>
                  </button>

                  {/* 4. Telegram Guruhga Xabar (Full width) */}
                  <a
                    href={tgShareUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      gridColumn: '1 / -1',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6,
                      padding: '8px 12px',
                      borderRadius: 10,
                      background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
                      color: '#FFFFFF',
                      fontSize: 12,
                      fontWeight: 800,
                      textDecoration: 'none',
                      boxShadow: '0 2px 8px rgba(2, 132, 199, 0.25)',
                    }}
                  >
                    <Send size={13} />
                    <span>✈️ Telegram guruhga xabar yuborish</span>
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      )}
      </div>

      {/* Full students list across groups (Vedomost & Results) */}
      <div id="results-workspace" style={{ scrollMarginTop: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 32, marginBottom: 12, flexWrap: 'wrap', gap: 10 }}>
        <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>📊</span>
          <span>{t('td_students_list')} — Guruhlar Vedomosti ({students.length})</span>
        </h2>
        <button
          type="button"
          onClick={exportVedomostCsv}
          className="btn primary sm"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontWeight: 800,
            background: 'linear-gradient(135deg, #0ea5e9, #0284c7)',
            borderColor: '#0284c7',
            padding: '8px 16px',
            borderRadius: 10,
            cursor: 'pointer',
          }}
          title="Barcha o'quvchilar ballari va guruhlarini CSV/Excel faylga yuklash"
        >
          <Download size={15} />
          <span>📥 CSV / Excel Yuklab Olish (Export Vedomost)</span>
        </button>
      </div>
      {students.length === 0 ? (
        <p className="muted">{t('gf_no_students')}</p>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>{t('th_student')}</th>
                <th>{t('th_email')}</th>
                <th>Tarif</th>
                <th>Testlar</th>
                <th>Esselar</th>
                <th>{t('groups')}</th>
              </tr>
            </thead>
            <tbody>
              {students.map((s) => (
                <tr key={s.id}>
                  <td><strong>{s.full_name}</strong></td>
                  <td>{s.email}</td>
                  <td>
                    <span className="badge green" style={{ fontWeight: 600 }}>
                      {s.pro_status_label ?? '⭐ PRO (Faol)'}
                    </span>
                  </td>
                  <td>{s.tests_count ?? 0} ta</td>
                  <td>{s.essays_count ?? 0} ta</td>
                  <td>
                    {groups
                      .filter((g) => (g.students ?? []).some((m) => m.id === s.id))
                      .map((g) => g.name)
                      .join(', ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Submissions — recent_results from /teacher/. */}
      <h2>{t('recent_student_results')}</h2>
      <p className="muted small">{t('latest_submissions_hint')}</p>
      {recent.length === 0 ? (
        <p className="muted">{t('no_student_results_hint')}</p>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>{t('th_student')}</th>
                <th>{t('th_test_name')}</th>
                <th>{t('score')}</th>
                <th>{t('status')}</th>
                <th>{t('date')}</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r) => (
                <tr key={`${r.student}-${r.test}-${r.date}`}>
                  <td>{r.student}</td>
                  <td>{r.test}</td>
                  <td>{r.percentage}%</td>
                  <td>
                    <span className={`badge ${r.is_passed ? 'green' : 'rose'}`}>
                      {r.is_passed ? t('status_passed') : t('status_failed')}
                    </span>
                  </td>
                  <td className="muted small">{r.date ? r.date.slice(0, 16).replace('T', ' ') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Essay queue links — essay UI lives in other streams; link out. */}      <h2>{t('teacher_queue')}</h2>
      <div className="grid">
        <div className="card">
          <strong>{t('essay_topics')}</strong>
          <p className="muted small">{t('td_queue_hint')}</p>
          <Link className="btn primary sm" to="/teacher/essays">
            {t('td_open_queue')} →
          </Link>
        </div>
        <div className="card">
          <strong>{t('lb_essay_title')}</strong>
          <p className="muted small">
            {board ? `${board.total_essays} ${t('lb_total_essays')} · ${board.total_students} ${t('lb_graded_students')}` : t('loading')}
          </p>
          <Link className="btn sm" to="/essay-leaderboard">
            {t('view_all')} →
          </Link>
        </div>
      </div>
      {board && board.podium.length > 0 && (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>{t('lb_rank')}</th>
                <th>{t('lb_student')}</th>
                <th>{t('lb_best_score')}</th>
                <th>{t('lb_essays_col')}</th>
              </tr>
            </thead>
            <tbody>
              {board.podium.map((e) => (
                <tr key={e.student_id}>
                  <td>{e.rank}</td>
                  <td>{e.name}</td>
                  <td>
                    {e.best_score} <span className="muted small">({e.converted_score} / 75)</span>
                  </td>
                  <td>{e.essay_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Classroom Projector QR Modal */}
      {qrModalData && (
        <ClassroomQrModal
          isOpen={qrModalData.isOpen}
          onClose={() => setQrModalData(null)}
          title={qrModalData.title}
          code={qrModalData.code}
          webUrl={qrModalData.webUrl}
          tmaUrl={qrModalData.tmaUrl}
          subtitle={qrModalData.subtitle}
        />
      )}
      </div>

      {/* 📝 Teacher Homework 3-Step Wizard (Stage 4) */}
      <TeacherHomeworkWizard
        isOpen={hwModalOpen}
        onClose={() => setHwModalOpen(false)}
        onSuccess={() => {
          refreshOverview();
        }}
        groups={groups}
        initialGroupId={hwGroupId}
      />
    </div>
  );
}
