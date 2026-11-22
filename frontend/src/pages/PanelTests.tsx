import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useLang } from '../i18n/LangContext';
import { Panel } from '../lib/api';

interface TestItem {
  id: number;
  title: string;
  description?: string;
  course_title?: string;
  subject?: string;
  difficulty?: string;
  status: string;
  is_active: boolean;
  q_count?: number;
  attempts_count?: number;
  assignments_count?: number;
  results_count?: number;
  creator_name?: string;
  created_at?: string;
  can_delete?: boolean;
  can_archive?: boolean;
}

interface TestStats {
  total_count: number;
  published_count: number;
  draft_count: number;
  archived_count: number;
  attempted_count: number;
}

interface BulkPreviewData {
  action: string;
  total_selected: number;
  drafts_count: number;
  published_count: number;
  archived_count: number;
  has_assignments_count: number;
  has_attempts_count: number;
  safe_to_delete_count: number;
  blocked_from_delete_count: number;
  retained_count: number;
  blocked_tests: {
    id: number;
    title: string;
    status: string;
    attempts_count: number;
    assignments_count: number;
    reason: string;
  }[];
}

export default function PanelTests() {
  const { t } = useLang();
  const [tests, setTests] = useState<TestItem[]>([]);
  const [statuses, setStatuses] = useState<{ value: string; label: string }[]>([]);
  const [stats, setStats] = useState<TestStats | null>(null);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [subject, setSubject] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);

  // Bulk preview modal state
  const [previewData, setPreviewData] = useState<BulkPreviewData | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [isProcessingBulk, setIsProcessingBulk] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Panel.tests({ q, status, subject, page, page_size: 25 })
      .then((r) => {
        setTests(r.results as unknown as TestItem[]);
        if (r.statuses) setStatuses(r.statuses);
        if (r.stats) setStats(r.stats);
        if (r.total !== undefined) setTotalCount(r.total);
        if (r.total_pages !== undefined) setTotalPages(r.total_pages);
        setErr(null);
      })
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : 'Yuklashda xatolik.'))
      .finally(() => setLoading(false));
  }, [q, status, subject, page]);

  useEffect(() => {
    const id = setTimeout(load, 250);
    return () => clearTimeout(id);
  }, [load]);

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === tests.length && tests.length > 0) {
      setSelectedIds([]);
    } else {
      setSelectedIds(tests.map((x) => x.id));
    }
  };

  const removeSingle = async (test: TestItem) => {
    const attempts = test.attempts_count || test.results_count || 0;
    const assignments = test.assignments_count || 0;

    if (attempts > 0 || assignments > 0 || test.status === 'published') {
      const msg = attempts > 0
        ? `Ushbu testda ${attempts} ta o'quvchi urinishi mavjud! Tarixiy natijalarni saqlash uchun testni o'chirish o'rniga arxivlang.`
        : assignments > 0
        ? `Ushbu test ${assignments} ta faol topshiriqqa biriktirilgan. Avval topshiriqlarni bekor qiling yoki testni arxivlang.`
        : `E'lon qilingan testni to'g'ridan-to'g'ri o'chirib bo'lmaydi. Uni arxivlash tavsiya etiladi.`;

      const shouldArchive = window.confirm(`${msg}\n\nTestni arxivga o'tkazishni xohlaysizmi?`);
      if (shouldArchive) {
        archiveSingle(test.id);
      }
      return;
    }

    if (!window.confirm(`"${test.title}" testini butunlay o'chirmoqchimisiz?`)) return;

    try {
      await Panel.deleteTest(test.id);
      setSuccessMsg('Test muvaffaqiyatli o\'chirildi.');
      load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'O\'chirishda xatolik yuz berdi.');
    }
  };

  const archiveSingle = async (id: number) => {
    try {
      await Panel.archiveTest(id);
      setSuccessMsg('Test arxivlandi.');
      load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Arxivlashda xatolik.');
    }
  };

  const restoreSingle = async (id: number) => {
    try {
      await Panel.restoreTest(id);
      setSuccessMsg('Test arxivdan qoralamaga qaytarildi.');
      load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Tiklashda xatolik.');
    }
  };

  const duplicateSingle = async (id: number) => {
    try {
      await Panel.duplicateTest(id);
      setSuccessMsg('Test nusxasi qoralama sifatida muvaffaqiyatli yaratildi.');
      load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Nusxa olishda xatolik.');
    }
  };

  const unpublishSingle = async (id: number) => {
    try {
      await Panel.unpublishTest(id);
      setSuccessMsg('Test e\'londan olindi (qoralamaga o\'tkazildi).');
      load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'E\'londan olishda xatolik.');
    }
  };

  // Request bulk action preview
  const requestBulkAction = async (action: string) => {
    if (selectedIds.length === 0) {
      alert('Iltimos, avval kamida bitta testni tanlang.');
      return;
    }

    if (action === 'export') {
      try {
        const res = await Panel.bulkActionTests(selectedIds, 'export_metadata');
        const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `tests-export-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        setSuccessMsg(`${selectedIds.length} ta test ma'lumoti JSON formatida yuklab olindi.`);
      } catch (e: unknown) {
        setErr(e instanceof Error ? e.message : 'Eksport qilishda xatolik.');
      }
      return;
    }

    try {
      const preview = await Panel.bulkPreviewTests(selectedIds, action);
      setPreviewData(preview);
      setPendingAction(action);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Amalni tekshirishda xatolik.');
    }
  };

  const confirmBulkAction = async () => {
    if (!pendingAction || selectedIds.length === 0) return;
    setIsProcessingBulk(true);
    try {
      const res = await Panel.bulkActionTests(selectedIds, pendingAction);
      setPreviewData(null);
      setPendingAction(null);
      setSelectedIds([]);

      if (pendingAction === 'delete' || pendingAction === 'delete_unused_drafts') {
        const del = (res as { deleted_count?: number }).deleted_count || 0;
        const blk = (res as { blocked_count?: number }).blocked_count || 0;
        setSuccessMsg(`Amal yakunlandi: ${del} ta bo'sh qoralama o'chirildi, ${blk} ta test himoyalandi va saqlab qolindi.`);
      } else {
        setSuccessMsg('Guruhli amal muvaffaqiyatli bajarildi.');
      }
      load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Amalni bajarishda xatolik.');
    } finally {
      setIsProcessingBulk(false);
    }
  };

  return (
    <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '16px' }}>
      {/* Title & Top Action */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 style={{ margin: '0 0 4px', fontSize: '24px', fontWeight: 800 }}>
            {t('panel_test_control_center')}
          </h1>
          <p className="muted small" style={{ margin: 0 }}>
            Testlarni xavfsiz boshqarish, tahlil qilish va guruhli boshqaruv
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <Link className="btn secondary sm" to="/teacher/ai-converter">
            ✨ AI Konvertor
          </Link>
          <Link className="btn primary sm" to="/panel/tests/new">
            + {t('panel_new_test')}
          </Link>
        </div>
      </div>

      {/* Metrics Summary Header */}
      {stats && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px',
          marginBottom: '20px'
        }}>
          <div className="card" style={{ padding: '14px', borderLeft: '4px solid #3b82f6' }}>
            <div className="muted small">{t('panel_total_tests')}</div>
            <div style={{ fontSize: '22px', fontWeight: 800, marginTop: '4px' }}>{stats.total_count}</div>
          </div>
          <div className="card" style={{ padding: '14px', borderLeft: '4px solid #10b981' }}>
            <div className="muted small">{t('panel_published_tests')}</div>
            <div style={{ fontSize: '22px', fontWeight: 800, color: '#10b981', marginTop: '4px' }}>{stats.published_count}</div>
          </div>
          <div className="card" style={{ padding: '14px', borderLeft: '4px solid #f59e0b' }}>
            <div className="muted small">{t('panel_draft_tests')}</div>
            <div style={{ fontSize: '22px', fontWeight: 800, color: '#f59e0b', marginTop: '4px' }}>{stats.draft_count}</div>
          </div>
          <div className="card" style={{ padding: '14px', borderLeft: '4px solid #6b7280' }}>
            <div className="muted small">{t('panel_archived_tests')}</div>
            <div style={{ fontSize: '22px', fontWeight: 800, color: '#6b7280', marginTop: '4px' }}>{stats.archived_count}</div>
          </div>
          <div className="card" style={{ padding: '14px', borderLeft: '4px solid #8b5cf6' }}>
            <div className="muted small">{t('panel_attempted_tests')}</div>
            <div style={{ fontSize: '22px', fontWeight: 800, color: '#8b5cf6', marginTop: '4px' }}>{stats.attempted_count}</div>
          </div>
        </div>
      )}

      {/* Notifications */}
      {err && (
        <div className="card" style={{ padding: '12px 16px', background: '#fee2e2', border: '1px solid #f87171', color: '#991b1b', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>⚠️ {err}</div>
          <button className="btn sm ghost" onClick={() => setErr(null)}>✕</button>
        </div>
      )}
      {successMsg && (
        <div className="card" style={{ padding: '12px 16px', background: '#ecfdf5', border: '1px solid #6ee7b7', color: '#065f46', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>✅ {successMsg}</div>
          <button className="btn sm ghost" onClick={() => setSuccessMsg(null)}>✕</button>
        </div>
      )}

      {/* Search and Filters Toolbar */}
      <div className="toolbar" style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' }}>
        <input
          style={{ flex: '1 1 220px' }}
          placeholder={t('panel_search_tests') || 'Nomi, tavsifi, muallif...'}
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }}
        />
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} style={{ minWidth: '150px' }}>
          <option value="">{t('all') || 'Barcha holatlar'}</option>
          {statuses.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <input
          style={{ width: '160px' }}
          placeholder="Fan (Subject)"
          value={subject}
          onChange={(e) => { setSubject(e.target.value); setPage(1); }}
        />
      </div>

      {/* Bulk Action Toolbar */}
      {selectedIds.length > 0 && (
        <div className="card" style={{
          padding: '12px 16px',
          background: '#f8fafc',
          border: '1px solid #cbd5e1',
          marginBottom: '16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '10px'
        }}>
          <div style={{ fontWeight: 600 }}>
            📌 {selectedIds.length} ta test tanlandi
            <button className="btn sm ghost" onClick={() => setSelectedIds([])} style={{ marginLeft: '10px' }}>
              Bekor qilish
            </button>
          </div>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            <button className="btn sm secondary" onClick={() => requestBulkAction('archive')}>
              📦 {t('panel_bulk_archive')}
            </button>
            <button className="btn sm secondary" onClick={() => requestBulkAction('restore')}>
              ↩️ {t('panel_bulk_restore')}
            </button>
            <button className="btn sm secondary" onClick={() => requestBulkAction('unpublish')}>
              📝 {t('panel_bulk_unpublish')}
            </button>
            <button className="btn sm secondary" onClick={() => requestBulkAction('export')}>
              📊 {t('panel_bulk_export')}
            </button>
            <button className="btn sm secondary" onClick={() => requestBulkAction('delete_unused_drafts')}>
              🧹 {t('panel_bulk_clean_drafts')}
            </button>
            <button className="btn sm danger" onClick={() => requestBulkAction('delete')}>
              🗑️ {t('panel_bulk_delete_safe')}
            </button>
          </div>
        </div>
      )}

      {/* Tests Table */}
      {tests.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '48px 20px' }}>
          <p style={{ fontSize: '18px', fontWeight: 700, margin: '0 0 8px' }}>
            {loading ? 'Yuklanmoqda...' : '✨ Testlar topilmadi'}
          </p>
          <p className="muted small" style={{ marginBottom: '20px' }}>
            Qidiruv mezonlarini o'zgartiring yoki yangi test qo'shing.
          </p>
          <div style={{ display: 'flex', gap: '10px', justifyContent: 'center' }}>
            <Link className="btn primary" to="/panel/tests/new">
              {t('panel_new_test')}
            </Link>
          </div>
        </div>
      ) : (
        <div className="table-wrap card" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                <th style={{ width: '40px', textAlign: 'center' }}>
                  <input
                    type="checkbox"
                    checked={selectedIds.length === tests.length && tests.length > 0}
                    onChange={toggleSelectAll}
                    aria-label="Select all"
                  />
                </th>
                <th>{t('th_test_name')}</th>
                <th>Fan</th>
                <th>Holat</th>
                <th style={{ textAlign: 'center' }}>Savollar</th>
                <th style={{ textAlign: 'center' }}>Urinishlar / Natijalar</th>
                <th>Muallif</th>
                <th style={{ textAlign: 'right' }}>Amallar</th>
              </tr>
            </thead>
            <tbody>
              {tests.map((x) => {
                const isSelected = selectedIds.includes(x.id);
                const statusBadge =
                  x.status === 'published' && x.is_active
                    ? { bg: '#ecfdf5', color: '#065f46', label: "E'lon qilingan" }
                    : x.status === 'draft'
                    ? { bg: '#fffbeb', color: '#92400e', label: 'Qoralama' }
                    : { bg: '#f3f4f6', color: '#4b5563', label: 'Arxivlangan' };

                return (
                  <tr
                    key={x.id}
                    style={{
                      background: isSelected ? '#f0f9ff' : 'transparent',
                      borderBottom: '1px solid #f1f5f9',
                    }}
                  >
                    <td style={{ textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelect(x.id)}
                        aria-label={`Select ${x.title}`}
                      />
                    </td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{x.title}</div>
                      {x.course_title && (
                        <div className="muted small" style={{ fontSize: '12px' }}>
                          Kurs: {x.course_title}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="badge" style={{ background: '#f1f5f9', color: '#334155' }}>
                        {x.subject || 'Umumiy'}
                      </span>
                    </td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          background: statusBadge.bg,
                          color: statusBadge.color,
                          fontWeight: 600,
                          padding: '3px 8px',
                          borderRadius: '12px',
                        }}
                      >
                        {statusBadge.label}
                      </span>
                    </td>
                    <td style={{ textAlign: 'center', fontWeight: 600 }}>
                      {x.q_count ?? 0}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <span
                        title={`${x.attempts_count ?? 0} ta urinish, ${x.assignments_count ?? 0} ta topshiriq`}
                        style={{
                          fontSize: '12px',
                          padding: '2px 6px',
                          borderRadius: '6px',
                          background: (x.attempts_count ?? 0) > 0 ? '#ede9fe' : '#f8fafc',
                          color: (x.attempts_count ?? 0) > 0 ? '#5b21b6' : '#64748b',
                        }}
                      >
                        👤 {x.attempts_count ?? 0} | 📋 {x.assignments_count ?? 0}
                      </span>
                    </td>
                    <td style={{ fontSize: '13px', color: '#475569' }}>
                      {x.creator_name || '—'}
                    </td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <div style={{ display: 'inline-flex', gap: '4px' }}>
                        <Link
                          className="btn sm ghost"
                          to={`/panel/tests/${x.id}/questions`}
                          title="Savollarni ko'rish va tahrirlash"
                        >
                          ❓ Savollar
                        </Link>
                        <Link
                          className="btn sm ghost"
                          to={`/panel/tests/${x.id}/edit`}
                          title="Tahrirlash"
                        >
                          ✏️
                        </Link>
                        <button
                          className="btn sm ghost"
                          onClick={() => duplicateSingle(x.id)}
                          title={t('panel_duplicate_test') || 'Nusxa olish'}
                        >
                          📋
                        </button>
                        {x.status === 'archived' ? (
                          <button
                            className="btn sm ghost"
                            onClick={() => restoreSingle(x.id)}
                            title={t('panel_restore_test') || 'Qoralamaga qaytarish'}
                          >
                            ↩️
                          </button>
                        ) : (
                          <button
                            className="btn sm ghost"
                            onClick={() => archiveSingle(x.id)}
                            title={t('panel_archive_test') || 'Arxivlash'}
                          >
                            📦
                          </button>
                        )}
                        {x.status === 'published' && (
                          <button
                            className="btn sm ghost"
                            onClick={() => unpublishSingle(x.id)}
                            title={t('panel_unpublish_test') || 'E\'londan olish'}
                          >
                            🚫
                          </button>
                        )}
                        <button
                          className="btn sm danger"
                          onClick={() => removeSingle(x)}
                          title="O'chirish"
                        >
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
          <div className="muted small">
            Jami: {totalCount} ta test | Sahifa {page} / {totalPages}
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="btn sm secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ← Oldingi
            </button>
            <button
              className="btn sm secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Keyingi →
            </button>
          </div>
        </div>
      )}

      {/* Safety Preview Modal */}
      {previewData && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: '16px'
        }}>
          <div className="card" style={{ maxWidth: '580px', width: '100%', padding: '24px', maxHeight: '90vh', overflowY: 'auto' }}>
            <h2 style={{ margin: '0 0 12px', fontSize: '20px', fontWeight: 800 }}>
              🛡️ {t('panel_preview_title')}
            </h2>
            <p className="muted small" style={{ marginBottom: '16px' }}>
              {t('panel_preview_notice')}
            </p>

            <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '8px', marginBottom: '16px', border: '1px solid #e2e8f0' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '14px' }}>
                <div>Tanlangan testlar:</div>
                <div style={{ fontWeight: 700 }}>{previewData.total_selected} ta</div>
                <div>Qoralamalar:</div>
                <div>{previewData.drafts_count} ta</div>
                <div>E'lon qilingan:</div>
                <div>{previewData.published_count} ta</div>
                <div>Topshiriqlari mavjud:</div>
                <div>{previewData.has_assignments_count} ta</div>
                <div>Urinishlar / Natijalar bor:</div>
                <div style={{ color: '#8b5cf6', fontWeight: 700 }}>{previewData.has_attempts_count} ta</div>
                <div style={{ borderTop: '1px solid #cbd5e1', paddingTop: '6px', fontWeight: 600 }}>
                  Xavfsiz o'chiriladi:
                </div>
                <div style={{ borderTop: '1px solid #cbd5e1', paddingTop: '6px', color: '#10b981', fontWeight: 800 }}>
                  {previewData.safe_to_delete_count} ta
                </div>
                <div style={{ fontWeight: 600 }}>Himoyalanadi / Saqlanadi:</div>
                <div style={{ color: '#ef4444', fontWeight: 800 }}>{previewData.retained_count} ta</div>
              </div>
            </div>

            {previewData.blocked_tests.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontWeight: 600, fontSize: '13px', marginBottom: '6px', color: '#991b1b' }}>
                  ⚠️ Quyidagi testlar natijalarni himoyalash uchun o'chirilmaydi:
                </div>
                <div style={{ maxHeight: '120px', overflowY: 'auto', background: '#fff1f2', padding: '8px', borderRadius: '6px', fontSize: '12px' }}>
                  {previewData.blocked_tests.map((b) => (
                    <div key={b.id} style={{ marginBottom: '4px' }}>
                      • <strong>{b.title}</strong> — {b.reason}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                className="btn secondary"
                onClick={() => { setPreviewData(null); setPendingAction(null); }}
                disabled={isProcessingBulk}
              >
                Bekor qilish
              </button>
              <button
                className="btn primary"
                onClick={confirmBulkAction}
                disabled={isProcessingBulk}
              >
                {isProcessingBulk ? 'Bajarilmoqda...' : 'Tasdiqlash va davom etish'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
