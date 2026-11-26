import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Download, FileText, GraduationCap, Inbox, ShieldCheck } from 'lucide-react';
import { useLang } from '../i18n/LangContext';
import { apiFetch, SpeakingApi } from '../lib/api';

interface WorkspacePayload {
  groups: { id: number; name: string; subject: string }[];
  inbox: {
    writing: { id: number; student: string; topic: string; scale: string; score: number; max_score: number }[];
    speaking: { id: number; student: string; topic: string; track: string; ai_band: number | null }[];
    mocks: { attempt_id: number; student: string; test_title: string; exam_type: string }[];
  };
  ielts_analytics: {
    scale: string;
    attempts_count: number;
    avg_band: number | null;
    writing_avg_band: number | null;
    speaking_avg_band: number | null;
  };
  multilevel_analytics: {
    scale: string;
    attempts_count: number;
    avg_score_75: number | null;
    level_distribution: Record<string, number>;
  };
  override_audit: {
    kind: string;
    id: number;
    student: string;
    title: string;
    score: number;
    teacher: string;
    comment: string;
  }[];
}

export default function TeacherEnglishWorkspace() {
  const { t } = useLang();
  const [groupId, setGroupId] = useState<string>('');
  const [data, setData] = useState<WorkspacePayload | null>(null);
  const [tab, setTab] = useState<'writing' | 'speaking' | 'mocks'>('writing');
  const [spkScore, setSpkScore] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const qs = groupId ? `?group_id=${groupId}` : '';
    apiFetch<WorkspacePayload>(`/api/v1/english/teacher/workspace/${qs}`)
      .then((res) => {
        if (active) {
          setData(res);
          setErr(null);
        }
      })
      .catch((e: unknown) => {
        if (active) setErr(e instanceof Error ? e.message : t('err_retry_js'));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [groupId, t]);

  const gradeSpeaking = async (subId: number) => {
    const val = Number(spkScore[subId]);
    if (!Number.isFinite(val)) return;
    await SpeakingApi.teacherReview(subId, { score: val, comments: 'Teacher reviewed' });
    setData((prev) =>
      prev
        ? {
            ...prev,
            inbox: { ...prev.inbox, speaking: prev.inbox.speaking.filter((s) => s.id !== subId) },
          }
        : prev,
    );
  };

  const exportUrl = (fmt: 'csv' | 'pdf') =>
    `/api/v1/english/teacher/export/?export_format=${fmt}${groupId ? `&group_id=${groupId}` : ''}`;

  return (
    <div className="max-w-[1280px] mx-auto w-full px-3 sm:px-6 py-4 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to="/teacher" className="btn ghost sm">
            <ArrowLeft size={15} /> {t('teacher_dashboard')}
          </Link>
          <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
            <GraduationCap size={22} className="text-indigo-600 dark:text-indigo-400" />
            <span>{t('ten_workspace_title')}</span>
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {data?.groups && data.groups.length > 0 && (
            <select
              className="input sm"
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
            >
              <option value="">{t('ten_all_groups')}</option>
              {data.groups.map((g) => (
                <option key={g.id} value={String(g.id)}>
                  {g.name}
                </option>
              ))}
            </select>
          )}
          <a href={exportUrl('csv')} className="btn sm ghost" download>
            <Download size={14} /> CSV
          </a>
          <a href={exportUrl('pdf')} className="btn sm primary" download>
            <FileText size={14} /> PDF
          </a>
        </div>
      </div>

      {err && <div className="card error">{err}</div>}
      {loading ? (
        <div className="bento-card p-8 text-center muted">{t('loading')}</div>
      ) : (
        data && (
          <>
            {/* Separated IELTS vs Multilevel KPI Cards (scales are NEVER mixed) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <section className="bento-card p-5 space-y-2">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-extrabold text-slate-900 dark:text-white">
                    IELTS Academic & General (Band 0–9)
                  </h2>
                  <span className="badge blue">{data.ielts_analytics.attempts_count} mocks</span>
                </div>
                <div className="grid grid-cols-3 gap-2 pt-2 text-center">
                  <div>
                    <div className="text-xs muted">Mock Avg</div>
                    <div className="text-lg font-black">{data.ielts_analytics.avg_band ?? '—'}</div>
                  </div>
                  <div>
                    <div className="text-xs muted">Writing Avg</div>
                    <div className="text-lg font-black">{data.ielts_analytics.writing_avg_band ?? '—'}</div>
                  </div>
                  <div>
                    <div className="text-xs muted">Speaking Avg</div>
                    <div className="text-lg font-black">{data.ielts_analytics.speaking_avg_band ?? '—'}</div>
                  </div>
                </div>
              </section>

              <section className="bento-card p-5 space-y-2">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-extrabold text-slate-900 dark:text-white">
                    CEFR Multi-level (BMB / 75)
                  </h2>
                  <span className="badge blue">{data.multilevel_analytics.attempts_count} mocks</span>
                </div>
                <div className="grid grid-cols-4 gap-2 pt-2 text-center">
                  <div>
                    <div className="text-xs muted">Avg / 75</div>
                    <div className="text-lg font-black">{data.multilevel_analytics.avg_score_75 ?? '—'}</div>
                  </div>
                  <div>
                    <div className="text-xs muted">B1</div>
                    <div className="text-lg font-black">{data.multilevel_analytics.level_distribution.B1 || 0}</div>
                  </div>
                  <div>
                    <div className="text-xs muted">B2</div>
                    <div className="text-lg font-black">{data.multilevel_analytics.level_distribution.B2 || 0}</div>
                  </div>
                  <div>
                    <div className="text-xs muted">C1</div>
                    <div className="text-lg font-black">{data.multilevel_analytics.level_distribution.C1 || 0}</div>
                  </div>
                </div>
              </section>
            </div>

            {/* Unified Grading Inbox */}
            <section className="bento-card p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-extrabold flex items-center gap-2">
                  <Inbox size={18} /> {t('ten_inbox_title')}
                </h2>
                <div className="flex gap-2">
                  <button type="button" className={`btn sm ${tab === 'writing' ? 'primary' : 'ghost'}`} onClick={() => setTab('writing')}>
                    Writing ({data.inbox.writing.length})
                  </button>
                  <button type="button" className={`btn sm ${tab === 'speaking' ? 'primary' : 'ghost'}`} onClick={() => setTab('speaking')}>
                    Speaking ({data.inbox.speaking.length})
                  </button>
                  <button type="button" className={`btn sm ${tab === 'mocks' ? 'primary' : 'ghost'}`} onClick={() => setTab('mocks')}>
                    Mocks ({data.inbox.mocks.length})
                  </button>
                </div>
              </div>

              {tab === 'writing' && (
                data.inbox.writing.length === 0 ? (
                  <p className="muted small">{t('ten_inbox_empty')}</p>
                ) : (
                  <ul className="space-y-2">
                    {data.inbox.writing.map((w) => (
                      <li key={w.id} className="flex items-center justify-between gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-800">
                        <div>
                          <strong>{w.student}</strong> — <span>{w.topic}</span>{' '}
                          <span className="muted small">({w.score}/{w.max_score})</span>
                        </div>
                        <Link to={`/teacher/essays/${w.id}/review`} className="btn sm primary">
                          {t('tr_open_review')} →
                        </Link>
                      </li>
                    ))}
                  </ul>
                )
              )}

              {tab === 'speaking' && (
                data.inbox.speaking.length === 0 ? (
                  <p className="muted small">{t('ten_inbox_empty')}</p>
                ) : (
                  <ul className="space-y-2">
                    {data.inbox.speaking.map((s) => (
                      <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-800">
                        <div>
                          <strong>{s.student}</strong> — <span>{s.topic}</span>{' '}
                          <span className="muted small">({s.track})</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            step="0.5"
                            min="0"
                            max={s.track === 'cefr_multilevel' ? '75' : '9'}
                            className="input sm"
                            style={{ width: 90 }}
                            placeholder={s.track === 'cefr_multilevel' ? '0..75' : 'Band'}
                            value={spkScore[s.id] || ''}
                            onChange={(e) => setSpkScore((prev) => ({ ...prev, [s.id]: e.target.value }))}
                          />
                          <button type="button" className="btn sm primary" onClick={() => void gradeSpeaking(s.id)}>
                            {t('save')}
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )
              )}

              {tab === 'mocks' && (
                data.inbox.mocks.length === 0 ? (
                  <p className="muted small">{t('ten_inbox_empty')}</p>
                ) : (
                  <ul className="space-y-2">
                    {data.inbox.mocks.map((m) => (
                      <li key={m.attempt_id} className="flex items-center justify-between gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-800">
                        <div>
                          <strong>{m.student}</strong> — <span>{m.test_title}</span> ({m.exam_type})
                        </div>
                        <Link to={`/results`} className="btn sm ghost">
                          {t('tr_open_review')}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )
              )}
            </section>

            {/* Override Audit Trail */}
            {data.override_audit.length > 0 && (
              <section className="bento-card p-5 space-y-3">
                <h2 className="text-base font-extrabold flex items-center gap-2">
                  <ShieldCheck size={18} /> {t('ten_override_audit')}
                </h2>
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>{t('th_student')}</th>
                        <th>{t('th_topic')}</th>
                        <th>{t('score')}</th>
                        <th>Teacher</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.override_audit.map((row) => (
                        <tr key={`${row.kind}-${row.id}`}>
                          <td>{row.student}</td>
                          <td>{row.title}</td>
                          <td>{row.score}</td>
                          <td>{row.teacher}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </>
        )
      )}
    </div>
  );
}
