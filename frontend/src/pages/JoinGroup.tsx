import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowRight,
  BookOpen,
  LogIn,
  Users,
  X,
  Search,
  GraduationCap,
  Sparkles,
  CheckCircle2,
} from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useToast } from '../context/ToastContext';
import { useLang } from '../i18n/LangContext';
import {
  GroupInviteApi,
  type GroupJoinPreview,
} from '../lib/api';

export default function JoinGroup() {
  const { token } = useParams<{ token?: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const toast = useToast();
  const { t } = useLang();

  // Direct Code / Token Flow
  const [codeInput, setCodeInput] = useState(token || '');
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [group, setGroup] = useState<GroupJoinPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [joined, setJoined] = useState(false);

  // If token is in URL, fetch preview immediately
  useEffect(() => {
    if (token) {
      setCodeInput(token);
      fetchPreview(token);
    }
  }, [token]);

  const fetchPreview = async (codeOrToken: string) => {
    const raw = codeOrToken.trim();
    if (!raw) return;
    setLoadingPreview(true);
    setError(null);
    try {
      const data = await GroupInviteApi.preview(raw);
      setGroup(data);
      if (data.is_member) setJoined(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('jg_not_found_text');
      setError(msg);
      setGroup(null);
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleJoin = async (targetTokenOrCode?: string) => {
    const code = targetTokenOrCode || group?.invite_token || group?.invite_code || codeInput.trim();
    if (!code) return;
    setSubmitting(true);
    try {
      const res = await GroupInviteApi.join(code);
      toast.success(res.message || t('jg_joined'));
      setJoined(true);
      const gid = res.group_id;
      setTimeout(() => {
        if (gid) {
          navigate(`/groups/${gid}`);
        } else {
          navigate('/dashboard');
        }
      }, 1000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('jg_join_failed');
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const nextUrl = encodeURIComponent(codeInput ? `/join/${codeInput}` : '/join');

  return (
    <div style={{ maxWidth: 840, margin: '0 auto', padding: '30px 16px 80px', boxSizing: 'border-box' }}>
      {/* Brand Header */}
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <Link to="/" style={{ display: 'inline-flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
          <img src="/logo-mark.png" alt="GRANDEC" width={38} height={38} />
          <span className="text-xl font-extrabold text-slate-900 dark:text-white tracking-wide">
            GRANDEC
          </span>
        </Link>
        <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white mt-3.5 mb-1.5">
          {t('jg_page_title')}
        </h1>
        <p className="m-0 text-sm text-slate-600 dark:text-slate-400">
          {t('jg_page_subtitle')}
        </p>
      </div>

      <div
        className="rounded-2xl p-5 sm:p-7 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-lg box-border"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void fetchPreview(codeInput);
          }}
          className="flex flex-col sm:flex-row gap-3 w-full mb-5"
        >
          <input
            type="text"
            placeholder={t('jg_code_placeholder')}
            value={codeInput}
            onChange={(e) => setCodeInput(e.target.value.toUpperCase())}
            className="w-full sm:flex-1 px-4 py-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/80 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white text-sm sm:text-base font-semibold tracking-wider box-border"
          />
          <button
            type="submit"
            disabled={loadingPreview || !codeInput.trim()}
            className="w-full sm:w-auto px-6 py-3.5 rounded-xl font-bold text-sm text-white flex items-center justify-center gap-2 shrink-0 transition-opacity"
            style={{
              background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
              border: 'none',
              cursor: 'pointer',
              opacity: !codeInput.trim() ? 0.65 : 1,
            }}
          >
            <Search size={16} />
            <span>{loadingPreview ? t('jg_searching') : t('jg_find_btn')}</span>
          </button>
        </form>

        {/* Error */}
        {error && (
          <div
            style={{
              padding: '14px 18px',
              borderRadius: 12,
              background: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: '#EF4444',
              fontSize: 14,
              marginBottom: 16,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <X size={18} />
            <span>{error}</span>
          </div>
        )}

        {/* Group Found Preview */}
        {group && (
          <div
            style={{
              padding: '22px',
              borderRadius: 16,
              background: 'linear-gradient(135deg, rgba(200,146,42,0.12) 0%, rgba(200,146,42,0.03) 100%)',
              border: '1px solid rgba(200,146,42,0.3)',
              marginTop: 10,
            }}
          >
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '4px 10px',
                  borderRadius: 8,
                  background: 'rgba(200,146,42,0.2)',
                  color: '#D97706',
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                <BookOpen size={13} /> {group.subject_display || group.subject}
              </span>

              <span
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-200/70 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-xs font-semibold"
              >
                <Users size={13} /> {t('jg_students').replace('{n}', String(group.student_count))}
              </span>
            </div>

            <h2 className="text-lg sm:text-xl font-bold text-slate-900 dark:text-white m-0 mb-2">
              {group.name}
            </h2>

            <p className="m-0 mb-3.5 text-sm text-slate-700 dark:text-slate-300 flex items-center gap-2">
              <GraduationCap size={16} color="#D97706" />
              <span>{t('jg_teacher')}: <b>{group.teacher_name}</b></span>
            </p>

            {group.description && (
              <p className="m-0 mb-4 text-xs sm:text-sm text-slate-600 dark:text-slate-400">
                {group.description}
              </p>
            )}

            {/* Action Buttons */}
            {joined ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ color: '#10B981', fontWeight: 600, fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <CheckCircle2 size={18} /> {t('jg_already')}
                </div>
                <button
                  type="button"
                  onClick={() => navigate(`/groups/${group.id}`)}
                  style={{
                    padding: '12px 20px',
                    borderRadius: 12,
                    background: '#D97706',
                    color: '#fff',
                    fontWeight: 700,
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: 14,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  {t('jg_to_cabinet')} <ArrowRight size={16} />
                </button>
              </div>
            ) : user ? (
              <button
                type="button"
                onClick={() => void handleJoin()}
                disabled={submitting}
                style={{
                  width: '100%',
                  padding: '14px 20px',
                  borderRadius: 12,
                  background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                  color: '#fff',
                  fontWeight: 700,
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 15,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  boxShadow: '0 4px 15px rgba(217,119,6,0.3)',
                }}
              >
                <Sparkles size={18} />
                {submitting ? t('loading') : t('jg_join')}
              </button>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <Link
                  to={`/login?next=${nextUrl}`}
                  style={{
                    padding: '12px 20px',
                    borderRadius: 12,
                    background: '#D97706',
                    color: '#fff',
                    fontWeight: 700,
                    textDecoration: 'none',
                    textAlign: 'center',
                    fontSize: 14,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  <LogIn size={16} /> {t('jg_login_join')}
                </Link>
                <Link
                  to={`/register?next=${nextUrl}`}
                  className="px-5 py-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-300 dark:border-slate-700 text-center text-sm font-semibold no-underline"
                  style={{ textDecoration: 'none' }}
                >
                  {t('jg_register')}
                </Link>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Umumiy Platforma Peshqadamlari Card (Light & Dark Mode Compliant) */}
      <div
        className="mt-6 p-4 sm:p-5 rounded-2xl bg-amber-50/90 dark:bg-slate-900/90 border border-amber-500/30 flex items-center justify-between flex-wrap gap-3"
      >
        <div>
          <span className="text-sm sm:text-base font-bold text-slate-900 dark:text-white block">
            🌍 {t('jg_leaderboard_card_title')}
          </span>
          <span className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">
            {t('jg_leaderboard_card_desc')}
          </span>
        </div>
        <Link
          to="/leaderboard"
          className="w-full sm:w-auto justify-center"
          style={{
            padding: '10px 18px',
            borderRadius: 10,
            background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
            color: '#fff',
            fontWeight: 700,
            fontSize: 13,
            textDecoration: 'none',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          {t('jg_leaderboard_card_cta')} →
        </Link>
      </div>
    </div>
  );
}
