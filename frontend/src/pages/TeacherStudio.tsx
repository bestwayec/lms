import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BarChart3, Copy, Download, PenLine, Plus, Search, Share2, Trash2 } from 'lucide-react';
import { useAuth } from '../auth/authState';
import { useLang } from '../i18n/LangContext';
import { TeacherEssays, canReviewEssays, type TeacherEssayCard } from '../lib/api';
import {
  ASSESSMENT_CATEGORIES,
  STUDIO_SUBJECTS,
  StudioApi,
  type StudioDetail,
  type StudioListItem,
} from '../lib/studio';
import AssignDialog from '../components/studio/AssignDialog';
import EssayReviewDrawer from '../components/studio/EssayReviewDrawer';

/** Teacher Studio hub & Test Bank: my tests (search, filter, duplicate, export, edit, assign, results) and essays waiting for review. */
export default function TeacherStudio() {
  const { t } = useLang();
  const { user } = useAuth();
  const [tests, setTests] = useState<StudioListItem[] | null>(null);
  const [essays, setEssays] = useState<TeacherEssayCard[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [assignFor, setAssignFor] = useState<StudioDetail | null>(null);
  const [reviewId, setReviewId] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [statusTab, setStatusTab] = useState<'all' | 'published' | 'draft'>('all');
  const [subjectFilter, setSubjectFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [busyId, setBusyId] = useState<number | null>(null);
  const reviewer = canReviewEssays(user);

  const loadTests = useCallback(() => {
    StudioApi.list({
      q: search.trim() || undefined,
      status: statusTab,
      subject: subjectFilter,
      category: categoryFilter,
    })
      .then(setTests)
      .catch((e) => setErr(e instanceof Error ? e.message : t('err_retry_js')));
  }, [search, statusTab, subjectFilter, categoryFilter, t]);

  const loadEssays = useCallback(() => {
    if (!reviewer) return;
    TeacherEssays.queue()
      .then((q) => setEssays([...q.student_requested, ...q.pending]))
      .catch(() => setEssays([]));
  }, [reviewer]);

  useEffect(() => {
    loadTests();
    loadEssays();
  }, [loadTests, loadEssays]);

  const openAssign = async (id: number) => {
    try {
      setAssignFor(await StudioApi.detail(id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : t('err_retry_js'));
    }
  };

  const handleDuplicate = async (id: number) => {
    setBusyId(id);
    setErr(null);
    try {
      await StudioApi.duplicate(id);
      setNotice(t('studio_duplicated', 'Test nusxasi yaratildi (Qoralama)'));
      loadTests();
    } catch (e) {
      setErr(e instanceof Error ? e.message : t('err_retry_js'));
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (id: number, title: string) => {
    if (!window.confirm(t('studio_delete_confirm', `"${title}" testini o'chirmoqchimisiz?`))) {
      return;
    }
    setBusyId(id);
    setErr(null);
    try {
      await StudioApi.delete(id);
      setNotice(t('studio_deleted', 'Test muvaffaqiyatli o‘chirildi'));
      loadTests();
    } catch (e) {
      const code = (e as { code?: string })?.code;
      if (code === 'has_attempts') {
        setErr(t('studio_err_has_attempts', 'Ushbu testni o‘chirib bo‘lmaydi: o‘quvchilar allaqachon topshirgan!'));
      } else {
        setErr(e instanceof Error ? e.message : t('err_retry_js'));
      }
    } finally {
      setBusyId(null);
    }
  };

  const totalCount = tests?.length ?? 0;
  const publishedCount = tests?.filter((t) => t.status === 'published').length ?? 0;
  const draftCount = tests?.filter((t) => t.status === 'draft').length ?? 0;

  return (
    <div className="studio-page">
      <header className="studio-hub__head">
        <div>
          <h1 className="studio-h1">{t('studio_title', 'Ustoz Test Banki & Studiyasi')}</h1>
          <p className="muted">{t('studio_subtitle', 'Savollar tuzing, import qiling, guruhga biriktiring va natijalarni tahlil qiling')}</p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Link to="/teacher/ai-converter" className="btn secondary">
            ✨ {t('studio_ai_btn', 'AI Konvertor')}
          </Link>
          <Link to="/teacher/studio/new" className="btn primary">
            <Plus size={16} aria-hidden="true" /> {t('studio_new_test')}
          </Link>
        </div>
      </header>

      {err && (
        <div className="studio-alert is-bad" role="alert">
          {err}
        </div>
      )}
      {notice && (
        <div className="studio-alert" style={{ background: 'var(--green-bg, #ecfdf5)', color: 'var(--green-text, #065f46)', border: '1px solid var(--green-border, #a7f3d0)' }} role="status">
          {notice}
        </div>
      )}

      {/* Test Bank Filter & Search Controls */}
      <section className="card studio-bank-bar" style={{ padding: '12px 16px', marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flex: 1, minWidth: 220 }}>
            <div style={{ position: 'relative', width: '100%', maxWidth: 360 }}>
              <Search size={15} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)' }} aria-hidden="true" />
              <input
                type="search"
                style={{ width: '100%', paddingLeft: 32, paddingRight: 10, height: 36, borderRadius: 6, border: '1px solid var(--border)' }}
                placeholder={t('studio_search_ph', 'Test nomi yoki kod bo‘yicha qidirish...')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select
              style={{ height: 36, borderRadius: 6, border: '1px solid var(--border)', padding: '0 8px', fontSize: '0.9rem' }}
              value={subjectFilter}
              onChange={(e) => setSubjectFilter(e.target.value)}
              aria-label={t('filter_by_subject', 'Fan bo‘yicha filter')}
            >
              <option value="all">{t('all_subjects', 'Barcha fanlar')}</option>
              {STUDIO_SUBJECTS.map((sub) => (
                <option key={sub} value={sub}>
                  {t(`studio_subject_${sub}`, sub)}
                </option>
              ))}
            </select>
            <select
              style={{ height: 36, borderRadius: 6, border: '1px solid var(--border)', padding: '0 8px', fontSize: '0.9rem' }}
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              aria-label={t('filter_by_category', 'Kategoriya bo‘yicha filter')}
            >
              <option value="all">{t('all_categories', 'Barcha kategoriyalar')}</option>
              {ASSESSMENT_CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {t(`studio_category_${cat}`, cat)}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              className={`btn sm ${statusTab === 'all' ? 'primary' : 'ghost'}`}
              onClick={() => setStatusTab('all')}
            >
              {t('all', 'Barchasi')} ({totalCount})
            </button>
            <button
              type="button"
              className={`btn sm ${statusTab === 'published' ? 'primary' : 'ghost'}`}
              onClick={() => setStatusTab('published')}
            >
              🟢 {t('studio_status_published', 'Nashr qilingan')} ({publishedCount})
            </button>
            <button
              type="button"
              className={`btn sm ${statusTab === 'draft' ? 'primary' : 'ghost'}`}
              onClick={() => setStatusTab('draft')}
            >
              📝 {t('studio_status_draft', 'Qoralama')} ({draftCount})
            </button>
          </div>
        </div>
      </section>

      <div className="studio-hub">
        <section className="card studio-hub__tests" aria-labelledby="studio-my-tests">
          <h2 id="studio-my-tests">{t('studio_my_tests', 'Mening testlarim')}</h2>
          {tests === null ? (
            <div className="studio-skeleton" role="status" aria-label={t('loading')} />
          ) : tests.length === 0 ? (
            <div className="studio-empty">
              <p>{t('studio_no_tests', 'Hozircha testlar mavjud emas')}</p>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
                <Link to="/teacher/ai-converter" className="btn primary sm">
                  ✨ AI Konvertor
                </Link>
                <Link to="/teacher/studio/new" className="btn secondary sm">
                  {t('studio_new_test')}
                </Link>
              </div>
            </div>
          ) : (
            <ul className="studio-list">
              {tests.map((test) => (
                <li key={test.id} className="studio-list__item" style={{ alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
                  <div className="studio-list__main" style={{ flex: '1 1 280px' }}>
                    <strong>{test.title}</strong>
                    <div className="muted small" style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4, alignItems: 'center' }}>
                      <span className={`studio-status is-${test.status}`}>{t(`studio_status_${test.status}`, test.status)}</span>
                      <span>·</span>
                      <span>{t(`studio_subject_${test.subject}`, test.subject)}</span>
                      {test.assessment_category && (
                        <>
                          <span>·</span>
                          <span style={{ background: 'var(--code-bg, #f3f4f6)', padding: '1px 6px', borderRadius: 4, fontSize: '0.8rem' }}>
                            {t(`studio_category_${test.assessment_category}`, test.assessment_category)}
                          </span>
                        </>
                      )}
                      {test.is_timed === false && (
                        <>
                          <span>·</span>
                          <span style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>{t('studio_time_untimed', 'Vaqt cheklovisiz')}</span>
                        </>
                      )}
                      <span>·</span>
                      <span>{t('studio_n_questions', '{n} ta savol').replace('{n}', String(test.questions))}</span>
                      <span>·</span>
                      <span>{t('studio_n_attempts', '{n} ta topshirish').replace('{n}', String(test.attempts))}</span>
                      {test.mock_code && (
                        <>
                          <span>·</span>
                          <code style={{ background: 'var(--code-bg, #f3f4f6)', padding: '2px 6px', borderRadius: 4 }}>{test.mock_code}</code>
                        </>
                      )}
                    </div>
                  </div>

                  <div className="studio-list__actions" style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {test.is_studio && test.attempts === 0 && (
                      <Link className="btn sm" to={`/teacher/studio/${test.id}/edit`}>
                        <PenLine size={14} aria-hidden="true" /> {t('studio_edit', 'Tahrirlash')}
                      </Link>
                    )}
                    {test.is_studio && test.attempts > 0 && (
                      <Link className="btn sm" to={`/teacher/studio/${test.id}/edit`}>
                        {t('studio_view', 'Ko‘rish')}
                      </Link>
                    )}
                    <button
                      type="button"
                      className="btn sm"
                      title={t('studio_duplicate', 'Nusxasini yaratish')}
                      disabled={busyId === test.id}
                      onClick={() => void handleDuplicate(test.id)}
                    >
                      <Copy size={14} aria-hidden="true" /> {t('studio_copy_btn', 'Nusxa')}
                    </button>
                    {test.status === 'published' && (
                      <button type="button" className="btn sm primary" onClick={() => void openAssign(test.id)}>
                        <Share2 size={14} aria-hidden="true" /> {t('studio_assign', 'Biriktirish')}
                      </button>
                    )}
                    <a
                      href={StudioApi.exportUrl(test.id)}
                      download={`test_${test.id}.csv`}
                      className="btn sm ghost"
                      title={t('studio_export_csv', 'CSV yuklab olish')}
                    >
                      <Download size={14} aria-hidden="true" /> CSV
                    </a>
                    <Link className="btn sm" to={`/teacher/studio/${test.id}/results`}>
                      <BarChart3 size={14} aria-hidden="true" /> {t('studio_results', 'Natijalar')}
                    </Link>
                    {test.attempts === 0 && (
                      <button
                        type="button"
                        className="btn sm is-danger"
                        disabled={busyId === test.id}
                        title={t('delete', 'O‘chirish')}
                        onClick={() => void handleDelete(test.id, test.title)}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {reviewer && (
          <section className="card studio-hub__essays" aria-labelledby="studio-essays-h">
            <h2 id="studio-essays-h">{t('studio_essays_waiting', 'Tekshirish kutilayotgan esselar')}</h2>
            {essays === null ? (
              <div className="studio-skeleton" role="status" aria-label={t('loading')} />
            ) : essays.length === 0 ? (
              <p className="muted">{t('tr_no_items', 'Esselar mavjud emas')}</p>
            ) : (
              <ul className="studio-list">
                {essays.slice(0, 12).map((e) => (
                  <li key={e.id} className="studio-list__item">
                    <div className="studio-list__main">
                      <strong>{e.student}</strong>
                      <span className="muted small">
                        {e.topic ?? '—'} · {t('tr_ai_score', 'AI ball')}: {e.total_score}/{e.max_score}
                        {e.teacher_review_requested && ` · ${t('tr_requested', 'O‘quvchi so‘ragan')}`}
                      </span>
                    </div>
                    <button type="button" className="btn sm primary" onClick={() => setReviewId(e.id)}>
                      {t('studio_quick_review', 'Tekshirish')}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <Link to="/teacher/essays" className="small">
              {t('view_all', 'Barchasini ko‘rish')} →
            </Link>
          </section>
        )}
      </div>

      {assignFor && (
        <AssignDialog
          testId={assignFor.test.id}
          testTitle={assignFor.test.title}
          links={assignFor.links}
          assignments={assignFor.assignments}
          onClose={() => setAssignFor(null)}
        />
      )}
      {reviewId !== null && (
        <EssayReviewDrawer submissionId={reviewId} onClose={() => setReviewId(null)} onSaved={() => loadEssays()} />
      )}
    </div>
  );
}
