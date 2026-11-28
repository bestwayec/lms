import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  BookOpen,
  CheckCircle2,
  ClipboardList,
  FileText,
  GraduationCap,
  Headphones,
  Layers,
  Mic,
  PenTool,
  Play,
  RotateCcw,
  Search,
  Sparkles,
  Target,
} from 'lucide-react';
import { useAuth } from '../auth/authState';
import { useToast } from '../context/toastState';
import { useLang } from '../i18n/LangContext';
import { EnglishCenterApi, type EnglishCenterData, type EnglishCenterTestCard } from '../lib/api';

const BAND_CHOICES = [5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0];
const CEFR_CHOICES = ['A2', 'B1', 'B2', 'C1', 'C2'];

function testLinkWithMode(testId: number, mode: string): string {
  return `/tests/${testId}?mode=${encodeURIComponent(mode)}`;
}

export default function EnglishCenter() {
  const { t } = useLang();
  const { refreshUser } = useAuth();
  const toast = useToast();

  const [data, setData] = useState<EnglishCenterData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedMode, setSelectedMode] = useState<string>('practice');
  const [searchQuery, setSearchQuery] = useState('');

  const load = useCallback(
    (track?: string, q?: string) => {
      setLoading(true);
      setError(null);
      EnglishCenterApi.get(track, q)
        .then((res) => setData(res))
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : t('error_generic', 'Xatolik yuz berdi'));
        })
        .finally(() => setLoading(false));
    },
    [t],
  );

  useEffect(() => {
    let alive = true;
    EnglishCenterApi.get()
      .then((res) => {
        if (alive) {
          setData(res);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (alive) {
          setError(err instanceof Error ? err.message : t('error_generic', 'Xatolik yuz berdi'));
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [t]);

  const handleTrackChange = async (trackCode: string) => {
    if (saving || data?.track === trackCode) return;
    setSaving(true);
    try {
      await EnglishCenterApi.updateSettings({ english_track: trackCode, set_active_subject: true });
      await refreshUser().catch(() => undefined);
      load(trackCode, searchQuery.trim() || undefined);
      toast.success(t('eng_track_saved', "Yo'nalish saqlandi"));
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : t('error_generic', 'Saqlanmadi'));
    } finally {
      setSaving(false);
    }
  };

  const handleTargetBand = async (bandVal: string) => {
    const parsed = bandVal ? Number(bandVal) : null;
    setSaving(true);
    try {
      await EnglishCenterApi.updateSettings({ target_band: parsed });
      await refreshUser().catch(() => undefined);
      setData((prev) => (prev ? { ...prev, target_band: parsed } : prev));
      toast.success(t('eng_target_saved', 'Maqsad saqlandi'));
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : t('error_generic', 'Saqlanmadi'));
    } finally {
      setSaving(false);
    }
  };

  const handleTargetCefr = async (cefrVal: string) => {
    setSaving(true);
    try {
      await EnglishCenterApi.updateSettings({ target_cefr_level: cefrVal });
      await refreshUser().catch(() => undefined);
      setData((prev) => (prev ? { ...prev, target_cefr_level: cefrVal } : prev));
      toast.success(t('eng_target_saved', 'Maqsad saqlandi'));
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : t('error_generic', 'Saqlanmadi'));
    } finally {
      setSaving(false);
    }
  };

  const activeTrackInfo = data?.tracks.find((tr) => tr.code === data.track) || data?.tracks[0];
  const isIeltsTrack = data?.track === 'ielts_academic' || data?.track === 'ielts_general';

  const renderTestList = (items: EnglishCenterTestCard[], emptyText: string, fallbackHref: string) => {
    if (items.length === 0) {
      return (
        <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-4 text-center">
          <p className="text-xs text-slate-600 dark:text-slate-400 mb-2">{emptyText}</p>
          <Link to={fallbackHref} className="text-xs font-bold text-indigo-600 dark:text-indigo-400 hover:underline">
            {t('eng_browse_all', "Barcha testlarni ko'rish")} →
          </Link>
        </div>
      );
    }
    return (
      <ul className="space-y-2">
        {items.slice(0, 4).map((item) => (
          <li
            key={item.id}
            className="flex items-center justify-between gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 hover:border-indigo-400 dark:hover:border-indigo-500 transition-colors"
          >
            <div className="min-w-0">
              <p className="text-sm font-bold text-slate-900 dark:text-white truncate">{item.title}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2 flex-wrap">
                <span>{item.question_count} {t('questions_short', 'savol')}</span>
                {item.time_limit_minutes > 0 && <span>· {item.time_limit_minutes} {t('minutes_short', 'daq')}</span>}
                {item.mock_code && <span className="font-mono text-[11px]">{item.mock_code}</span>}
              </p>
            </div>
            <Link
              to={testLinkWithMode(item.id, selectedMode)}
              className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-indigo-600 text-white hover:bg-indigo-700 no-underline"
            >
              <Play size={13} />
              <span>{t('start', 'Boshlash')}</span>
            </Link>
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="max-w-[1360px] mx-auto w-full px-3 sm:px-6 py-4 space-y-6">
      {/* Header & Track Selector */}
      <section className="bento-card p-5 sm:p-6">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-5">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-500/20 text-xs font-bold mb-2">
              <GraduationCap size={14} />
              <span>{t('english_center_title', 'English Learning Center')}</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
              {t('eng_hub_heading', 'IELTS Academic, General va CEFR Multi-level markazi')}
            </h1>
            {activeTrackInfo && (
              <p className="text-sm text-slate-600 dark:text-slate-300 mt-1 max-w-2xl">
                {activeTrackInfo.description}
              </p>
            )}
          </div>

          {/* Target Score & Search */}
          <div className="flex flex-wrap items-center gap-3">
            {isIeltsTrack ? (
              <label className="flex flex-col gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
                <span className="inline-flex items-center gap-1">
                  <Target size={13} className="text-amber-500" />
                  {t('eng_target_band_label', 'Maqsad IELTS Band')}
                </span>
                <select
                  value={data?.target_band != null ? String(data.target_band) : ''}
                  disabled={saving}
                  onChange={(e) => handleTargetBand(e.target.value)}
                  className="h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-bold text-slate-900 dark:text-white"
                >
                  <option value="">{t('eng_not_set', 'Tanlanmagan')}</option>
                  {BAND_CHOICES.map((b) => (
                    <option key={b} value={b.toFixed(1)}>
                      Band {b.toFixed(1)}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label className="flex flex-col gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
                <span className="inline-flex items-center gap-1">
                  <Target size={13} className="text-amber-500" />
                  {t('eng_target_cefr_label', 'Maqsad CEFR daraja')}
                </span>
                <select
                  value={data?.target_cefr_level || ''}
                  disabled={saving}
                  onChange={(e) => handleTargetCefr(e.target.value)}
                  className="h-9 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-bold text-slate-900 dark:text-white"
                >
                  <option value="">{t('eng_not_set', 'Tanlanmagan')}</option>
                  {CEFR_CHOICES.map((lvl) => (
                    <option key={lvl} value={lvl}>
                      {lvl}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                load(data?.track, searchQuery.trim() || undefined);
              }}
              className="flex items-end gap-2 w-full sm:w-auto"
            >
              <div className="relative flex-1 sm:flex-initial min-w-0">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t('eng_search_placeholder', 'Test yoki mavzu qidirish...')}
                  style={{ paddingLeft: 38 }}
                  className="h-9 w-full sm:w-56 pr-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-white"
                />
              </div>
              <button
                type="submit"
                className="h-9 px-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-400 text-white text-xs font-bold shrink-0 border-0"
              >
                {t('search', 'Qidirish')}
              </button>
            </form>
          </div>
        </div>

        {/* 4 Track Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-5" role="radiogroup" aria-label={t('eng_track_selector', "Tayyorlov yo'nalishi")}>
          {(data?.tracks || []).map((tr) => {
            const active = tr.code === data?.track;
            return (
              <button
                key={tr.code}
                type="button"
                role="radio"
                aria-checked={active}
                disabled={saving}
                onClick={() => handleTrackChange(tr.code)}
                className={`text-left p-3.5 rounded-xl border transition-all ${
                  active
                    ? 'border-indigo-500 bg-indigo-50/90 dark:bg-indigo-950/50 ring-2 ring-indigo-500/20'
                    : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/40 hover:border-slate-300 dark:hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-sm font-extrabold text-slate-900 dark:text-white">{tr.label}</span>
                  {active && <CheckCircle2 size={16} className="text-indigo-600 dark:text-indigo-400 shrink-0" />}
                </div>
                <span className="inline-block text-[11px] font-mono font-bold px-2 py-0.5 rounded bg-slate-200/70 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                  {tr.scale}
                </span>
              </button>
            );
          })}
        </div>

        {/* Study Mode Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-200 dark:border-slate-800">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mr-1">
              {t('eng_study_mode', 'O‘qish rejimi')}:
            </span>
            {(data?.study_modes || []).map((m) => {
              const selected = selectedMode === m.code;
              return (
                <button
                  key={m.code}
                  type="button"
                  onClick={() => setSelectedMode(m.code)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors ${
                    selected
                      ? 'border-amber-500 bg-amber-500/20 text-amber-800 dark:text-amber-200'
                      : 'border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  {m.label}
                </button>
              );
            })}
          </div>

          {data?.resume && (
            <Link
              to={data.resume.route}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-950 text-xs font-extrabold no-underline shadow-sm"
            >
              <RotateCcw size={14} />
              <span>{t('eng_resume_cta', 'Davom ettirish')}: {data.resume.title}</span>
            </Link>
          )}
        </div>
      </section>

      {error && (
        <div className="bento-card p-4 border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-sm">
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((idx) => (
            <div key={idx} className="bento-card p-5 h-44 animate-pulse bg-slate-100 dark:bg-slate-800/40" />
          ))}
        </div>
      ) : data ? (
        <>
          {/* Real Skill Progress Snapshot */}
          <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3" aria-label={t('eng_skill_progress', "Ko'nikmalar progressi")}>
            <div className="bento-card p-4">
              <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Listening</span>
              <p className="text-xl font-extrabold text-slate-900 dark:text-white mt-1">
                {data.skill_progress.listening.best_pct != null ? `${data.skill_progress.listening.best_pct}%` : '—'}
              </p>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                {data.skill_progress.listening.attempts} {t('attempts_short', 'urinish')}
              </span>
            </div>
            <div className="bento-card p-4">
              <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Reading</span>
              <p className="text-xl font-extrabold text-slate-900 dark:text-white mt-1">
                {data.skill_progress.reading.best_pct != null ? `${data.skill_progress.reading.best_pct}%` : '—'}
              </p>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                {data.skill_progress.reading.attempts} {t('attempts_short', 'urinish')}
              </span>
            </div>
            <div className="bento-card p-4">
              <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Writing</span>
              <p className="text-xl font-extrabold text-slate-900 dark:text-white mt-1">
                {data.skill_progress.writing.latest_score != null
                  ? `${data.skill_progress.writing.latest_score}/${data.skill_progress.writing.latest_max ?? 9}`
                  : '—'}
              </p>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                {data.skill_progress.writing.submissions} {t('essays', 'esse')}
              </span>
            </div>
            <div className="bento-card p-4">
              <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Speaking</span>
              <p className="text-xl font-extrabold text-slate-900 dark:text-white mt-1">
                {data.skill_progress.speaking.latest_band != null ? `Band ${data.skill_progress.speaking.latest_band}` : '—'}
              </p>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                {data.skill_progress.speaking.submissions} {t('eng_recordings', 'yozuv')}
              </span>
            </div>
            <div className="bento-card p-4 col-span-2 sm:col-span-1">
              <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">{t('eng_mistakes_title', 'Xatolar daftari')}</span>
              <p className="text-xl font-extrabold text-slate-900 dark:text-white mt-1">
                {data.mistakes.total}
              </p>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                {t('eng_to_review', 'takrorlash kerak')}
              </span>
            </div>
          </section>

          {/* Main Skill Modules Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Listening Module */}
            <section className="bento-card p-5 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Headphones size={18} className="text-indigo-600 dark:text-indigo-400" />
                  <h2 className="text-base font-extrabold text-slate-900 dark:text-white">Listening</h2>
                </div>
                <Link to={`/tests?skill=LISTENING&mode=${encodeURIComponent(selectedMode)}`} className="text-xs font-bold text-indigo-600 dark:text-indigo-400 hover:underline">
                  {t('eng_all_listening', 'Barchasi')} ({data.counts.listening_tests}) →
                </Link>
              </div>
              {renderTestList(
                data.listening_tests,
                t('eng_no_listening', "Tanlangan yo'nalishda Listening testlari topilmadi."),
                '/tests?skill=LISTENING',
              )}
            </section>

            {/* Reading Module */}
            <section className="bento-card p-5 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <BookOpen size={18} className="text-emerald-600 dark:text-emerald-400" />
                  <h2 className="text-base font-extrabold text-slate-900 dark:text-white">Reading</h2>
                </div>
                <Link to={`/tests?skill=READING&mode=${encodeURIComponent(selectedMode)}`} className="text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:underline">
                  {t('eng_all_reading', 'Barchasi')} ({data.counts.reading_tests}) →
                </Link>
              </div>
              {renderTestList(
                data.reading_tests,
                t('eng_no_reading', "Tanlangan yo'nalishda Reading testlari topilmadi."),
                '/tests?skill=READING',
              )}
            </section>

            {/* Writing Studio */}
            <section className="bento-card p-5 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <PenTool size={18} className="text-amber-600 dark:text-amber-400" />
                  <h2 className="text-base font-extrabold text-slate-900 dark:text-white">Writing Studio</h2>
                </div>
                <Link to="/essays" className="text-xs font-bold text-amber-600 dark:text-amber-400 hover:underline">
                  {t('eng_open_writing', 'Writing Studiyasi')} ({data.counts.writing_topics}) →
                </Link>
              </div>
              {data.writing_topics.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-4 text-center">
                  <p className="text-xs text-slate-600 dark:text-slate-400 mb-2">
                    {t('eng_no_writing', "Ingliz tili Writing mavzulari hozircha bo'sh.")}
                  </p>
                  <Link to="/essays" className="text-xs font-bold text-amber-600 dark:text-amber-400 hover:underline">
                    {t('eng_custom_writing', 'Erkin mavzuda yozish')} →
                  </Link>
                </div>
              ) : (
                <ul className="space-y-2">
                  {data.writing_topics.slice(0, 4).map((w) => (
                    <li
                      key={w.id}
                      className="flex items-center justify-between gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-bold text-slate-900 dark:text-white truncate">{w.title}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          {w.category} · {w.word_limit_min}+ {t('words_short', "so'z")} · {w.time_limit_minutes} {t('minutes_short', 'daq')}
                        </p>
                      </div>
                      <Link
                        to={`/essays/write/${w.id}`}
                        className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-bold bg-amber-500 hover:bg-amber-600 text-slate-950 no-underline"
                      >
                        {t('write', 'Yozish')}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Speaking Studio */}
            <section className="bento-card p-5 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Mic size={18} className="text-rose-600 dark:text-rose-400" />
                  <h2 className="text-base font-extrabold text-slate-900 dark:text-white">AI Speaking Simulator</h2>
                </div>
                <Link to="/speaking" className="text-xs font-bold text-rose-600 dark:text-rose-400 hover:underline">
                  {t('eng_open_speaking', 'Speaking Xonasi')} ({data.counts.speaking_topics}) →
                </Link>
              </div>
              {data.speaking_topics.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-4 text-center">
                  <p className="text-xs text-slate-600 dark:text-slate-400 mb-2">
                    {t('eng_no_speaking', 'Speaking mavzulari tez orada yuklanadi.')}
                  </p>
                  <Link to="/speaking" className="text-xs font-bold text-rose-600 dark:text-rose-400 hover:underline">
                    {t('eng_open_speaking', 'Speaking Xonasi')} →
                  </Link>
                </div>
              ) : (
                <ul className="space-y-2">
                  {data.speaking_topics.slice(0, 4).map((sp) => (
                    <li
                      key={sp.id}
                      className="flex items-center justify-between gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-bold text-slate-900 dark:text-white truncate">{sp.title}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          {sp.part.toUpperCase()} · {sp.speak_time_seconds}s
                        </p>
                      </div>
                      <Link
                        to={`/speaking/practice/${sp.id}`}
                        className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-bold bg-rose-600 hover:bg-rose-700 text-white no-underline"
                      >
                        {t('practice', 'Mashq')}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          {/* Full Mocks, Vocabulary, Homework & Grammar */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <section className="bento-card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Layers size={17} className="text-purple-600 dark:text-purple-400" />
                  <h2 className="text-sm font-extrabold text-slate-900 dark:text-white">{t('eng_full_mocks', 'Full Mock Imtihonlar')}</h2>
                </div>
                <Link to="/tests?mode=full_mock" className="text-xs font-bold text-purple-600 dark:text-purple-400 hover:underline">
                  {data.counts.full_mocks} →
                </Link>
              </div>
              {renderTestList(
                data.full_mocks,
                t('eng_no_mocks', "Tanlangan yo'nalishda Full Mock topilmadi."),
                '/tests',
              )}
            </section>

            <section className="bento-card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles size={17} className="text-sky-600 dark:text-sky-400" />
                  <h2 className="text-sm font-extrabold text-slate-900 dark:text-white">{t('eng_vocab_grammar', 'Vocabulary & Grammar')}</h2>
                </div>
                <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
                  {data.counts.vocabulary_packs} packs
                </span>
              </div>
              {data.vocabulary_packs.length === 0 ? (
                <p className="text-xs text-slate-600 dark:text-slate-400">
                  {t('eng_vocab_empty', "Lug'at to'plamlari guruh yoki o'qituvchi tomonidan qo'shilganda shu yerda ko'rinadi.")}
                </p>
              ) : (
                <ul className="space-y-2">
                  {data.vocabulary_packs.slice(0, 4).map((vp) => (
                    <li key={vp.id} className="flex items-center justify-between p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 text-xs">
                      <span className="font-bold text-slate-900 dark:text-white truncate">{vp.title}</span>
                      <span className="text-slate-500 dark:text-slate-400 shrink-0">{vp.word_count} words</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="pt-2 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs gap-2 flex-wrap">
                <Link to="/vocabulary" className="font-bold text-indigo-600 dark:text-indigo-400 hover:underline">
                  {t('voc_studio_title', 'Vocabulary Studio')} →
                </Link>
                <Link to="/grammar" className="font-bold text-sky-600 dark:text-sky-400 hover:underline">
                  {t('gram_studio_title', 'Grammar Studio')} →
                </Link>
              </div>
            </section>

            <section className="bento-card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ClipboardList size={17} className="text-teal-600 dark:text-teal-400" />
                  <h2 className="text-sm font-extrabold text-slate-900 dark:text-white">{t('eng_homework_mistakes', 'Vazifalar va Xatolar')}</h2>
                </div>
                <Link to="/my-homework" className="text-xs font-bold text-teal-600 dark:text-teal-400 hover:underline">
                  {t('all', 'Barchasi')} →
                </Link>
              </div>
              {data.homework.length === 0 ? (
                <p className="text-xs text-slate-600 dark:text-slate-400">
                  {t('eng_no_homework', "Faol ingliz tili vazifalari yo'q.")}
                </p>
              ) : (
                <ul className="space-y-2">
                  {data.homework.slice(0, 4).map((hw) => (
                    <li key={hw.id} className="flex items-center justify-between p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 text-xs">
                      <span className="font-bold text-slate-900 dark:text-white truncate">{hw.title}</span>
                      <span className={hw.is_completed ? 'text-emerald-600 font-bold' : 'text-amber-600 font-bold'}>
                        {hw.is_completed ? '✓' : hw.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="pt-2 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs">
                <Link to="/results" className="inline-flex items-center gap-1 font-bold text-indigo-600 dark:text-indigo-400 hover:underline">
                  <FileText size={13} />
                  <span>{t('results_analysis', 'Natijalar va Tahlil')} ({data.recent_results.length})</span>
                </Link>
              </div>
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}
