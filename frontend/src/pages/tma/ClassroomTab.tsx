import { useEffect, useState } from 'react';
import { useLang } from '../../i18n/LangContext';
import { TmaApi, tmaErrorMessage } from './api';

interface GroupAssignment {
  id: number;
  title: string;
  test_id?: number;
  test_title?: string;
  due_date?: string | null;
  is_classroom_entitlement: boolean;
  can_start: boolean;
  access_reason?: string;
}

interface StudentGroupItem {
  id: number;
  name: string;
  subject: string;
  teacher_name: string;
  assignments: GroupAssignment[];
}

export default function ClassroomTab({ onOpenTest }: { onOpenTest: (testId: number) => void }) {
  const { t } = useLang();
  const [groups, setGroups] = useState<StudentGroupItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [joinCode, setJoinCode] = useState('');
  const [joining, setJoining] = useState(false);
  const [joinMsg, setJoinMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const fetchGroups = async () => {
    try {
      setLoading(true);
      const res = await TmaApi.myGroups();
      setGroups(res.groups || []);
      setError(null);
    } catch (e) {
      setError(tmaErrorMessage(e, t('tma_loading_error')));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchGroups();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleJoin = async () => {
    const clean = joinCode.trim();
    if (!clean) return;
    setJoining(true);
    setJoinMsg(null);
    try {
      const isToken = clean.length > 20 && !clean.includes('-');
      const res = isToken
        ? await TmaApi.joinGroup(undefined, clean)
        : await TmaApi.joinGroup(clean, undefined);

      setJoinMsg({ type: 'ok', text: res.message || t('tma_join_success') });
      setJoinCode('');
      void fetchGroups();
    } catch (e) {
      setJoinMsg({ type: 'err', text: tmaErrorMessage(e, t('tma_join_error')) });
    } finally {
      setJoining(false);
    }
  };

  return (
    <div className="tma-slide">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>🏫 {t('classroom') || 'Mening sinfxonalarim'}</h2>
        <span className="tma-badge" style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#2563eb' }}>
          {groups?.length ?? 0} {t('tma_groups_count')}
        </span>
      </div>

      {/* Join group with code card */}
      <div className="tma-card" style={{ marginBottom: 20 }}>
        <p className="tma-sub" style={{ marginBottom: 8, fontWeight: 700, color: 'var(--tma-ink)' }}>
          🔑 {t('join_with_code') || "Taklif kodi orqali guruhga qo'shilish"}
        </p>
        <p className="tma-muted" style={{ marginBottom: 12, fontSize: 12 }}>
          {t('tma_join_hint')}
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            className="tma-input"
            placeholder={t('tma_join_placeholder')}
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleJoin();
            }}
          />
          <button
            className="tma-btn tma-btn-hl"
            style={{ width: 'auto', padding: '0 20px', whiteSpace: 'nowrap' }}
            disabled={joining || !joinCode.trim()}
            onClick={() => void handleJoin()}
          >
            {joining ? '…' : (t('join') || "Qo'shilish")}
          </button>
        </div>
        {joinMsg && (
          <p
            style={{
              fontSize: 13,
              fontWeight: 600,
              marginTop: 10,
              color: joinMsg.type === 'ok' ? '#16a34a' : '#dc2626',
            }}
          >
            {joinMsg.type === 'ok' ? '✓ ' : '✕ '}
            {joinMsg.text}
          </p>
        )}
      </div>

      {loading && (
        <div className="tma-list">
          <div className="tma-skel" />
          <div className="tma-skel" />
        </div>
      )}

      {error && <div className="tma-err">{error}</div>}

      {!loading && groups && groups.length === 0 && (
        <div className="tma-card tma-center" style={{ padding: 32 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🎓</div>
          <h3 style={{ fontSize: 16, fontWeight: 800, margin: '0 0 8px' }}>
            {t('no_classroom_yet') || 'Siz hali biron bir guruhga a\'zo emassiz'}
          </h3>
          <p className="tma-muted" style={{ fontSize: 13, lineHeight: 1.5, marginBottom: 0 }}>
            {t('tma_join_empty_hint')}
          </p>
        </div>
      )}

      {!loading && groups && groups.length > 0 && (
        <div className="tma-list">
          {groups.map((g) => (
            <div key={g.id} className="tma-card">
              <div className="tma-row" style={{ marginBottom: 12 }}>
                <div className="tma-ico" style={{ background: 'rgba(217, 119, 6, 0.15)', color: '#d97706' }}>
                  🏫
                </div>
                <div className="tma-grow">
                  <p className="tma-title" style={{ fontSize: 16 }}>{g.name}</p>
                  <p className="tma-sub" style={{ marginTop: 2 }}>
                    👨‍🏫 {g.teacher_name} · <span style={{ textTransform: 'capitalize' }}>{g.subject}</span>
                  </p>
                </div>
              </div>

              {/* Group assignments */}
              <div>
                <p className="tma-sub" style={{ fontWeight: 700, color: 'var(--tma-ink)', marginBottom: 8 }}>
                  📝 {t('assigned_tests') || 'Biriktirilgan vazifalar'} ({g.assignments.length}):
                </p>
                {g.assignments.length === 0 ? (
                  <p className="tma-muted" style={{ fontSize: 12, margin: '4px 0 0' }}>
                    {t('tma_no_hw_yet')}
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {g.assignments.map((hw) => (
                      <div
                        key={hw.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          background: 'var(--tma-elevated)',
                          padding: '10px 12px',
                          borderRadius: 10,
                          border: '1px solid var(--tma-border)',
                        }}
                      >
                        <div style={{ minWidth: 0, flex: 1, marginRight: 8 }}>
                          <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: 'var(--tma-ink)' }}>
                            {hw.test_title || hw.title}
                          </p>
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 2, flexWrap: 'wrap' }}>
                            <span className="tma-badge" style={{ background: 'rgba(34,197,94,0.15)', color: '#16a34a', fontSize: 10 }}>
                              {t('free_classroom_test') || 'Guruh testi (Bepul)'}
                            </span>
                            {hw.due_date && (
                              <span className="tma-sub" style={{ fontSize: 11 }}>
                                ⏰ {hw.due_date}
                              </span>
                            )}
                          </div>
                        </div>
                        {hw.test_id && (
                          <button
                            type="button"
                            className="tma-btn tma-btn-hl"
                            style={{
                              width: 'auto',
                              padding: '6px 14px',
                              fontSize: 12,
                              borderRadius: 8,
                            }}
                            onClick={() => onOpenTest(hw.test_id!)}
                          >
                            {t('start_test') || 'Boshlash'}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
