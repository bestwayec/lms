import { useEffect, useState } from 'react';
import { useLang } from '../../i18n/LangContext';
import { TmaApi, tmaErrorMessage } from './api';

type Scope = 'platform' | 'group';

export default function LeaderboardTab() {
  const { t } = useLang();
  const [scope, setScope] = useState<Scope>('platform');
  const [period, setPeriod] = useState<'weekly' | 'all_time'>('weekly');
  const [groups, setGroups] = useState<any[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);

  const [platformData, setPlatformData] = useState<any | null>(null);
  const [groupData, setGroupData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    TmaApi.myGroups()
      .then((res) => {
        const grps = res.groups || [];
        setGroups(grps);
        if (grps.length > 0 && selectedGroupId === null) {
          setSelectedGroupId(grps[0].id);
        }
      })
      .catch(() => undefined);
  }, [selectedGroupId]);

  useEffect(() => {
    let alive = true;

    if (scope === 'platform') {
      TmaApi.platformLeaderboard(period)
        .then((data) => {
          if (alive) setPlatformData(data);
        })
        .catch((e) => {
          if (alive) setError(tmaErrorMessage(e, t('tma_loading_error')));
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    } else if (selectedGroupId) {
      TmaApi.groupLeaderboard(selectedGroupId)
        .then((data) => {
          if (alive) setGroupData(data);
        })
        .catch((e) => {
          if (alive) setError(tmaErrorMessage(e, t('tma_loading_error')));
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }

    return () => {
      alive = false;
    };
  }, [scope, period, selectedGroupId, t]);

  return (
    <div className="tma-slide">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>🏆 {t('leaderboard') || 'Peshqadamlar reytingi'}</h2>
      </div>

      {/* Scope toggle: Platform vs Group */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
        <button
          type="button"
          className={`tma-btn ${scope === 'platform' ? 'tma-btn-hl' : 'tma-btn-card'}`}
          style={{ padding: '10px 14px', fontSize: 13 }}
          onClick={() => setScope('platform')}
        >
          🌐 {t('platform_rating') || 'Umumiy reyting'}
        </button>
        <button
          type="button"
          className={`tma-btn ${scope === 'group' ? 'tma-btn-hl' : 'tma-btn-card'}`}
          style={{ padding: '10px 14px', fontSize: 13 }}
          onClick={() => setScope('group')}
        >
          🏫 {t('group_rating') || 'Sinfxona'}
        </button>
      </div>

      {scope === 'platform' && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <button
            type="button"
            className={`tma-badge ${period === 'weekly' ? 'tma-diff-medium' : ''}`}
            style={{
              padding: '6px 14px',
              fontSize: 12,
              cursor: 'pointer',
              border: period === 'weekly' ? 'none' : '1px solid #cbd5e1',
              background: period === 'weekly' ? 'var(--tma-accent)' : '#fff',
              color: period === 'weekly' ? '#fff' : 'var(--tma-muted)',
            }}
            onClick={() => setPeriod('weekly')}
          >
            Haftalik XP
          </button>
          <button
            type="button"
            className={`tma-badge ${period === 'all_time' ? 'tma-diff-medium' : ''}`}
            style={{
              padding: '6px 14px',
              fontSize: 12,
              cursor: 'pointer',
              border: period === 'all_time' ? 'none' : '1px solid #cbd5e1',
              background: period === 'all_time' ? 'var(--tma-accent)' : '#fff',
              color: period === 'all_time' ? '#fff' : 'var(--tma-muted)',
            }}
            onClick={() => setPeriod('all_time')}
          >
            Barcha davrlar
          </button>
        </div>
      )}

      {scope === 'group' && groups.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <select
            className="tma-input"
            value={selectedGroupId || ''}
            onChange={(e) => setSelectedGroupId(Number(e.target.value))}
            style={{ fontWeight: 600 }}
          >
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name} ({g.teacher_name})
              </option>
            ))}
          </select>
        </div>
      )}

      {loading && (
        <div className="tma-list">
          <div className="tma-skel" />
          <div className="tma-skel" />
          <div className="tma-skel" />
        </div>
      )}

      {error && <div className="tma-err">{error}</div>}

      {/* Platform Leaderboard Render */}
      {!loading && scope === 'platform' && platformData && (
        <div>
          {platformData.user_rank && (
            <div className="tma-card" style={{ background: '#fef3c7', borderColor: '#fcd34d', marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 700, color: '#92400e', fontSize: 13 }}>
                  ⚡ Sizning o'rningiz:
                </span>
                <span style={{ fontWeight: 800, fontSize: 16, color: '#b45309' }}>
                  #{platformData.user_rank}
                </span>
              </div>
            </div>
          )}

          <div className="tma-list">
            {(platformData.items || []).map((item: any) => (
              <div
                key={item.rank}
                className="tma-card"
                style={{
                  padding: '12px 16px',
                  background: item.is_current_user ? '#fffbeb' : '#fff',
                  border: item.is_current_user ? '1.5px solid #d97706' : '1px solid #e2e8f0',
                }}
              >
                <div className="tma-row">
                  <div
                    style={{
                      width: 32,
                      fontSize: 16,
                      fontWeight: 800,
                      textAlign: 'center',
                    }}
                  >
                    {item.badge}
                  </div>
                  <div className="tma-grow">
                    <p className="tma-title" style={{ fontSize: 14 }}>
                      {item.display_name}
                      {item.is_current_user && (
                        <span className="tma-badge" style={{ marginLeft: 6, background: '#fef3c7', color: '#b45309' }}>
                          Siz
                        </span>
                      )}
                    </p>
                    <p className="tma-sub" style={{ marginTop: 2 }}>
                      🔥 {item.streak || 0} kun streak
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontWeight: 800, fontSize: 15, color: '#d97706' }}>
                      {item.xp} XP
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Group Leaderboard Render */}
      {!loading && scope === 'group' && groupData && (
        <div>
          <div className="tma-list">
            {(groupData.leaderboard || []).map((item: any) => (
              <div
                key={item.student_id}
                className="tma-card"
                style={{
                  padding: '12px 16px',
                  background: item.is_me ? '#fffbeb' : '#fff',
                  border: item.is_me ? '1.5px solid #d97706' : '1px solid #e2e8f0',
                }}
              >
                <div className="tma-row">
                  <div
                    style={{
                      width: 32,
                      fontSize: 16,
                      fontWeight: 800,
                      textAlign: 'center',
                    }}
                  >
                    {item.badge}
                  </div>
                  <div className="tma-grow">
                    <p className="tma-title" style={{ fontSize: 14 }}>
                      {item.full_name}
                      {item.is_me && (
                        <span className="tma-badge" style={{ marginLeft: 6, background: '#fef3c7', color: '#b45309' }}>
                          Siz
                        </span>
                      )}
                    </p>
                    <p className="tma-sub" style={{ marginTop: 2 }}>
                      📝 {item.tests_count} test ({item.avg_percentage}%) · ✍️ {item.essays_count} esse
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontWeight: 800, fontSize: 14, color: '#16a34a' }}>
                      {item.score_metric} ball
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
