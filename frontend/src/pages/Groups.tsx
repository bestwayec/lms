import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Alert, Dropdown, Modal } from '../components/ui';
import { useLang } from '../i18n/LangContext';
import { School, WhiteLabelApi, ClassroomApi, api } from '../lib/api';
import { FolderOpenIcon, SettingsIcon, UsersIcon, XIcon } from '../components/icons';
import type {
  GroupMember,
  GroupMembershipHistoryItem,
  GroupStudentResults,
  SchoolGroup,
} from '../lib/school';
import {
  broadcastGroupVedomost,
  errMessage,
  getGroupMembershipHistory,
  getGroupStudentResults,
} from '../lib/school';

export default function Groups() {
  const activateQuota = async (groupId: number, studentId: number, planType: 'pro' | 'premium') => {
    setErr(null);
    setOk(null);
    try {
      const res = await api<{ status: string; message: string }>(
        `/api/v1/courses/groups/${groupId}/students/${studentId}/activate-quota/`,
        {
          method: 'POST',
          body: JSON.stringify({ plan_type: planType }),
        },
      );
      flash(res.message || 'Litsenziya muvaffaqiyatli faollashtirildi!');
    } catch (quotaErr: unknown) {
      setErr(errMessage(quotaErr));
    }
  };

  const { t } = useLang();
  const [groups, setGroups] = useState<SchoolGroup[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');

  // White-Label B2B Branding Modal State
  const [brandingOpen, setBrandingOpen] = useState(false);
  const [centerName, setCenterName] = useState('');
  const [headerTitle, setHeaderTitle] = useState('');
  const [brandColor, setBrandColor] = useState('#1e3a8a');
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [stampFile, setStampFile] = useState<File | null>(null);
  const [currentLogoUrl, setCurrentLogoUrl] = useState<string | null>(null);
  const [currentStampUrl, setCurrentStampUrl] = useState<string | null>(null);
  const [savingBranding, setSavingBranding] = useState(false);

  // Inline edit state (PATCH /api/v1/school/groups/<id>/).
  const [editing, setEditing] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');

  // Detail / members / history / analytics / attendance state.
  const [openGroup, setOpenGroup] = useState<number | null>(null);
  const [groupTabs, setGroupTabs] = useState<Record<number, 'members' | 'history' | 'analytics' | 'attendance'>>({});
  const [groupAttendance, setGroupAttendance] = useState<Record<string, 'present' | 'absent' | 'late' | 'excused'>>({});
  const [analyticsData, setAnalyticsData] = useState<Record<number, import('../lib/api').GroupFullAnalyticsResponse>>({});
  const [analyticsLoading, setAnalyticsLoading] = useState<number | null>(null);
  const [historyData, setHistoryData] = useState<Record<number, GroupMembershipHistoryItem[]>>({});
  const [historyLoading, setHistoryLoading] = useState<number | null>(null);
  const [studentResults, setStudentResults] = useState<GroupStudentResults | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [memberBusy, setMemberBusy] = useState(false);
  const searchVersion = useRef(0);
  const [search, setSearch] = useState('');
  const [found, setFound] = useState<GroupMember[]>([]);
  const [searching, setSearching] = useState(false);
  const [loadingGroups, setLoadingGroups] = useState(true);
  const searchTimer = useRef<number | null>(null);

  // Student join by invite code (optional secondary collapse for teachers/staff)
  const [joinCode, setJoinCode] = useState('');
  const [joinBusy, setJoinBusy] = useState(false);
  const [showJoinForm, setShowJoinForm] = useState(false);
  const [creatingGroup, setCreatingGroup] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [lifecycleBusyId, setLifecycleBusyId] = useState<number | null>(null);
  const [broadcastingId, setBroadcastingId] = useState<number | null>(null);

  const handleBroadcastVedomost = async (group: SchoolGroup) => {
    setBroadcastingId(group.id);
    setErr(null);
    setOk(null);
    try {
      const res = await broadcastGroupVedomost(group.id);
      flash(res?.message || res?.detail || `✅ "${group.name}" guruhining reytingi va PDF vedomosti Telegram guruhga yuborildi!`);
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    } finally {
      setBroadcastingId(null);
    }
  };

  const quickMarkStudent = async (
    groupId: number,
    studentId: number,
    status: 'present' | 'absent' | 'late' | 'excused',
    studentName: string,
  ) => {
    const key = `${groupId}_${studentId}`;
    setGroupAttendance((prev) => ({ ...prev, [key]: status }));
    try {
      const res = await School.attendanceQuickMark({
        group_id: groupId,
        student_id: studentId,
        status,
      });
      if (res.parent_alert_scheduled) {
        flash(`⚠️ ${studentName}: "Kelmadi" saqlandi. 15 daqiqadan so'ng ota-onaga Telegram orqali xabar boradi.`);
      } else {
        flash(`✓ ${studentName}: ${status === 'present' ? 'Keldi' : status === 'late' ? 'Kechikdi' : 'Sababli'} darhol saqlandi.`);
      }
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    }
  };

  const load = useCallback(async () => {
    try {
      // GET /api/v1/school/groups/
      const list = (await School.groups()) as unknown as SchoolGroup[];
      setGroups(list);
    } catch (e: unknown) {
      setErr(errMessage(e));
    } finally {
      setLoadingGroups(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    School.groups()
      .then((list) => { if (active) setGroups(list as unknown as SchoolGroup[]); })
      .catch((error: unknown) => { if (active) setErr(errMessage(error)); })
      .finally(() => { if (active) setLoadingGroups(false); });
    return () => { active = false; };
  }, []);

  useEffect(
    () => () => {
      if (searchTimer.current !== null) window.clearTimeout(searchTimer.current);
    },
    [],
  );

  const flash = (msg: string) => {
    setOk(msg);
    setErr(null);
  };

  const handleJoin = async (e: FormEvent) => {
    e.preventDefault();
    if (!joinCode.trim()) return;
    setJoinBusy(true);
    setErr(null);
    setOk(null);
    try {
      const res = await School.joinGroup(joinCode.trim());
      flash(res.message || 'Guruhga muvaffaqiyatli qo‘shildingiz!');
      setJoinCode('');
      await load();
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    } finally {
      setJoinBusy(false);
    }
  };

  const loadAnalytics = async (groupId: number) => {
    setAnalyticsLoading(groupId);
    try {
      const res = await School.groupAnalytics(groupId);
      setAnalyticsData((prev) => ({ ...prev, [groupId]: res }));
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    } finally {
      setAnalyticsLoading(null);
    }
  };

  const copyInviteLink = (group: SchoolGroup) => {
    const link = `https://grandec.uz/join/${group.invite_token || group.invite_code || group.id}`;
    void navigator.clipboard.writeText(link);
    flash(`Guruh taklif havolasi nusxalandi: ${link}`);
  };

  const shareToTelegram = (group: SchoolGroup) => {
    const link = `https://grandec.uz/join/${group.invite_token || group.invite_code || group.id}`;
    const text = `Assalomu alaykum! "${group.name}" guruhimizga qo'shiling va avtomatik ravishda 365 kunlik PRO tarifiga ega bo'ling: ${link}`;
    window.open(
      `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`,
      '_blank',
    );
  };

  const openBrandingModal = async () => {
    setBrandingOpen(true);
    try {
      const res = await WhiteLabelApi.get();
      setCenterName(res.center_name || '');
      setHeaderTitle(res.header_title || '');
      setBrandColor(res.brand_color || '#1e3a8a');
      setCurrentLogoUrl(res.center_logo_url || null);
      setCurrentStampUrl(res.stamp_signature_url || null);
    } catch {
      // fallback
    }
  };

  const saveBranding = async (e: FormEvent) => {
    e.preventDefault();
    setSavingBranding(true);
    try {
      const fd = new FormData();
      fd.append('center_name', centerName);
      fd.append('header_title', headerTitle);
      fd.append('brand_color', brandColor);
      if (logoFile) fd.append('center_logo', logoFile);
      if (stampFile) fd.append('stamp_signature', stampFile);
      const res = await WhiteLabelApi.update(fd);
      flash('Markaz brendi va hisobot sozlamalari muvaffaqiyatli saqlandi!');
      setCurrentLogoUrl(res.center_logo_url || null);
      setCurrentStampUrl(res.stamp_signature_url || null);
      setBrandingOpen(false);
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    } finally {
      setSavingBranding(false);
    }
  };

  // POST /api/v1/school/groups/ — parity with group_form.html create.
  const create = async (e: FormEvent) => {
    e.preventDefault();
    const cleanName = name.trim();
    if (!cleanName || creatingGroup) return;
    setCreatingGroup(true);
    setErr(null);
    setOk(null);
    try {
      const idemKey = `grp-${Date.now().toString(36)}-${cleanName.toLowerCase().slice(0, 24)}`;
      await School.createGroup({ name: cleanName, description: desc.trim() }, idemKey);
      setName('');
      setDesc('');
      flash(t('gf_created'));
      await load();
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    } finally {
      setCreatingGroup(false);
    }
  };

  const startEdit = (g: SchoolGroup) => {
    setOpenGroup(null);
    setEditing(g.id);
    setEditName(g.name);
    setEditDesc(g.description ?? '');
  };

  // PATCH /api/v1/school/groups/<id>/ — parity with group_form.html edit.
  const saveEdit = async (e: FormEvent) => {
    e.preventDefault();
    if (editing === null || savingEdit || !editName.trim()) return;
    setSavingEdit(true);
    try {
      await School.updateGroup(editing, { name: editName.trim(), description: editDesc.trim() });
      setEditing(null);
      flash(t('grp_updated'));
      await load();
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    } finally {
      setSavingEdit(false);
    }
  };

  const [depGroup, setDepGroup] = useState<SchoolGroup | null>(null);
  const [depData, setDepData] = useState<{
    can_delete: boolean;
    reasons: string[];
    dependencies: {
      students_count: number;
      homeworks_count: number;
      homework_submissions_count: number;
      attendance_sessions_count: number;
      essay_assignments_count: number;
      academic_records_count: number;
    };
  } | null>(null);
  const [depLoading, setDepLoading] = useState(false);

  const checkDependencies = async (g: SchoolGroup) => {
    setDepGroup(g);
    setDepLoading(true);
    setDepData(null);
    try {
      const res = await ClassroomApi.groupDependencies(g.id);
      setDepData(res);
    } catch (e: unknown) {
      setErr(errMessage(e));
      setDepGroup(null);
    } finally {
      setDepLoading(false);
    }
  };

  const handleArchive = async (id: number) => {
    if (lifecycleBusyId === id) return;
    setLifecycleBusyId(id);
    try {
      const res = await ClassroomApi.archiveGroup(id);
      flash(res?.message || 'Guruh muvaffaqiyatli arxivlandi!');
      setDepGroup(null);
      await load();
    } catch (e: unknown) {
      setErr(errMessage(e));
    } finally {
      setLifecycleBusyId(null);
    }
  };

  const handleRestore = async (id: number) => {
    if (lifecycleBusyId === id) return;
    setLifecycleBusyId(id);
    try {
      const res = await ClassroomApi.restoreGroup(id);
      flash(res?.message || 'Guruh qayta faollashtirildi!');
      await load();
    } catch (e: unknown) {
      setErr(errMessage(e));
    } finally {
      setLifecycleBusyId(null);
    }
  };

  const handleSafeDelete = async (id: number) => {
    if (lifecycleBusyId === id) return;
    if (!window.confirm("Haqiqatan ham ushbu guruhni butunlay o'chirmoqchimisiz?")) return;
    setLifecycleBusyId(id);
    try {
      const res = await ClassroomApi.deleteGroup(id);
      flash(res?.message || "Guruh muvaffaqiyatli o'chirildi.");
      setDepGroup(null);
      if (openGroup === id) setOpenGroup(null);
      await load();
    } catch (e: unknown) {
      setErr(errMessage(e));
    } finally {
      setLifecycleBusyId(null);
    }
  };

  const loadHistory = async (groupId: number) => {
    setHistoryLoading(groupId);
    try {
      const items = await getGroupMembershipHistory(groupId);
      setHistoryData((prev) => ({ ...prev, [groupId]: items }));
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    } finally {
      setHistoryLoading(null);
    }
  };

  const openStudentResults = async (groupId: number, studentId: number) => {
    setResultsLoading(true);
    setStudentResults(null);
    try {
      const data = await getGroupStudentResults(groupId, studentId);
      setStudentResults(data);
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    } finally {
      setResultsLoading(false);
    }
  };

  // GET /api/v1/school/students/?q=&group_id= — debounced member search.
  const onSearch = (groupId: number, qq: string) => {
    setSearch(qq);
    if (searchTimer.current !== null) window.clearTimeout(searchTimer.current);
    const version = ++searchVersion.current;
    if (qq.trim().length < 2) {
      setFound([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    searchTimer.current = window.setTimeout(async () => {
      try {
        const res = (await School.studentSearch(qq.trim(), groupId)) as unknown as GroupMember[];
        if (version === searchVersion.current) setFound(res);
      } catch (e2: unknown) {
        if (version === searchVersion.current) setErr(errMessage(e2));
      } finally {
        if (version === searchVersion.current) setSearching(false);
      }
    }, 300);
  };

  // POST /api/v1/school/groups/<id>/members/ {add, remove}.
  const addMember = async (groupId: number, userId: number) => {
    setMemberBusy(true);
    try {
      const fresh = (await School.members(groupId, { add: [userId] })) as unknown as SchoolGroup;
      setGroups((prev) => prev.map((g) => (g.id === groupId ? fresh : g)));
      setHistoryData((prev) => {
        const next = { ...prev };
        delete next[groupId];
        return next;
      });
      setAnalyticsData((prev) => {
        const next = { ...prev };
        delete next[groupId];
        return next;
      });
      setFound((prev) => prev.filter((s) => s.id !== userId));
      flash(t('grp_member_added'));
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    } finally {
      setMemberBusy(false);
    }
  };

  const removeMember = async (groupId: number, student: GroupMember) => {
    const studentLabel = student.full_name || student.email;
    if (!window.confirm(`${studentLabel}: ${t('grp_confirm_remove')}`)) return;
    setMemberBusy(true);
    try {
      const fresh = (await School.members(groupId, { remove: [student.id] })) as unknown as SchoolGroup;
      setGroups((prev) => prev.map((g) => (g.id === groupId ? fresh : g)));
      setHistoryData((prev) => {
        const next = { ...prev };
        delete next[groupId];
        return next;
      });
      setAnalyticsData((prev) => {
        const next = { ...prev };
        delete next[groupId];
        return next;
      });
      if (studentResults && studentResults.student.id === student.id) {
        setStudentResults(null);
      }
      flash(t('grp_member_removed'));
    } catch (e2: unknown) {
      setErr(errMessage(e2));
    } finally {
      setMemberBusy(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 8 }}>
        <div>
          <h1 style={{ margin: 0 }}>
            <FolderOpenIcon size={24} className="ico" /> {t('groups')}
          </h1>
          <p className="muted small" style={{ margin: '4px 0 0' }}>{t('td_groups_hint')}</p>
        </div>
        <button
          type="button"
          onClick={openBrandingModal}
          className="btn sm"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            background: 'var(--info-bg)',
            borderColor: 'var(--info-border)',
            color: 'var(--info-text)',
            fontWeight: 600,
          }}
        >
          <SettingsIcon size={14} />
          <span>🎨 Markaz brendi & muhri (White-Label)</span>
        </button>
        <button
          type="button"
          onClick={() => setShowJoinForm((prev) => !prev)}
          className="btn sm ghost"
        >
          {showJoinForm ? '✕ Kod shaklini yopish' : '🎯 Kod bilan guruhga kirish'}
        </button>
      </div>

      {err && (
        <div style={{ marginBottom: 14 }}>
          <Alert tone="danger" onClose={() => setErr(null)}>
            {err}
          </Alert>
        </div>
      )}
      {ok && (
        <div style={{ marginBottom: 14 }}>
          <Alert tone="success" onClose={() => setOk(null)}>
            {ok}
          </Alert>
        </div>
      )}

      {/* Primary Group Create + Optional Join Code Form */}
      <div style={{ display: 'grid', gridTemplateColumns: showJoinForm ? 'repeat(auto-fit, minmax(min(320px, 100%), 1fr))' : '1fr', gap: 16 }}>
        <form onSubmit={create} className="card form" style={{ maxWidth: '100%', margin: 0 }}>
          <h2>{t('gf_new_short')}</h2>
          <div className="row">
            <label>
              {t('gf_name_label')}
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('gf_name_ph')}
                required
                disabled={creatingGroup}
              />
            </label>
            <label>
              {t('gf_desc_label')}
              <input
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder={t('gf_desc_ph')}
                disabled={creatingGroup}
              />
            </label>
          </div>
          <button
            type="submit"
            className="btn primary sm"
            disabled={creatingGroup || !name.trim()}
            style={{ alignSelf: 'flex-start' }}
          >
            {creatingGroup ? 'Yaratilmoqda…' : t('gf_create')}
          </button>
        </form>

        {showJoinForm && (
          <form onSubmit={handleJoin} className="card form" style={{ maxWidth: '100%', margin: 0 }}>
            <h2>🎯 Guruhga Taklif Kodi Orqali Qo‘shilish</h2>
            <p className="muted small">Hamkasb ustoz taqdim etgan unikal guruh kodi (#GR-...) orqali guruhga qo‘shiling:</p>
            <div className="row">
              <label style={{ flex: 1 }}>
                Taklif kodi:
                <input
                  value={joinCode}
                  onChange={(e) => setJoinCode(e.target.value)}
                  placeholder="#GR-104 yoki GR-104"
                  required
                  disabled={joinBusy}
                />
              </label>
            </div>
            <button type="submit" className="btn primary sm" disabled={joinBusy || !joinCode.trim()} style={{ alignSelf: 'flex-start' }}>
              {joinBusy ? 'Qo‘shilmoqda…' : '🚀 Guruhga qo‘shilish'}
            </button>
          </form>
        )}
      </div>

      {/* List — parity with group_list.html cards + empty state. */}
      {loadingGroups ? (
        <p className="muted" role="status" aria-live="polite">{t('loading')}</p>
      ) : groups.length === 0 ? (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>{t('td_no_groups')}</h3>
          <p className="muted">{t('td_no_groups_hint')}</p>
        </div>
      ) : (
        <div className="grid" style={{ marginTop: 16 }}>
          {groups.map((g) => {
            const students = g.students ?? [];
            const open = openGroup === g.id;
            const isEditing = editing === g.id;
            const isLifecycleBusy = lifecycleBusyId === g.id;
            const tab = groupTabs[g.id] ?? 'analytics';
            const analytics = analyticsData[g.id];
            const isLoadingAnalytics = analyticsLoading === g.id;

            return (
              <div key={g.id} className="card">
                {isEditing ? (
                  <form onSubmit={saveEdit} className="form">
                    <label>
                      {t('gf_name_label')}
                      <input value={editName} onChange={(e) => setEditName(e.target.value)} required disabled={savingEdit} />
                    </label>
                    <label>
                      {t('gf_desc_label')}
                      <input value={editDesc} onChange={(e) => setEditDesc(e.target.value)} disabled={savingEdit} />
                    </label>
                    <div className="row">
                      <button type="submit" className="btn primary sm" disabled={savingEdit || !editName.trim()}>
                        {savingEdit ? 'Saqlanmoqda…' : t('save')}
                      </button>
                      <button type="button" className="btn sm ghost" onClick={() => setEditing(null)}>
                        {t('cancel')}
                      </button>
                    </div>
                  </form>
                ) : (
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', minWidth: 0 }}>
                        <strong style={{ fontSize: '1.05rem' }}>{g.name}</strong>
                        {g.status === 'archived' && (
                          <span className="badge" style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
                            Arxivlangan
                          </span>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        {g.telegram_chat_id ? (
                          <span
                            style={{
                              padding: '3px 10px',
                              borderRadius: 999,
                              background: 'var(--success-bg)',
                              color: 'var(--success-text)',
                              fontWeight: 700,
                              fontSize: '0.75rem',
                              border: '1px solid var(--success-border)',
                            }}
                          >
                            ✅ Telegram: {g.telegram_chat_title || g.telegram_chat_id}
                          </span>
                        ) : (
                          <span
                            style={{
                              padding: '3px 10px',
                              borderRadius: 999,
                              background: 'var(--warning-bg)',
                              color: 'var(--warning-text)',
                              fontWeight: 700,
                              fontSize: '0.75rem',
                              border: '1px solid var(--warning-border)',
                            }}
                          >
                            ⚠️ Telegram ulanmagan
                          </span>
                        )}
                        {g.invite_code && (
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: 6,
                              background: 'var(--info-bg)',
                              color: 'var(--info-text)',
                              fontWeight: 700,
                              fontSize: '0.78rem',
                              border: '1px solid var(--info-border)',
                            }}
                          >
                            #{g.invite_code}
                          </span>
                        )}
                      </div>
                    </div>
                    <p className="muted small">
                      <UsersIcon size={12} className="ico" /> {g.student_count ?? students.length} {t('an_talaba_full')}
                      {g.teacher_name ? ` · ${g.teacher_name}` : ''}
                    </p>
                    {g.description ? <p className="muted small">{g.description}</p> : null}
                    <div style={{display:'flex', marginLeft:'-8px'}} className="muted small" aria-hidden>
                      {students.slice(0, 5).map((s) => (
                        <span key={s.id} title={s.full_name} style={{marginLeft:'8px'}}>
                          {(s.first_name || s.full_name || '?').slice(0, 1)}·
                        </span>
                      ))}
                    </div>

                    {/* Telegram 1-Click Link, Manual Fallback & Broadcast Vedomost Box */}
                    {(() => {
                      const code = g.invite_code || g.group_code || String(g.id);
                      const studentJoinLink = `https://grandec.uz/join/${code}`;
                      const manualCmd = `/ulash ${code}`;
                      const isBroadcasting = broadcastingId === g.id;
                      const isTgConnected = Boolean(g.telegram_chat_id);
                      return (
                        <div
                          style={{
                            marginTop: 12,
                            padding: '12px 14px',
                            borderRadius: 12,
                            background: 'var(--bg-elevated)',
                            border: '1px solid var(--border-subtle)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 10,
                          }}
                        >
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                            <a
                              href={`https://t.me/uz_essaygrader_bot?startgroup=link_${encodeURIComponent(code)}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn sm"
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 6,
                                padding: '6px 12px',
                                borderRadius: 10,
                                fontWeight: 700,
                                fontSize: '0.8rem',
                                background: 'var(--brand-telegram)',
                                color: '#FFFFFF',
                                border: 'none',
                                textDecoration: 'none',
                              }}
                            >
                              {isTgConnected ? '🔄 Telegram guruhni almashtirish' : '📲 Telegram guruhga 1-klikda ulash'}
                            </a>

                            <button
                              type="button"
                              className="btn sm"
                              disabled={isBroadcasting || !isTgConnected}
                              title={!isTgConnected ? 'Avval Telegram guruhni ulab oling' : undefined}
                              onClick={() => void handleBroadcastVedomost(g)}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 6,
                                padding: '6px 12px',
                                borderRadius: 10,
                                fontWeight: 700,
                                fontSize: '0.8rem',
                                background: isTgConnected ? 'var(--brand-primary)' : 'var(--disabled-bg)',
                                color: isTgConnected ? '#FFFFFF' : 'var(--disabled-text)',
                                border: 'none',
                                cursor: isBroadcasting || !isTgConnected ? 'not-allowed' : 'pointer',
                                opacity: isBroadcasting ? 0.7 : 1,
                              }}
                            >
                              {isBroadcasting
                                ? '⏳ Yuborilmoqda...'
                                : isTgConnected
                                ? '📤 Reyting va Vedomostni yuborish'
                                : '📤 Vedomost (Telegram ulangan emas)'}
                            </button>
                          </div>

                          <div
                            style={{
                              display: 'flex',
                              flexWrap: 'wrap',
                              gap: '6px 14px',
                              alignItems: 'center',
                              fontSize: '0.76rem',
                              color: 'var(--text-secondary)',
                            }}
                          >
                            <span
                              style={{ cursor: 'pointer' }}
                              title="Nusxalash uchun bosing"
                              onClick={() => {
                                void navigator.clipboard.writeText(manualCmd);
                                flash(`Komanda nusxalandi: ${manualCmd}`);
                              }}
                            >
                              Qo&apos;lda ulash: guruhda{' '}
                              <code
                                style={{
                                  padding: '2px 6px',
                                  borderRadius: 6,
                                  background: 'var(--bg-surface)',
                                  border: '1px solid var(--border-subtle)',
                                  color: 'var(--text-primary)',
                                  fontWeight: 700,
                                }}
                              >
                                {manualCmd}
                              </code>{' '}
                              deb yozing 📋
                            </span>
                            <span
                              style={{ cursor: 'pointer' }}
                              title="Havolani nusxalash uchun bosing"
                              onClick={() => {
                                void navigator.clipboard.writeText(studentJoinLink);
                                flash(`O'quvchilar havolasi nusxalandi: ${studentJoinLink}`);
                              }}
                            >
                              O&apos;quvchi havolasi:{' '}
                              <strong style={{ color: 'var(--brand-primary)', textDecoration: 'underline' }}>
                                {studentJoinLink}
                              </strong>
                            </span>
                          </div>
                        </div>
                      );
                    })()}
                    <div className="row" style={{ marginTop: 12, justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <button
                          type="button"
                          className="btn sm secondary"
                          onClick={() => {
                            setEditing(null);
                            const nextOpen = open ? null : g.id;
                            setOpenGroup(nextOpen);
                            if (nextOpen && !analyticsData[g.id]) {
                              void loadAnalytics(g.id);
                            }
                          }}
                        >
                          {open ? t('back') : 'Tahlil va A‘zolar'}
                        </button>
                        <button
                          type="button"
                          className="btn sm ghost"
                          disabled={isLifecycleBusy}
                          onClick={() => startEdit(g)}
                        >
                          {t('edit')}
                        </button>
                      </div>

                      <Dropdown
                        trigger={
                          <span className="btn sm ghost" aria-label={`${g.name} qo'shimcha amallari`}>
                            ⋯ Boshqa
                          </span>
                        }
                        items={[
                          {
                            id: 'copy-link',
                            label: '📋 Taklif havolasini nusxalash',
                            onClick: () => copyInviteLink(g),
                          },
                          {
                            id: 'share-tg',
                            label: '✈️ Telegramda ulashish',
                            onClick: () => shareToTelegram(g),
                          },
                          g.status === 'archived'
                            ? {
                                id: 'restore',
                                label: '♻️ Guruhni faollashtirish',
                                disabled: isLifecycleBusy,
                                onClick: () => void handleRestore(g.id),
                              }
                            : {
                                id: 'archive',
                                label: '📦 Guruhni arxivlash',
                                disabled: isLifecycleBusy,
                                onClick: () => void handleArchive(g.id),
                              },
                          {
                            id: 'delete',
                            label: `🗑️ ${t('delete')}`,
                            danger: true,
                            disabled: isLifecycleBusy,
                            onClick: () => void checkDependencies(g),
                          },
                        ]}
                      />
                    </div>
                  </>
                )}

                {/* Detail — Tabs for Members, History, Attendance and Analytics */}
                {open && !isEditing && (
                  <div style={{ marginTop: 14, borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: 12 }}>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className={`btn sm ${tab === 'members' ? 'primary' : 'ghost'}`}
                        onClick={() => setGroupTabs((prev) => ({ ...prev, [g.id]: 'members' }))}
                      >
                        👥 {t('grp_members')} ({students.length})
                      </button>
                      <button
                        type="button"
                        className={`btn sm ${tab === 'history' ? 'primary' : 'ghost'}`}
                        onClick={() => {
                          setGroupTabs((prev) => ({ ...prev, [g.id]: 'history' }));
                          if (!historyData[g.id]) void loadHistory(g.id);
                        }}
                      >
                        📜 {t('grp_history')}
                      </button>
                      <button
                        type="button"
                        className={`btn sm ${tab === 'attendance' ? 'primary' : 'ghost'}`}
                        onClick={() => setGroupTabs((prev) => ({ ...prev, [g.id]: 'attendance' }))}
                      >
                        📅 1-Click Davomat
                      </button>
                      <button
                        type="button"
                        className={`btn sm ${tab === 'analytics' ? 'primary' : 'ghost'}`}
                        onClick={() => {
                          setGroupTabs((prev) => ({ ...prev, [g.id]: 'analytics' }));
                          if (!analyticsData[g.id]) void loadAnalytics(g.id);
                        }}
                      >
                        📊 Monitoring & BMB
                      </button>
                    </div>

                    {tab === 'analytics' && (
                      <div>
                        {isLoadingAnalytics && <p className="muted small">Guruh tahlili yuklanmoqda…</p>}
                        {analytics && (
                          <div style={{ display: 'grid', gap: 12 }}>
                            {/* Export actions */}
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                              <a
                                href={School.exportExcelUrl(g.id)}
                                target="_blank"
                                rel="noreferrer"
                                className="btn sm"
                                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, borderColor: '#10b981', color: '#10b981' }}
                              >
                                <span>📥</span> Excel (.xlsx)
                              </a>
                              <a
                                href={ClassroomApi.exportGroupReportUrl(g.id)}
                                target="_blank"
                                rel="noreferrer"
                                className="btn sm"
                                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, borderColor: '#38bdf8', color: '#38bdf8' }}
                              >
                                <span>📊</span> {t('grp_export_csv')}
                              </a>
                              <a
                                href={School.exportPdfUrl(g.id)}
                                target="_blank"
                                rel="noreferrer"
                                className="btn sm"
                                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, borderColor: '#ef4444', color: '#ef4444' }}
                              >
                                <span>📄</span> PDF Hisobot
                              </a>
                              <a
                                href={WhiteLabelApi.monthlyReportPdfUrl(g.id)}
                                target="_blank"
                                rel="noreferrer"
                                className="btn sm"
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: 6,
                                  background: 'rgba(99, 102, 241, 0.15)',
                                  borderColor: '#6366f1',
                                  color: '#818cf8',
                                  fontWeight: 600,
                                }}
                              >
                                <span>📑</span> Oylik A4 Hisobot (White-Label)
                              </a>
                            </div>

                            {/* Summary stats */}
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8 }}>
                              <div style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '8px 10px', borderRadius: '6px' }}>
                                <span className="muted small">Testlar:</span>
                                <strong style={{ display: 'block', fontSize: '1.05rem' }}>{analytics.summary.total_tests_taken}</strong>
                              </div>
                              <div style={{ background: 'var(--bg-elevated)', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                <span className="muted small">Esselar:</span>
                                <strong style={{ display: 'block', fontSize: '1.05rem' }}>{analytics.summary.total_essays_submitted}</strong>
                              </div>
                              <div style={{ background: 'var(--bg-elevated)', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                <span className="muted small">O‘rtacha Test:</span>
                                <strong style={{ display: 'block', fontSize: '1.05rem', color: 'var(--success-text)' }}>{analytics.summary.average_test_percentage}%</strong>
                              </div>
                              <div style={{ background: 'var(--bg-elevated)', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                <span className="muted small">O‘rtacha Esse:</span>
                                <strong style={{ display: 'block', fontSize: '1.05rem', color: 'var(--warning-text)' }}>{analytics.summary.average_essay_score} / 20</strong>
                              </div>
                              {analytics.assignments_summary && (
                                <div style={{ background: 'var(--bg-elevated)', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                  <span className="muted small">{t('grp_hw_completion')}:</span>
                                  <strong style={{ display: 'block', fontSize: '1.05rem', color: 'var(--info-text)' }}>
                                    {analytics.assignments_summary.completion_rate !== null
                                      ? `${analytics.assignments_summary.completion_rate}%`
                                      : '—'}
                                  </strong>
                                  {analytics.assignments_summary.overdue_count > 0 && (
                                    <span className="muted small" style={{ color: 'var(--danger-text)', fontSize: '0.72rem' }}>
                                      {t('grp_overdue')}: {analytics.assignments_summary.overdue_count}
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>

                            {analytics.weak_tests && analytics.weak_tests.length > 0 && (
                              <div>
                                <span className="muted small" style={{ fontWeight: 600 }}>{t('grp_weak_tests')}:</span>
                                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                                  {analytics.weak_tests.map((wt) => (
                                    <span
                                      key={wt.test_id}
                                      style={{
                                        padding: '3px 8px',
                                        borderRadius: '4px',
                                        fontSize: '0.76rem',
                                        background: 'var(--danger-bg)',
                                        color: 'var(--danger-text)',
                                      }}
                                    >
                                      {wt.test_title} — {wt.avg_percentage}% ({wt.attempts})
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {analytics.essay_insights && analytics.essay_insights.criterion_averages.length > 0 && (
                              <div>
                                <span className="muted small" style={{ fontWeight: 600 }}>{t('grp_essay_criteria_avg')}:</span>
                                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                                  {analytics.essay_insights.criterion_averages.slice(0, 4).map((cr) => (
                                    <span
                                      key={cr.criterion_id}
                                      style={{
                                        padding: '3px 8px',
                                        borderRadius: '4px',
                                        fontSize: '0.74rem',
                                        background: 'var(--warning-bg)',
                                        color: 'var(--warning-text)',
                                      }}
                                    >
                                      #{cr.criterion_id}: {cr.avg_score} ({cr.samples})
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* BMB distribution */}
                            <div>
                              <span className="muted small" style={{ fontWeight: 600 }}>BMB Sertifikat Taqsimoti:</span>
                              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                                {Object.entries(analytics.summary.bmb_distribution).map(([gr, cnt]) => (
                                  <span
                                    key={gr}
                                    style={{
                                      padding: '2px 8px',
                                      borderRadius: '4px',
                                      fontSize: '0.78rem',
                                      fontWeight: 700,
                                      background: gr.startsWith('A') ? 'rgba(16, 185, 129, 0.15)' : gr.startsWith('B') ? 'rgba(59, 130, 246, 0.15)' : gr.startsWith('C') ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                                      color: gr.startsWith('A') ? '#10b981' : gr.startsWith('B') ? '#3b82f6' : gr.startsWith('C') ? '#f59e0b' : '#ef4444',
                                    }}
                                  >
                                    {gr}: {cnt} ta
                                  </span>
                                ))}
                              </div>
                            </div>

                            {/* Student monitoring list */}
                            {analytics.students.length > 0 && (
                              <div style={{ overflowX: 'auto', marginTop: 4 }}>
                                <table className="data" style={{ fontSize: '0.82rem' }}>
                                  <thead>
                                    <tr>
                                      <th>Talaba</th>
                                      <th>Tarif</th>
                                      <th>To‘lov</th>
                                      <th>Testlar</th>
                                      <th>O‘rtacha</th>
                                      <th>BMB</th>
                                      <th>Esselar</th>
                                      <th>Oxirgi faollik</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {analytics.students.map((st) => (
                                      <tr key={st.student_id}>
                                        <td><strong>{st.student_name}</strong></td>
                                        <td><span className="badge green" style={{ fontWeight: 600 }}>⭐ PRO (Faol)</span></td>
                                        <td>
                                          <span className={`badge ${st.tuition_status === 'paid' ? 'green' : st.tuition_status === 'overdue' ? 'rose' : 'amber'}`}>
                                            {st.tuition_label || 'Kutilmoqda'}
                                          </span>
                                        </td>
                                        <td>{st.tests_count}</td>
                                        <td>{st.avg_test_percentage}%</td>
                                        <td>
                                          <span className={`badge ${st.latest_test_grade.startsWith('A') ? 'green' : st.latest_test_grade.startsWith('B') ? 'blue' : 'rose'}`}>
                                            {st.latest_test_grade}
                                          </span>
                                        </td>
                                        <td>{st.essays_count} ta ({st.avg_essay_score} b.)</td>
                                        <td className="muted small">{st.last_active ? new Date(st.last_active).toLocaleDateString() : '—'}</td>
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

                    {tab === 'members' && (
                      <>
                        <h4 style={{ margin: '8px 0' }}>
                          {t('grp_members')} ({students.length})
                        </h4>
                        <ul className="muted small">
                          {students.map((s) => (
                            <li key={s.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-subtle)', flexWrap: 'wrap', gap: 6 }}>
                              <div>
                                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{s.full_name}</span>{' '}
                                <span className="muted" style={{ fontSize: '0.8rem' }}>({s.email})</span>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                <button
                                  type="button"
                                  className="btn sm ghost"
                                  style={{ padding: '2px 8px', fontSize: '0.75rem' }}
                                  onClick={() => void openStudentResults(g.id, s.id)}
                                  title="Guruh testlari natijalarini ko'rish"
                                >
                                  {t('grp_results')}
                                </button>
                                <button
                                  type="button"
                                  className="btn sm"
                                  style={{ padding: '2px 8px', fontSize: '0.75rem', borderColor: '#f59e0b', color: '#f59e0b' }}
                                  onClick={() => activateQuota(g.id, s.id, 'pro')}
                                  title="Ustoz kvotasidan 30 kunlik PRO berish"
                                >
                                  ⚡ PRO
                                </button>
                                <button
                                  type="button"
                                  className="btn sm"
                                  style={{ padding: '2px 8px', fontSize: '0.75rem', borderColor: '#a855f7', color: '#a855f7' }}
                                  onClick={() => activateQuota(g.id, s.id, 'premium')}
                                  title="Ustoz kvotasidan 30 kunlik PREMIUM berish"
                                >
                                  👑 VIP
                                </button>
                                <button
                                  className="btn sm ghost"
                                  style={{ marginLeft: 4 }}
                                  disabled={memberBusy}
                                  onClick={() => removeMember(g.id, s)}
                                  aria-label={`${t('delete')} ${s.full_name}`}
                                >
                                  <XIcon size={13} />
                                </button>
                              </div>
                            </li>
                          ))}
                          {students.length === 0 && <li>{t('gf_no_students')}</li>}
                        </ul>

                        {resultsLoading && <p className="muted small" role="status">{t('loading')}…</p>}
                        {studentResults && (
                          <div className="card" style={{ padding: 12, margin: '12px 0', background: 'var(--bg-elevated)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                              <strong style={{ fontSize: '0.9rem' }}>{studentResults.student.name} — {t('grp_results')}</strong>
                              <button type="button" className="btn sm ghost" onClick={() => setStudentResults(null)}>✕</button>
                            </div>
                            {studentResults.results.length === 0 ? (
                              <p className="muted small">{t('grp_no_results_assigned')}</p>
                            ) : (
                              <ul className="muted small" style={{ margin: 0, paddingLeft: 16 }}>
                                {studentResults.results.map((r) => (
                                  <li key={r.id} style={{ padding: '3px 0' }}>
                                    <strong>{r.test}</strong> ({r.subject}) —{' '}
                                    {r.grading_status === 'graded'
                                      ? `${r.score} / ${r.max_score} (${r.percentage}%)`
                                      : 'Baholash kutilmoqda'}{' '}
                                    <span style={{ opacity: 0.6 }}>• {new Date(r.calculated_at).toLocaleDateString()}</span>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        )}

                        <div style={{ marginTop: 14 }}>
                          <label className="small" style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>
                            {t('gf_select_students')}
                            <input
                              value={search}
                              onChange={(e) => onSearch(g.id, e.target.value)}
                              placeholder={t('mt_search_ph')}
                              style={{ marginTop: 4 }}
                            />
                          </label>
                          <p className="muted small" style={{ margin: '4px 0 8px' }}>
                            {t('grp_search_hint')}
                          </p>
                          {search.trim().length >= 2 && (
                            <p className="muted small">
                              {searching ? t('loading') : `${found.length} ${t('an_talaba_full')}`}
                            </p>
                          )}
                          <ul className="muted small">
                            {found
                              .filter((s) => !students.some((m) => m.id === s.id))
                              .map((s) => (
                                <li key={s.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 0' }}>
                                  <span>{s.full_name || `${s.first_name} ${s.last_name}`.trim() || s.email} ({s.email})</span>
                                  <button
                                    className="btn sm ghost"
                                    style={{ marginLeft: 8 }}
                                    disabled={memberBusy}
                                    onClick={() => addMember(g.id, s.id)}
                                  >
                                    + {t('grp_add')}
                                  </button>
                                </li>
                              ))}
                          </ul>
                          {search.trim().length >= 2 && !searching && found.length === 0 && (
                            <p className="muted small">{t('grp_no_results')}</p>
                          )}
                        </div>
                      </>
                    )}

                    {tab === 'history' && (
                      <div style={{ marginTop: 8 }}>
                        <h4 style={{ margin: '8px 0' }}>{t('grp_history')}</h4>
                        {historyLoading === g.id && <p className="muted small">{t('loading')}…</p>}
                        {historyData[g.id] && historyData[g.id].length === 0 && (
                          <p className="muted small">{t('grp_no_history')}</p>
                        )}
                        {historyData[g.id] && historyData[g.id].length > 0 && (
                          <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', fontSize: '0.85rem', borderCollapse: 'collapse' }}>
                              <thead>
                                <tr style={{ textAlign: 'left', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                                  <th style={{ padding: '6px 8px' }}>Talaba</th>
                                  <th style={{ padding: '6px 8px' }}>Harakat</th>
                                  <th style={{ padding: '6px 8px' }}>Sana</th>
                                  <th style={{ padding: '6px 8px' }}>Tasdiqladi</th>
                                  <th style={{ padding: '6px 8px' }}>Sabab</th>
                                </tr>
                              </thead>
                              <tbody>
                                {historyData[g.id].map((h) => (
                                  <tr key={h.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                    <td style={{ padding: '6px 8px' }}>
                                      <span style={{ fontWeight: 600 }}>{h.student_name}</span>
                                      <br />
                                      <span style={{ opacity: 0.6, fontSize: '0.75rem' }}>{h.student_email}</span>
                                    </td>
                                    <td style={{ padding: '6px 8px' }}>
                                      <span
                                        className="badge"
                                        style={{
                                          padding: '2px 6px',
                                          borderRadius: 4,
                                          fontSize: '0.75rem',
                                          background:
                                            h.action === 'joined' || h.action === 'rejoined'
                                              ? 'rgba(16, 185, 129, 0.2)'
                                              : 'rgba(239, 68, 68, 0.2)',
                                          color:
                                            h.action === 'joined' || h.action === 'rejoined' ? '#10b981' : '#ef4444',
                                        }}
                                      >
                                        {h.action_display || h.action}
                                      </span>
                                    </td>
                                    <td style={{ padding: '6px 8px', opacity: 0.8, fontSize: '0.8rem' }}>
                                      {h.joined_at ? new Date(h.joined_at).toLocaleString() : '—'}
                                      {h.removed_at && (
                                        <div style={{ color: '#ef4444', fontSize: '0.75rem' }}>
                                          Chiqdi: {new Date(h.removed_at).toLocaleString()}
                                        </div>
                                      )}
                                    </td>
                                    <td style={{ padding: '6px 8px', opacity: 0.8 }}>{h.actor_name || 'Tizim'}</td>
                                    <td style={{ padding: '6px 8px', opacity: 0.7 }}>{h.reason || '—'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    )}

                    {tab === 'attendance' && (
                      <div style={{ marginTop: 8 }}>
                        {/* 1-Click Davomat Info Banner */}
                        <div
                          style={{
                            padding: '10px 14px',
                            borderRadius: 8,
                            background: 'var(--info-bg)',
                            border: '1px solid var(--info-border)',
                            marginBottom: 12,
                            fontSize: '0.84rem',
                            color: 'var(--info-text)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                          }}
                        >
                          <span style={{ fontSize: '1.2rem' }}>⚡</span>
                          <span>
                            <strong>1-Click Davomat:</strong> O'quvchi yonidagi tugmani bosing — davomat darhol saqlanadi. Agar <strong>❌ Kelmadi</strong> tanlansa, 15 daqiqadan so'ng ota-onasining Telegram botiga avtomatik xabar yuboriladi.
                          </span>
                        </div>

                        {students.length === 0 ? (
                          <p className="muted small">Bu guruhda hali o'quvchilar yo'q.</p>
                        ) : (
                          <div className="table-wrap">
                            <table className="data" style={{ fontSize: '0.86rem' }}>
                              <thead>
                                <tr>
                                  <th>O'quvchi</th>
                                  <th>1-Click Davomat</th>
                                </tr>
                              </thead>
                              <tbody>
                                {students.map((s) => {
                                  const key = `${g.id}_${s.id}`;
                                  const curStatus = groupAttendance[key];
                                  return (
                                    <tr key={s.id}>
                                      <td>
                                        <strong>{s.full_name}</strong>
                                        <div className="muted small">
                        {s.email.startsWith('tg_') || s.email.includes('@tma') ? (
                          <span className="badge" style={{ background: 'rgba(56, 189, 248, 0.12)', color: '#0284c7', fontSize: '0.7rem' }}>
                            📱 Telegram
                          </span>
                        ) : (
                          s.email
                        )}
                      </div>
                                      </td>
                                      <td>
                                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                          <button
                                            type="button"
                                            className={`btn sm ${curStatus === 'present' ? 'primary' : 'ghost'}`}
                                            onClick={() => quickMarkStudent(g.id, s.id, 'present', s.full_name)}
                                            style={{ minHeight: 44, minWidth: 74, fontWeight: curStatus === 'present' ? 800 : 500 }}
                                          >
                                            ✅ Keldi
                                          </button>
                                          <button
                                            type="button"
                                            className={`btn sm ${curStatus === 'late' ? 'primary' : 'ghost'}`}
                                            onClick={() => quickMarkStudent(g.id, s.id, 'late', s.full_name)}
                                            style={{ minHeight: 44, minWidth: 74, fontWeight: curStatus === 'late' ? 800 : 500 }}
                                          >
                                            ⚠️ Kechikdi
                                          </button>
                                          <button
                                            type="button"
                                            className={`btn sm ${curStatus === 'absent' ? 'primary' : 'ghost'}`}
                                            onClick={() => quickMarkStudent(g.id, s.id, 'absent', s.full_name)}
                                            style={{ minHeight: 44, minWidth: 74, fontWeight: curStatus === 'absent' ? 800 : 500 }}
                                          >
                                            ❌ Kelmadi
                                          </button>
                                          <button
                                            type="button"
                                            className={`btn sm ${curStatus === 'excused' ? 'primary' : 'ghost'}`}
                                            onClick={() => quickMarkStudent(g.id, s.id, 'excused', s.full_name)}
                                            style={{ minHeight: 44, minWidth: 74, fontWeight: curStatus === 'excused' ? 800 : 500 }}
                                          >
                                            📝 Sababli
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
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* White-Label B2B Branding Modal */}
      <Modal
        open={brandingOpen}
        onClose={() => {
          if (!savingBranding) setBrandingOpen(false);
        }}
        title="🎨 Markaz Brendi & White-Label Sozlamalari"
        subtitle="Ushbu ma'lumotlar ota-onalar yig'ilishi va direktorlar uchun generatsiya qilinadigan rasmiy A4 Oylik PDF hisobotlarida to'liq aks etadi."
        maxWidth={520}
      >
        <form onSubmit={saveBranding} style={{ display: 'grid', gap: 14 }}>
          <div>
            <label htmlFor="wl-center-name" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
              O'quv markazi / Maktab nomi
            </label>
            <input
              id="wl-center-name"
              type="text"
              value={centerName}
              onChange={(e) => setCenterName(e.target.value)}
              placeholder="Masalan: GRAND EDUCATION Karmana filiali"
              required
            />
          </div>

          <div>
            <label htmlFor="wl-header-title" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
              Hisobot bosh sarlavhasi (Header Title)
            </label>
            <input
              id="wl-header-title"
              type="text"
              value={headerTitle}
              onChange={(e) => setHeaderTitle(e.target.value)}
              placeholder="Masalan: OYLIK AKADEMIK VA BMB DIAGNOSTIKA HISOBOTI"
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr', gap: 12, alignItems: 'center' }}>
            <div>
              <label htmlFor="wl-brand-color-picker" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
                Brend rangi
              </label>
              <input
                id="wl-brand-color-picker"
                type="color"
                value={brandColor}
                onChange={(e) => setBrandColor(e.target.value)}
                style={{ height: 40, width: '100%', padding: 2, cursor: 'pointer', borderRadius: 8 }}
              />
            </div>
            <div>
              <label htmlFor="wl-brand-color-hex" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
                Rang kodi (HEX)
              </label>
              <input
                id="wl-brand-color-hex"
                type="text"
                value={brandColor}
                onChange={(e) => setBrandColor(e.target.value)}
                placeholder="#1e3a8a"
              />
            </div>
          </div>

          <div>
            <label htmlFor="wl-logo-file" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
              O'quv markazi logotipi (PNG / JPG)
            </label>
            {currentLogoUrl && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <img src={currentLogoUrl} alt="Logo" style={{ height: 36, objectFit: 'contain' }} />
                <span className="small muted">Joriy logotip yuklangan</span>
              </div>
            )}
            <input
              id="wl-logo-file"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => setLogoFile(e.target.files?.[0] || null)}
            />
          </div>

          <div>
            <label htmlFor="wl-stamp-file" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
              Rasmiy muhr yoki rahbar imzosi (Shaffof PNG tavsiya etiladi)
            </label>
            {currentStampUrl && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <img src={currentStampUrl} alt="Muhr" style={{ height: 44, objectFit: 'contain' }} />
                <span className="small muted">Joriy muhr yuklangan</span>
              </div>
            )}
            <input
              id="wl-stamp-file"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => setStampFile(e.target.files?.[0] || null)}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 10 }}>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => setBrandingOpen(false)}
              disabled={savingBranding}
            >
              Bekor qilish
            </button>
            <button
              type="submit"
              className="btn primary sm"
              disabled={savingBranding}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              {savingBranding ? 'Saqlanmoqda...' : '💾 Sozlamalarni saqlash'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Dependencies & Academic History Modal */}
      <Modal
        open={Boolean(depGroup)}
        onClose={() => {
          if (depGroup && lifecycleBusyId === depGroup.id) return;
          setDepGroup(null);
        }}
        title="🛡️ Guruh xavfsizligi va akademik audit"
        subtitle={depGroup ? `Guruh: ${depGroup.name}` : undefined}
        maxWidth={520}
      >
        {depGroup && (
          <>
            {depLoading && (
              <div style={{ textAlign: 'center', padding: '24px 0' }}>
                <p className="muted">Akademik tarix tekshirilmoqda…</p>
              </div>
            )}

            {!depLoading && depData && (
              <div>
                <div
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 12,
                    padding: 14,
                    marginBottom: 16,
                  }}
                >
                  <p style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                    Bog‘liq ma‘lumotlar:
                  </p>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    <li>O‘quvchilar: <b>{depData.dependencies.students_count}</b> nafar</li>
                    <li>Uy vazifalari: <b>{depData.dependencies.homeworks_count}</b> ta</li>
                    <li>Topshirilgan vazifalar: <b>{depData.dependencies.homework_submissions_count}</b> ta</li>
                    <li>Davomat mashg‘ulotlari: <b>{depData.dependencies.attendance_sessions_count}</b> ta</li>
                    <li>Esse topshiriqlari: <b>{depData.dependencies.essay_assignments_count}</b> ta</li>
                  </ul>
                </div>

                {!depData.can_delete ? (
                  <div style={{ marginBottom: 16 }}>
                    <Alert tone="warning" title="⚠️ Guruhni o‘chirish taqiqlangan!">
                      Ushbu guruhda o‘quvchilar va akademik tarix mavjud. O‘quvchilar natijalari va baholari yo‘qolib
                      ketmasligi uchun guruhni butunlay o‘chirish o‘rniga <b>arxivlash</b> tavsiya etiladi.
                    </Alert>
                  </div>
                ) : (
                  <div style={{ marginBottom: 16 }}>
                    <Alert tone="success">
                      ✅ Ushbu guruhda hech qanday akademik tarix yoki o‘quvchilar yo‘q. Uni xavfsiz o‘chirishingiz mumkin.
                    </Alert>
                  </div>
                )}

                <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="btn ghost sm"
                    disabled={lifecycleBusyId === depGroup.id}
                    onClick={() => setDepGroup(null)}
                  >
                    Bekor qilish
                  </button>
                  <button
                    type="button"
                    className="btn secondary sm"
                    disabled={lifecycleBusyId === depGroup.id}
                    onClick={() => void handleArchive(depGroup.id)}
                  >
                    {lifecycleBusyId === depGroup.id ? 'Bajarilmoqda…' : '📦 Guruhni arxivlash'}
                  </button>
                  {depData.can_delete && (
                    <button
                      type="button"
                      className="btn danger sm"
                      disabled={lifecycleBusyId === depGroup.id}
                      onClick={() => void handleSafeDelete(depGroup.id)}
                    >
                      {lifecycleBusyId === depGroup.id ? 'O‘chirilmoqda…' : '🗑 Butunlay o‘chirish'}
                    </button>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </Modal>
    </div>
  );
}
