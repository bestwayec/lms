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
    <div style={{ maxWidth: 840, margin: '0 auto', padding: '30px 16px 80px' }}>
      {/* Brand Header */}
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <Link to="/" style={{ display: 'inline-flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
          <img src="/logo-mark.png" alt="" width={38} height={38} />
          <span style={{ fontSize: 20, fontWeight: 800, color: 'var(--text-primary, #F8FAFC)', letterSpacing: 0.5 }}>
            GRAND EDUCATION
          </span>
        </Link>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: '14px 0 6px' }}>
          Guruhga va Kursxonaga Qo‘shilish
        </h1>
        <p style={{ margin: 0, color: 'var(--text-secondary, #94A3B8)', fontSize: 14 }}>
          Ustozingiz bergan 6 xonali guruh kodi yoki taklif havolasi orqali guruhga a‘zo bo‘ling.
        </p>
      </div>

      <div
        style={{
          background: 'var(--card-bg, #1E293B)',
          borderRadius: 20,
          padding: '28px 24px',
          border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
          boxShadow: '0 8px 30px rgba(0,0,0,0.2)',
        }}
      >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              fetchPreview(codeInput);
            }}
            style={{ display: 'flex', gap: 10, marginBottom: 20 }}
          >
            <input
              type="text"
              placeholder="Guruh kodini kiriting (masalan: BIO-104, KIM-205, HUQ-301)"
              value={codeInput}
              onChange={(e) => setCodeInput(e.target.value.toUpperCase())}
              style={{
                flex: 1,
                padding: '13px 16px',
                borderRadius: 12,
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.15)',
                color: '#fff',
                fontSize: 15,
                fontWeight: 600,
                letterSpacing: 1,
              }}
            />
            <button
              type="submit"
              disabled={loadingPreview || !codeInput.trim()}
              style={{
                padding: '13px 24px',
                borderRadius: 12,
                background: '#C8922A',
                color: '#fff',
                fontWeight: 600,
                fontSize: 14,
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                opacity: !codeInput.trim() ? 0.6 : 1,
              }}
            >
              <Search size={16} />
              {loadingPreview ? 'Qidirilmoqda...' : 'Topish'}
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
                color: '#F87171',
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
                    color: '#F59E0B',
                    fontSize: 12,
                    fontWeight: 700,
                  }}
                >
                  <BookOpen size={13} /> {group.subject_display || group.subject}
                </span>

                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '4px 10px',
                    borderRadius: 8,
                    background: 'rgba(255,255,255,0.08)',
                    color: '#CBD5E1',
                    fontSize: 12,
                  }}
                >
                  <Users size={13} /> {group.student_count} nafar o‘quvchi
                </span>
              </div>

              <h2 style={{ fontSize: 20, fontWeight: 700, margin: '0 0 8px', color: '#F8FAFC' }}>
                {group.name}
              </h2>

              <p style={{ margin: '0 0 14px', fontSize: 14, color: '#CBD5E1', display: 'flex', alignItems: 'center', gap: 8 }}>
                <GraduationCap size={16} color="#C8922A" />
                Ustoz: <b>{group.teacher_name}</b>
              </p>

              {group.description && (
                <p style={{ margin: '0 0 16px', fontSize: 13, color: '#94A3B8' }}>
                  {group.description}
                </p>
              )}

              {/* Action Buttons */}
              {joined ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ color: '#10B981', fontWeight: 600, fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <CheckCircle2 size={18} /> Siz allaqachon ushbu guruh a‘zosisiz!
                  </div>
                  <button
                    onClick={() => navigate(`/groups/${group.id}`)}
                    style={{
                      padding: '12px 20px',
                      borderRadius: 12,
                      background: '#C8922A',
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
                    Guruh Sahifasiga O‘tish <ArrowRight size={16} />
                  </button>
                </div>
              ) : user ? (
                <button
                  onClick={() => handleJoin()}
                  disabled={submitting}
                  style={{
                    width: '100%',
                    padding: '14px 20px',
                    borderRadius: 12,
                    background: 'linear-gradient(135deg, #C8922A 0%, #D97706 100%)',
                    color: '#fff',
                    fontWeight: 700,
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: 15,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                    boxShadow: '0 4px 15px rgba(200,146,42,0.3)',
                  }}
                >
                  <Sparkles size={18} />
                  {submitting ? 'Qo‘shilmoqda...' : 'Guruhga Qo‘shilish (1-klikda)'}
                </button>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <Link
                    to={`/login?next=${nextUrl}`}
                    style={{
                      padding: '12px 20px',
                      borderRadius: 12,
                      background: '#C8922A',
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
                    <LogIn size={16} /> Kirish va Guruhga Qo‘shilish
                  </Link>
                  <Link
                    to={`/register?next=${nextUrl}`}
                    style={{
                      padding: '11px 20px',
                      borderRadius: 12,
                      background: 'rgba(255,255,255,0.06)',
                      color: '#CBD5E1',
                      textDecoration: 'none',
                      textAlign: 'center',
                      fontSize: 14,
                      border: '1px solid rgba(255,255,255,0.12)',
                    }}
                  >
                    Ro‘yxatdan o‘tish
                  </Link>
                </div>
              )}
            </div>
          )}
        </div>

      <div
        style={{
          marginTop: 24,
          padding: '16px 20px',
          borderRadius: 16,
          background: 'rgba(245, 158, 11, 0.08)',
          border: '1px solid rgba(245, 158, 11, 0.25)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#F8FAFC', display: 'block' }}>
            🌍 Umumiy Platforma Peshqadamlari
          </span>
          <span style={{ fontSize: 12, color: '#94A3B8' }}>
            Barcha fanlar va guruhlar bo‘yicha respublika miqyosidagi jonli natijalar bilan tanishing.
          </span>
        </div>
        <Link
          to="/leaderboard"
          style={{
            padding: '9px 18px',
            borderRadius: 10,
            background: '#C8922A',
            color: '#fff',
            fontWeight: 700,
            fontSize: 13,
            textDecoration: 'none',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          Umumiy reytingni ko‘rish →
        </Link>
      </div>
    </div>
  );
}
