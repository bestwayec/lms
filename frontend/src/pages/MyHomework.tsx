import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLang } from '../i18n/LangContext';
import {
  HomeworkAPI,
  type StudentHomeworkItem,
} from '../lib/school';
import {
  BookOpen,
  Calendar,
  CheckCircle,
  Clock,
  FileText,
  Play,
  RotateCcw,
  Sparkles,
  User,
  Users,
  X,
} from 'lucide-react';

export default function MyHomework() {
  const { t } = useLang();
  const navigate = useNavigate();

  const [homeworks, setHomeworks] = useState<StudentHomeworkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending' | 'completed' | 'overdue'>('all');

  // Modal / Detail State
  const [activeHw, setActiveHw] = useState<StudentHomeworkItem | null>(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [resultModalOpen, setResultModalOpen] = useState(false);
  const [resultData, setResultData] = useState<{
    score: number | null;
    max_score: number | null;
    percentage: number | null;
    score_display: string;
    feedback: string;
    status_label: string;
    completed_at: string;
  } | null>(null);
  const [submittingAction, setSubmittingAction] = useState(false);

  // Custom task answer state
  const [customAnswer, setCustomAnswer] = useState('');
  const [savingProgress, setSavingProgress] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const fetchHomeworks = async (filter: string = statusFilter) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await HomeworkAPI.getStudentHomeworks(filter === 'all' ? undefined : filter);
      setHomeworks(resp.results || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg || t('hw_fetch_error'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHomeworks(statusFilter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const handleStartOrResume = async (hw: StudentHomeworkItem) => {
    setSubmittingAction(true);
    try {
      const startRes = await HomeworkAPI.startStudentHomework(hw.id);
      if (hw.content_type === 'test' && hw.action_id) {
        // Navigate to official test runner
        navigate(`/tests/${hw.action_id}${startRes.attempt_id ? `?attempt=${startRes.attempt_id}` : ''}`);
      } else if (hw.content_type === 'essay' && hw.action_id) {
        // Navigate to essay writer
        navigate(`/essays/${hw.action_id}/write`);
      } else if (hw.content_type === 'vocabulary' && hw.action_id) {
        navigate(`/vocabulary/packs/${hw.action_id}`);
      } else {
        // Custom or lesson task - open internal interactive modal
        setActiveHw(hw);
        setCustomAnswer(hw.score_display || '');
        setDetailModalOpen(true);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(msg || t('hw_start_error'));
    } finally {
      setSubmittingAction(false);
    }
  };

  const handleRetryGrading = async (hw: StudentHomeworkItem) => {
    setSubmittingAction(true);
    try {
      await HomeworkAPI.submitStudentHomework(hw.id, {});
      await fetchHomeworks(statusFilter);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(msg || t('hw_result_error'));
    } finally {
      setSubmittingAction(false);
    }
  };

  const handleViewResult = async (hw: StudentHomeworkItem) => {
    setSubmittingAction(true);
    try {
      const res = await HomeworkAPI.getStudentHomeworkResult(hw.id);
      setResultData({
        score: res.score,
        max_score: res.max_score,
        percentage: res.percentage,
        score_display: res.score_display,
        feedback: res.feedback,
        status_label: res.status_label,
        completed_at: res.completed_at,
      });
      setActiveHw(hw);
      setResultModalOpen(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(msg || t('hw_result_error'));
    } finally {
      setSubmittingAction(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!activeHw) return;
    setSavingProgress(true);
    setSaveSuccess(false);
    try {
      await HomeworkAPI.saveStudentHomework(activeHw.id, { text: customAnswer });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(msg || 'Saqlashda xatolik yuz berdi.');
    } finally {
      setSavingProgress(false);
    }
  };

  const handleSubmitCustom = async () => {
    if (!activeHw) return;
    if (!customAnswer.trim()) {
      alert('Iltimos, javobingizni kiriting.');
      return;
    }
    setSubmittingAction(true);
    try {
      await HomeworkAPI.submitStudentHomework(activeHw.id, { text: customAnswer });
      setDetailModalOpen(false);
      fetchHomeworks();
      alert('Vazifangiz muvaffaqiyatli topshirildi!');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(msg || 'Topshirishda xatolik yuz berdi.');
    } finally {
      setSubmittingAction(false);
    }
  };

  // Metrics
  const totalCount = homeworks.length;
  const pendingCount = homeworks.filter(
    (h) => h.status === 'not_started' || h.status === 'in_progress'
  ).length;
  const completedCount = homeworks.filter(
    (h) => h.status === 'submitted' || h.status === 'awaiting_review' || h.status === 'graded'
  ).length;
  const overdueCount = homeworks.filter((h) => h.status === 'overdue').length;

  const getStatusBadge = (status: string, serverLabel: string, scoreDisplay?: string) => {
    const statusLabel = t(`hw_status_${status}`, serverLabel);
    switch (status) {
      case 'grading_failed':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '3px 10px',
              borderRadius: 20,
              fontSize: 12,
              fontWeight: 700,
              background: 'var(--warning-bg, #FEF3C7)',
              color: 'var(--warning-text, #92400E)',
            }}
          >
            <Clock size={13} />
            {statusLabel}
          </span>
        );
      case 'graded':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '3px 10px',
              borderRadius: 20,
              fontSize: 12,
              fontWeight: 800,
              background: '#D1FAE5',
              color: '#065F46',
            }}
          >
            <CheckCircle size={13} />
            {scoreDisplay ? `${statusLabel} (${scoreDisplay})` : statusLabel}
          </span>
        );
      case 'awaiting_review':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '3px 10px',
              borderRadius: 20,
              fontSize: 12,
              fontWeight: 700,
              background: '#EDE9FE',
              color: '#5B21B6',
            }}
          >
            <Clock size={13} />
            {statusLabel}
          </span>
        );
      case 'submitted':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '3px 10px',
              borderRadius: 20,
              fontSize: 12,
              fontWeight: 700,
              background: '#E0E7FF',
              color: '#3730A3',
            }}
          >
            <CheckCircle size={13} />
            {statusLabel}
          </span>
        );
      case 'in_progress':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '3px 10px',
              borderRadius: 20,
              fontSize: 12,
              fontWeight: 700,
              background: '#DBEAFE',
              color: '#1E40AF',
            }}
          >
            <Play size={13} />
            {statusLabel}
          </span>
        );
      case 'overdue':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '3px 10px',
              borderRadius: 20,
              fontSize: 12,
              fontWeight: 700,
              background: '#FEE2E2',
              color: '#991B1B',
            }}
          >
            <Clock size={13} />
            {statusLabel}
          </span>
        );
      case 'cancelled':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '3px 10px',
              borderRadius: 20,
              fontSize: 12,
              fontWeight: 600,
              background: '#F3F4F6',
              color: '#4B5563',
            }}
          >
            {statusLabel}
          </span>
        );
      default:
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '3px 10px',
              borderRadius: 20,
              fontSize: 12,
              fontWeight: 600,
              background: '#F3F4F6',
              color: '#4B5563',
            }}
          >
            <Play size={13} />
            {statusLabel}
          </span>
        );
    }
  };

  const getContentTypeBadge = (type: string) => {
    let label = 'Maxsus topshiriq';
    let bg = '#F3F4F6';
    let color = '#374151';

    if (type === 'test') {
      label = 'Test';
      bg = '#E0F2FE';
      color = '#0369A1';
    } else if (type === 'essay') {
      label = 'Esse';
      bg = '#FCE7F3';
      color = '#BE185D';
    } else if (type === 'vocabulary') {
      label = "Lug'at";
      bg = '#FEF3C7';
      color = '#B45309';
    } else if (type === 'lesson') {
      label = 'Dars vazifasi';
      bg = '#EDE9FE';
      color = '#6D28D9';
    }

    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          padding: '2px 8px',
          borderRadius: 6,
          fontSize: 11,
          fontWeight: 700,
          background: bg,
          color: color,
        }}
      >
        <BookOpen size={11} />
        {label}
      </span>
    );
  };

  return (
    <div className="container" style={{ maxWidth: 1040, margin: '0 auto', padding: '24px 16px' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '1.85rem',
              fontWeight: 900,
              margin: '0 0 6px 0',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <FileText size={28} color="#4F46E5" />
            <span>{t('my_homework_title') || 'Mening vazifalarim'}</span>
          </h1>
          <p style={{ margin: 0, color: 'var(--text-secondary, #6B7280)', fontSize: 14 }}>
            {t('my_homework_subtitle') || "O'qituvchingiz biriktirgan barcha uy vazifalari va topshiriqlar"}
          </p>
        </div>

        <button
          type="button"
          onClick={() => fetchHomeworks()}
          disabled={loading}
          className="btn sm"
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <RotateCcw size={14} className={loading ? 'spin' : ''} />
          <span>{t('refresh', 'Yangilash')}</span>
        </button>
      </div>

      {/* Metrics Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 12,
          marginBottom: 24,
        }}
      >
        <div
          style={{
            background: 'var(--card-bg, #fff)',
            border: '1px solid var(--border-color, #E5E7EB)',
            borderRadius: 12,
            padding: 14,
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ fontSize: 12, color: '#6B7280', fontWeight: 600 }}>{t('hw_stat_all') || 'Jami topshiriqlar'}</div>
          <div style={{ fontSize: 24, fontWeight: 900, marginTop: 4 }}>{totalCount}</div>
        </div>

        <div
          style={{
            background: 'var(--card-bg, #fff)',
            border: '1px solid var(--border-color, #E5E7EB)',
            borderRadius: 12,
            padding: 14,
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ fontSize: 12, color: '#1E40AF', fontWeight: 600 }}>{t('hw_stat_pending') || 'Bajarilmagan'}</div>
          <div style={{ fontSize: 24, fontWeight: 900, color: '#2563EB', marginTop: 4 }}>{pendingCount}</div>
        </div>

        <div
          style={{
            background: 'var(--card-bg, #fff)',
            border: '1px solid var(--border-color, #E5E7EB)',
            borderRadius: 12,
            padding: 14,
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ fontSize: 12, color: '#065F46', fontWeight: 600 }}>{t('hw_stat_completed') || 'Yakunlangan'}</div>
          <div style={{ fontSize: 24, fontWeight: 900, color: '#059669', marginTop: 4 }}>{completedCount}</div>
        </div>

        <div
          style={{
            background: 'var(--card-bg, #fff)',
            border: '1px solid var(--border-color, #E5E7EB)',
            borderRadius: 12,
            padding: 14,
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ fontSize: 12, color: '#991B1B', fontWeight: 600 }}>{t('hw_stat_overdue') || "Muddati o'tgan"}</div>
          <div style={{ fontSize: 24, fontWeight: 900, color: '#DC2626', marginTop: 4 }}>{overdueCount}</div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          marginBottom: 20,
          borderBottom: '1px solid var(--border-color, #E5E7EB)',
          paddingBottom: 8,
          overflowX: 'auto',
        }}
      >
        {(
          [
            { id: 'all', label: t('hw_filter_all') || 'Barchasi' },
            { id: 'pending', label: t('hw_filter_pending') || 'Kutilayotgan' },
            { id: 'completed', label: t('hw_filter_completed') || 'Yakunlangan' },
            { id: 'overdue', label: t('hw_filter_overdue') || "Muddati o'tgan" },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setStatusFilter(tab.id)}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: statusFilter === tab.id ? 'var(--primary, #4F46E5)' : 'transparent',
              color: statusFilter === tab.id ? '#fff' : 'var(--text-secondary, #6B7280)',
              fontWeight: 700,
              fontSize: 13,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Error state */}
      {error && (
        <div
          style={{
            padding: 14,
            borderRadius: 8,
            background: '#FEE2E2',
            color: '#B91C1C',
            marginBottom: 20,
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          {error}
        </div>
      )}

      {/* Loading state */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#6B7280' }}>
          <div className="spin" style={{ width: 28, height: 28, margin: '0 auto 12px' }}>
            <RotateCcw size={28} />
          </div>
          <p>{t('loading') || 'Yuklanmoqda...'}</p>
        </div>
      ) : homeworks.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '60px 20px',
            background: 'var(--card-bg, #fff)',
            borderRadius: 14,
            border: '1px dashed var(--border-color, #E5E7EB)',
          }}
        >
          <BookOpen size={48} color="#9CA3AF" style={{ margin: '0 auto 12px' }} />
          <h3 style={{ margin: '0 0 6px 0', fontSize: 16, fontWeight: 700 }}>
            {t('no_homeworks_found') || 'Hozircha hech qanday vazifa biriktirilmagan.'}
          </h3>
          <p style={{ margin: 0, fontSize: 13, color: '#6B7280' }}>
            {t('no_homeworks_desc') || "O'qituvchingiz yangi topshiriq berganida bu yerda paydo bo'ladi."}
          </p>
        </div>
      ) : (
        /* Homework Cards Grid */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {homeworks.map((hw) => {
            const isCompleted =
              hw.status === 'graded' || hw.status === 'awaiting_review' || hw.status === 'submitted';
            const isCancelled = hw.status === 'cancelled';
            const dueDateObj = new Date(hw.due_date);

            return (
              <div
                key={hw.id}
                style={{
                  background: 'var(--card-bg, #fff)',
                  border: '1px solid var(--border-color, #E5E7EB)',
                  borderRadius: 14,
                  padding: 18,
                  boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: 16,
                  transition: 'border-color 0.2s',
                }}
              >
                {/* Left: Info */}
                <div style={{ flex: '1 1 340px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                    {getContentTypeBadge(hw.content_type)}
                    {getStatusBadge(hw.status, hw.status_label, hw.score_display)}
                  </div>

                  <h3 style={{ margin: '0 0 6px 0', fontSize: '1.15rem', fontWeight: 800 }}>{hw.title}</h3>

                  {hw.description && (
                    <p
                      style={{
                        margin: '0 0 10px 0',
                        fontSize: 13,
                        color: 'var(--text-secondary, #4B5563)',
                        lineHeight: 1.4,
                      }}
                    >
                      {hw.description}
                    </p>
                  )}

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 16,
                      fontSize: 12,
                      color: 'var(--text-secondary, #6B7280)',
                      flexWrap: 'wrap',
                    }}
                  >
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <Users size={13} />
                      {hw.group_name}
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <User size={13} />
                      {hw.teacher_name}
                    </span>
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 4,
                        color: hw.status === 'overdue' ? '#DC2626' : 'inherit',
                        fontWeight: hw.status === 'overdue' ? 700 : 'normal',
                      }}
                    >
                      <Calendar size={13} />
                      {dueDateObj.toLocaleDateString()} {dueDateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    {hw.time_limit > 0 && (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <Clock size={13} />
                        {hw.time_limit} {t('minutes', 'daqiqa')}
                      </span>
                    )}
                  </div>
                </div>

                {/* Right: Actions */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  {hw.status === 'grading_failed' ? (
                    <button
                      type="button"
                      onClick={() => handleRetryGrading(hw)}
                      disabled={submittingAction}
                      className="btn sm secondary"
                      style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, minHeight: 44 }}
                    >
                      <Clock size={14} />
                      <span>{t('hw_retry_grading', 'Natijani qayta tekshirish')}</span>
                    </button>
                  ) : isCancelled ? (
                    <span style={{ fontSize: 13, color: '#9CA3AF', fontStyle: 'italic' }}>
                      {t('hw_cancelled') || 'Bekor qilingan'}
                    </span>
                  ) : isCompleted ? (
                    <button
                      type="button"
                      onClick={() => handleViewResult(hw)}
                      disabled={submittingAction}
                      className="btn sm secondary"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        fontWeight: 700,
                      }}
                    >
                      <Sparkles size={14} color="#059669" />
                      <span>{t('hw_view_result') || "Natijani ko'rish"}</span>
                    </button>
                  ) : hw.can_start === false ? (
                    <span style={{ fontSize: 13, color: 'var(--text-secondary, #6B7280)', fontStyle: 'italic' }}>
                      {hw.status === 'overdue'
                        ? t('hw_deadline_passed', 'Muddati tugagan')
                        : t('hw_not_available', 'Hozircha mavjud emas')}
                    </span>
                  ) : hw.status === 'in_progress' ? (
                    <button
                      type="button"
                      onClick={() => handleStartOrResume(hw)}
                      disabled={submittingAction}
                      className="btn sm primary"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        fontWeight: 700,
                        background: '#2563EB',
                      }}
                    >
                      <Play size={14} />
                      <span>{t('hw_resume') || 'Davom ettirish'}</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleStartOrResume(hw)}
                      disabled={submittingAction}
                      className="btn sm primary"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        fontWeight: 700,
                      }}
                    >
                      <Play size={14} />
                      <span>{t('hw_start') || 'Boshlash'}</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Result Modal */}
      {resultModalOpen && resultData && activeHw && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 16,
          }}
        >
          <div
            style={{
              background: 'var(--card-bg, #fff)',
              borderRadius: 16,
              maxWidth: 480,
              width: '100%',
              padding: 24,
              boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 800 }}>
                {t('hw_result_title') || 'Topshiriq natijasi'}
              </h3>
              <button
                type="button"
                onClick={() => setResultModalOpen(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            <p style={{ margin: '0 0 16px 0', fontSize: 14, color: '#4B5563' }}>{activeHw.title}</p>

            <div
              style={{
                background: '#F0FDF4',
                border: '1px solid #BBF7D0',
                borderRadius: 12,
                padding: 16,
                textAlign: 'center',
                marginBottom: 16,
              }}
            >
              <div style={{ fontSize: 13, color: '#166534', fontWeight: 700, marginBottom: 4 }}>
                {activeHw ? t(`hw_status_${activeHw.status}`, resultData.status_label) : resultData.status_label}
              </div>
              <div style={{ fontSize: 32, fontWeight: 900, color: '#15803D' }}>
                {resultData.score_display || `${resultData.percentage ?? resultData.score ?? 0}%`}
              </div>
              {resultData.percentage !== null && resultData.score_display !== `${resultData.percentage}%` && (
                <div style={{ fontSize: 13, color: '#166534', marginTop: 4 }}>
                  Natija: {resultData.percentage}%
                </div>
              )}
            </div>

            {resultData.feedback && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#4B5563', marginBottom: 4 }}>
                  {t('hw_teacher_feedback') || "O'qituvchi izohi:"}
                </div>
                <div
                  style={{
                    background: '#F9FAFB',
                    border: '1px solid #E5E7EB',
                    borderRadius: 8,
                    padding: 12,
                    fontSize: 13,
                    color: '#374151',
                    lineHeight: 1.5,
                  }}
                >
                  {resultData.feedback}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
              <button
                type="button"
                onClick={() => setResultModalOpen(false)}
                className="btn primary sm"
                style={{ minWidth: 90 }}
              >
                {t('close') || 'Yopish'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Custom Assignment Modal */}
      {detailModalOpen && activeHw && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 16,
          }}
        >
          <div
            style={{
              background: 'var(--card-bg, #fff)',
              borderRadius: 16,
              maxWidth: 580,
              width: '100%',
              padding: 24,
              boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 800 }}>{activeHw.title}</h3>
              <button
                type="button"
                onClick={() => setDetailModalOpen(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            {activeHw.description && (
              <div
                style={{
                  background: '#F9FAFB',
                  border: '1px solid #E5E7EB',
                  borderRadius: 8,
                  padding: 12,
                  fontSize: 14,
                  color: '#374151',
                  marginBottom: 16,
                  lineHeight: 1.5,
                }}
              >
                {activeHw.description}
              </div>
            )}

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                {t('hw_your_answer') || 'Javobingiz:'}
              </label>
              <textarea
                rows={6}
                value={customAnswer}
                onChange={(e) => setCustomAnswer(e.target.value)}
                placeholder={t('hw_answer_placeholder') || 'Javob matnini bu yerga yozing...'}
                style={{
                  width: '100%',
                  padding: 10,
                  borderRadius: 8,
                  border: '1px solid #D1D5DB',
                  fontFamily: 'inherit',
                  fontSize: 14,
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {saveSuccess && (
              <div style={{ color: '#059669', fontSize: 12, fontWeight: 700, marginBottom: 10 }}>
                ✓ {t('hw_draft_saved') || 'Qoralama saqlandi!'}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <button
                type="button"
                onClick={handleSaveDraft}
                disabled={savingProgress || submittingAction}
                className="btn sm"
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <Clock size={13} />
                <span>{savingProgress ? 'Saqlanmoqda...' : t('hw_save_draft') || 'Qoralamani saqlash'}</span>
              </button>

              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  onClick={() => setDetailModalOpen(false)}
                  className="btn sm"
                >
                  {t('cancel') || 'Bekor qilish'}
                </button>
                <button
                  type="button"
                  onClick={handleSubmitCustom}
                  disabled={submittingAction || !customAnswer.trim()}
                  className="btn sm primary"
                  style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700 }}
                >
                  <CheckCircle size={14} />
                  <span>{submittingAction ? 'Yuborilmoqda...' : t('hw_submit_now') || 'Topshirish'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
