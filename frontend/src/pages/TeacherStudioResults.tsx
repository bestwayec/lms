import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, Download, Share2 } from 'lucide-react';
import { useLang } from '../i18n/LangContext';
import AssignDialog from '../components/studio/AssignDialog';
import { StudioApi, type ItemAnalysis, type StudioDetail } from '../lib/studio';

/** Accuracy → heat level 0 (all failed) … 4 (all right); null = no data. */
function heat(acc: number | null): number | null {
  if (acc == null) return null;
  if (acc < 20) return 0;
  if (acc < 40) return 1;
  if (acc < 60) return 2;
  if (acc < 80) return 3;
  return 4;
}

/**
 * Teacher results for one test: score distribution + per-question accuracy
 * heatmap (item analysis). Items failed by more than the threshold of students
 * are flagged. Everything comes from finished, non-preview attempts.
 */
export default function TeacherStudioResults() {
  const { id = '' } = useParams<{ id: string }>();
  const { t, lang } = useLang();
  const [detail, setDetail] = useState<StudioDetail | null>(null);
  const [groupId, setGroupId] = useState<number | null>(null);
  const [loaded, setLoaded] = useState<{ key: string; data: ItemAnalysis | null; error: string | null } | null>(null);
  const key = `${id}:${groupId}:${lang}`;
  const current = loaded?.key === key ? loaded : null;
  const data = current?.data ?? null;
  const err = current?.error ?? null;
  const loading = !current;
  const [showMatrix, setShowMatrix] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);

  useEffect(() => {
    StudioApi.detail(id)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    StudioApi.analysis(id, groupId)
      .then((d) => {
        if (!cancelled) setLoaded({ key, data: d, error: null });
      })
      .catch((e) => {
        if (!cancelled) setLoaded({ key, data: null, error: e instanceof Error ? e.message : t('err_retry_js') });
      });
    return () => {
      cancelled = true;
    };
  }, [id, groupId, key, t]);

  const flagged = useMemo(() => (data ? data.items.filter((i) => i.flagged) : []), [data]);
  const maxBucket = data ? Math.max(1, ...data.distribution.map((b) => b.count)) : 1;

  return (
    <div className="studio-page">
      <header className="studio-top">
        <div className="studio-top__crumbs">
          <Link to="/teacher/studio" className="studio-back">
            <ArrowLeft size={16} aria-hidden="true" /> {t('studio_title')}
          </Link>
        </div>
        <h1 className="studio-h1">{data?.title ?? detail?.test.title ?? t('studio_results')}</h1>
        <div className="studio-top__actions">
          {data && data.assignments.length > 0 && (
            <select
              aria-label={t('studio_group_filter')}
              value={groupId ?? ''}
              onChange={(e) => setGroupId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">{t('studio_all_groups')}</option>
              {data.assignments.map((a) => (
                <option key={a.group_id} value={a.group_id}>
                  {a.group_name}
                </option>
              ))}
            </select>
          )}
          {detail?.test.status === 'published' && (
            <button type="button" className="btn sm primary" onClick={() => setAssignOpen(true)}>
              <Share2 size={14} aria-hidden="true" /> {t('studio_assign')}
            </button>
          )}
          <a
            href={StudioApi.exportUrl(id)}
            download={`test_${id}_questions.csv`}
            className="btn sm ghost"
            title={t('studio_export_csv', 'Savollarni CSV yuklab olish')}
          >
            <Download size={14} aria-hidden="true" /> CSV
          </a>
        </div>
      </header>

      {err && (
        <div className="studio-alert is-bad" role="alert">
          <AlertTriangle size={18} aria-hidden="true" /> {err}
        </div>
      )}
      {loading && !data && (
        <div role="status">
          <div className="studio-skeleton" />
          <p className="muted">{t('loading')}</p>
        </div>
      )}

      {data && data.students === 0 && (
        <div className="studio-empty">
          <p>{t('studio_results_empty')}</p>
        </div>
      )}

      {data && data.students > 0 && (
        <>
          <div className="studio-kpis" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10 }}>
            <div className="card studio-kpi">
              <span>{t('studio_kpi_assigned', 'Biriktirilgan')}</span>
              <strong>{data.total_assigned ?? data.students}</strong>
            </div>
            <div className="card studio-kpi">
              <span>{t('studio_kpi_students', 'Topshirgan')}</span>
              <strong>{data.submitted_count ?? data.students}</strong>
            </div>
            {(data.unsubmitted_count ?? 0) > 0 && (
              <div className="card studio-kpi is-warn">
                <span>{t('studio_kpi_unsubmitted', 'Topshirmagan')}</span>
                <strong>{data.unsubmitted_count}</strong>
              </div>
            )}
            {(data.pending_review_count ?? 0) > 0 && (
              <div className="card studio-kpi is-warn" style={{ background: 'var(--yellow-bg, #fefce8)' }}>
                <span>{t('studio_kpi_pending', 'Tekshirilmoqda')}</span>
                <strong>{data.pending_review_count}</strong>
              </div>
            )}
            <div className="card studio-kpi">
              <span>{t('studio_kpi_average')}</span>
              <strong>{data.average != null ? `${data.average}%` : '—'}</strong>
            </div>
            <div className="card studio-kpi">
              <span>{t('studio_kpi_median')}</span>
              <strong>{data.median != null ? `${data.median}%` : '—'}</strong>
            </div>
            <div className={`card studio-kpi${flagged.length ? ' is-warn' : ''}`}>
              <span>{t('studio_kpi_flagged')}</span>
              <strong>{flagged.length}</strong>
            </div>
          </div>

          <div className="studio-results">
            <section className="card studio-dist" aria-labelledby="studio-dist-h">
              <h2 id="studio-dist-h">{t('studio_distribution')}</h2>
              <div className="studio-dist__bars" role="list">
                {data.distribution.map((b) => (
                  <div
                    key={b.from}
                    className="studio-dist__col"
                    role="listitem"
                    aria-label={t('studio_dist_bar').replace('{range}', `${b.from}–${b.to}%`).replace('{n}', String(b.count))}
                  >
                    <span className="studio-dist__count">{b.count || ''}</span>
                    <div className="studio-dist__bar" style={{ height: `${(b.count / maxBucket) * 100}%` }} />
                    <span className="studio-dist__label">{b.from}</span>
                  </div>
                ))}
              </div>
              <p className="muted small">{t('studio_dist_axis')}</p>
            </section>

            {data.topics && data.topics.length > 0 && (
              <section className="card studio-topics" aria-labelledby="studio-topics-h">
                <h2 id="studio-topics-h">{t('studio_weak_topics', 'Mavzular bo‘yicha natija (eng zaifi birinchi)')}</h2>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 8 }}>
                  {data.topics.map((tp) => (
                    <li key={tp.topic}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 14 }}>
                        <strong>{t(`topic_${tp.topic}`, tp.topic)}</strong>
                        <span className="muted">
                          {t('studio_topic_accuracy', 'To‘g‘ri javoblar')}: {tp.correct}/{tp.possible}
                          {tp.accuracy !== null ? ` · ${tp.accuracy}%` : ''}
                        </span>
                      </div>
                      <div
                        role="progressbar"
                        aria-label={t(`topic_${tp.topic}`, tp.topic)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={tp.accuracy ?? 0}
                        style={{ height: 8, borderRadius: 4, background: 'var(--border)', overflow: 'hidden', marginTop: 4 }}
                      >
                        <div
                          style={{
                            width: `${tp.accuracy ?? 0}%`,
                            height: '100%',
                            background: (tp.accuracy ?? 0) < 60 ? 'var(--danger, #DC2626)' : 'var(--emerald, #059669)',
                          }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="card studio-heat" aria-labelledby="studio-heat-h">
              <div className="studio-heat__head">
                <h2 id="studio-heat-h">{t('studio_heatmap')}</h2>
                <div className="studio-legend" aria-hidden="true">
                  <span>0%</span>
                  {[0, 1, 2, 3, 4].map((l) => (
                    <i key={l} className={`studio-heat__cell is-h${l}`} />
                  ))}
                  <span>100%</span>
                </div>
              </div>
              <p className="muted small">{t('studio_heat_hint').replace('{n}', String(data.flag_threshold))}</p>
              <ul className="studio-heat__grid">
                {data.items.map((it) => {
                  const h = heat(it.accuracy);
                  return (
                    <li
                      key={it.question_id}
                      className={`studio-heat__cell ${h == null ? 'is-none' : `is-h${h}`}${it.flagged ? ' is-flagged' : ''}`}
                      title={`${it.number}. ${it.text}`}
                    >
                      <b>{it.number}</b>
                      <span>{it.accuracy != null ? `${Math.round(it.accuracy)}%` : '—'}</span>
                      <span className="sr-only">
                        {t('studio_heat_cell').replace('{c}', String(it.correct)).replace('{n}', String(it.total))}
                        {it.flagged ? `, ${t('studio_flagged')}` : ''}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </section>
          </div>

          {flagged.length > 0 && (
            <section className="card studio-flagged" aria-labelledby="studio-flag-h">
              <h2 id="studio-flag-h">
                <AlertTriangle size={18} aria-hidden="true" /> {t('studio_flagged_title')}
              </h2>
              <ul>
                {flagged.map((it) => (
                  <li key={it.question_id}>
                    <span className="studio-flagged__num">{it.number}</span>
                    <span className="studio-flagged__text">{it.text || t(`studio_qtype_${it.question_type}`, it.question_type)}</span>
                    <span className="studio-flagged__stat">
                      {t('studio_heat_cell').replace('{c}', String(it.correct)).replace('{n}', String(it.total))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="card studio-matrix-card">
            <button type="button" className="btn sm" aria-expanded={showMatrix} onClick={() => setShowMatrix((v) => !v)}>
              {showMatrix ? t('studio_hide_students') : t('studio_show_students')}
            </button>
            {showMatrix && (
              <div className="table-wrap studio-student-matrix">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">{t('th_student')}</th>
                      <th scope="col">%</th>
                      {data.items.map((it) => (
                        <th key={it.question_id} scope="col">
                          {it.number}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.matrix.map((row) => (
                      <tr key={row.attempt_id}>
                        <th scope="row">{row.student}</th>
                        <td>
                          {row.is_pending ? (
                            <span style={{ fontSize: '0.75rem', padding: '2px 6px', borderRadius: 4, background: '#fef3c7', color: '#92400e' }}>
                              {t('status_awaiting_review', 'Kutilmoqda')}
                            </span>
                          ) : (
                            `${Math.round(row.percentage ?? 0)}%`
                          )}
                        </td>
                        {row.cells.map((c, i) => (
                          <td
                            key={i}
                            className={c == null ? 'studio-mx is-none' : c ? 'studio-mx is-ok' : 'studio-mx is-bad'}
                            aria-label={c == null ? t('studio_cell_blank') : c ? t('studio_cell_right') : t('studio_cell_wrong')}
                          >
                            {c == null ? '·' : c ? '✓' : '✗'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {assignOpen && detail && (
        <AssignDialog
          testId={detail.test.id}
          testTitle={detail.test.title}
          links={detail.links}
          assignments={detail.assignments}
          onClose={() => setAssignOpen(false)}
        />
      )}
    </div>
  );
}
