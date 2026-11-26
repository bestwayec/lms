import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertCircle, ArrowLeft, CheckCircle2, FileText, RefreshCw, Sparkles } from 'lucide-react';
import { useLang } from '../i18n/LangContext';
import { Essays, type IeltsCriterionScore, type IeltsGradePayload, type IeltsGradeResponse } from '../lib/api';
import { countEssayWords } from '../lib/essays-arena';

interface TaskOption {
  code: IeltsGradePayload['task_type'];
  label: string;
  minWords: number;
  recommendedMinutes: number;
  defaultPrompt: string;
}

const WRITING_TASKS: TaskOption[] = [
  {
    code: 'ielts_task2',
    label: 'IELTS Task 2 Essay',
    minWords: 250,
    recommendedMinutes: 40,
    defaultPrompt:
      'Some people believe that unpaid community service should be a compulsory part of high school programmes. To what extent do you agree or disagree?',
  },
  {
    code: 'ielts_task1',
    label: 'IELTS Task 1 Report / Letter',
    minWords: 150,
    recommendedMinutes: 20,
    defaultPrompt:
      'Summarise the main features of the provided data or write a structured formal/semi-formal letter addressing every bullet point.',
  },
  {
    code: 'multilevel_1_1',
    label: 'BMB Multi-level Task 1.1 (Email)',
    minWords: 50,
    recommendedMinutes: 15,
    defaultPrompt: 'Reply briefly to your friend or colleague’s email (~50–70 words) covering the requested details.',
  },
  {
    code: 'multilevel_1_2',
    label: 'BMB Multi-level Task 1.2 (Formal Response)',
    minWords: 120,
    recommendedMinutes: 20,
    defaultPrompt: 'Write a structured response (~120–150 words) on the same situation with an appropriate formal/semi-formal register.',
  },
  {
    code: 'multilevel_2',
    label: 'BMB Multi-level Task 2 (Blog / Essay)',
    minWords: 180,
    recommendedMinutes: 25,
    defaultPrompt: 'Present your opinion and supporting arguments clearly in 180–220 words with balanced paragraphing.',
  },
];

export default function EssayStudio() {
  const { t } = useLang();
  const { topicId } = useParams();

  const [selectedTask, setSelectedTask] = useState<IeltsGradePayload['task_type']>('ielts_task2');
  const [customPrompt, setCustomPrompt] = useState<string>(WRITING_TASKS[0].defaultPrompt);
  const [essayText, setEssayText] = useState<string>('');
  const [analyzing, setAnalyzing] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [result, setResult] = useState<IeltsGradeResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'editor' | 'review'>('editor');

  const taskSpec = useMemo(
    () => WRITING_TASKS.find((item) => item.code === selectedTask) || WRITING_TASKS[0],
    [selectedTask],
  );
  const words = useMemo(() => countEssayWords(essayText), [essayText]);
  const wordProgress = Math.min(100, Math.round((words / Math.max(1, taskSpec.minWords)) * 100));

  const handleTaskSelect = (code: IeltsGradePayload['task_type']) => {
    setSelectedTask(code);
    const nextSpec = WRITING_TASKS.find((item) => item.code === code);
    if (nextSpec) setCustomPrompt(nextSpec.defaultPrompt);
  };

  const handleAiCheck = async () => {
    if (!essayText.trim()) {
      setErrorMsg(t('eng_writing_empty_err', 'Avval esse matnini yozing.'));
      return;
    }
    setAnalyzing(true);
    setErrorMsg(null);
    try {
      const res = await Essays.ieltsGrade({
        task_type: selectedTask,
        topic_title: customPrompt.trim() || taskSpec.label,
        ...(topicId && /^\d+$/.test(topicId) ? { topic_id: Number(topicId) } : {}),
        essay_text: essayText,
      });
      setResult(res);
      setActiveTab('review');
    } catch (err: unknown) {
      setResult(null);
      setErrorMsg(
        err instanceof Error
          ? err.message
          : t('eng_ai_unavailable', "AI baholash hozircha amalga oshmadi. Limitingiz qaytarildi."),
      );
    } finally {
      setAnalyzing(false);
    }
  };

  const criteriaList: IeltsCriterionScore[] = result?.criteria || [];

  return (
    <div className="max-w-[1360px] mx-auto w-full px-3 sm:px-6 py-4 space-y-5">
      {/* Header */}
      <header className="bento-card p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link
            to="/essays"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 text-xs font-bold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 no-underline"
          >
            <ArrowLeft size={15} />
            <span>{t('back', 'Ortga')}</span>
          </Link>
          <div>
            <span className="inline-block text-[11px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-300">
              WRITING STUDIO 3.0
            </span>
            <h1 className="text-lg sm:text-xl font-extrabold text-slate-900 dark:text-white mt-0.5">
              {t('x_essay_title', 'IELTS & CEFR Multi-level Writing Studio')}
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={selectedTask}
            onChange={(e) => handleTaskSelect(e.target.value as IeltsGradePayload['task_type'])}
            aria-label={t('eng_writing_task_select', 'Topshiriq turi')}
            className="h-10 px-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-bold text-slate-900 dark:text-white"
          >
            {WRITING_TASKS.map((task) => (
              <option key={task.code} value={task.code}>
                {task.label} ({task.minWords}+)
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={handleAiCheck}
            disabled={analyzing}
            className="bento-btn bento-btn-gold h-10 px-4 text-xs font-extrabold inline-flex items-center gap-2"
          >
            {analyzing ? (
              <>
                <RefreshCw size={15} className="animate-spin" />
                <span>{t('x_checking', 'Tekshirilmoqda...')}</span>
              </>
            ) : (
              <>
                <Sparkles size={15} />
                <span>{t('x_ai_check', 'AI Baholash')}</span>
              </>
            )}
          </button>
        </div>
      </header>

      {errorMsg && (
        <div className="bento-card p-4 border-rose-300 dark:border-rose-800 bg-rose-50/70 dark:bg-rose-950/30 flex items-center gap-2 text-sm font-semibold text-rose-700 dark:text-rose-300" role="alert">
          <AlertCircle size={17} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Split Workspace: Prompt / Editor + Feedback */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left: Prompt & Criteria Result Summary */}
        <aside className="lg:col-span-4 space-y-4">
          <div className="bento-card p-4 space-y-3">
            <div className="flex items-center justify-between text-xs font-bold text-slate-500 dark:text-slate-400">
              <span>{taskSpec.label}</span>
              <span className="font-mono">{taskSpec.recommendedMinutes} min · {taskSpec.minWords}+ words</span>
            </div>
            <textarea
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
              rows={4}
              aria-label={t('eng_writing_prompt', 'Mavzu matni')}
              className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 p-3 text-xs text-slate-800 dark:text-slate-200"
            />
            <div>
              <div className="flex justify-between text-xs font-bold mb-1">
                <span className="text-slate-600 dark:text-slate-300">{t('word_count', "So'zlar soni")}</span>
                <span className={words >= taskSpec.minWords ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}>
                  {words} / {taskSpec.minWords}
                </span>
              </div>
              <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                <div
                  className={`h-full transition-all ${words >= taskSpec.minWords ? 'bg-emerald-500' : 'bg-amber-500'}`}
                  style={{ width: `${wordProgress}%` }}
                />
              </div>
            </div>
          </div>

          <div className="bento-card p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                {t('x_ielts_score', 'Baholash natijasi')}
              </span>
              {result ? (
                <span className="text-xl font-black font-mono text-amber-600 dark:text-amber-400">
                  Band {result.overall_band.toFixed(1)} · {result.cefr_level}
                </span>
              ) : (
                <span className="text-xs font-mono text-slate-400">—</span>
              )}
            </div>

            {!result ? (
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {t('eng_writing_ungraded_hint', "Matnni yozing va 'AI Baholash' tugmasini bosing — mezon ballari va dalilli tahlil shu yerda chiqadi.")}
              </p>
            ) : (
              <ul className="space-y-2">
                {criteriaList.map((c, idx) => (
                  <li key={c.id ?? idx} className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/40">
                    <div className="flex items-center justify-between text-xs font-bold">
                      <span className="text-slate-900 dark:text-white">{c.name}</span>
                      <span className="font-mono text-indigo-600 dark:text-indigo-400">{Number(c.score).toFixed(1)}</span>
                    </div>
                    {c.reason && <p className="text-[11px] text-slate-600 dark:text-slate-300 mt-1">{c.reason}</p>}
                    {c.quote && (
                      <p className="text-[11px] italic text-slate-500 dark:text-slate-400 mt-1">
                        {c.quote_verified ? '✓ ' : ''}&ldquo;{c.quote}&rdquo;
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        {/* Right: Editor & Verified Feedback Tabs */}
        <section className="lg:col-span-8 bento-card p-4 sm:p-5 space-y-4">
          <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-3">
            <button
              type="button"
              onClick={() => setActiveTab('editor')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 ${
                activeTab === 'editor'
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            >
              <FileText size={14} />
              <span>{t('studio_edit', 'Muharrir')}</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('review')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 ${
                activeTab === 'review'
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            >
              <CheckCircle2 size={14} />
              <span>{t('eng_ai_review_tab', 'AI Tahlil va Model Javob')}</span>
            </button>
          </div>

          {activeTab === 'editor' ? (
            <textarea
              value={essayText}
              onChange={(e) => setEssayText(e.target.value)}
              rows={16}
              placeholder={t('x_essay_placeholder', 'Essengizni shu yerda yozing...')}
              className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-4 text-sm leading-relaxed text-slate-900 dark:text-slate-100 focus:border-indigo-500 outline-none"
            />
          ) : !result ? (
            <div className="py-12 text-center text-sm text-slate-500 dark:text-slate-400">
              {t('eng_writing_no_result_yet', "Hali AI baholash o'tkazilmagan.")}
            </div>
          ) : (
            <div className="space-y-4 text-sm">
              <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">
                  {t('summary', 'Umumiy xulosa')}
                </h2>
                <p className="text-slate-800 dark:text-slate-200 leading-relaxed">{result.summary}</p>
              </div>

              {(result.strengths?.length || result.weaknesses?.length) ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {result.strengths && result.strengths.length > 0 && (
                    <div className="p-3.5 rounded-xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50/60 dark:bg-emerald-950/20">
                      <h3 className="text-xs font-bold text-emerald-700 dark:text-emerald-300 mb-1.5">Strengths</h3>
                      <ul className="list-disc pl-4 space-y-1 text-xs text-slate-700 dark:text-slate-300">
                        {result.strengths.map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    </div>
                  )}
                  {result.weaknesses && result.weaknesses.length > 0 && (
                    <div className="p-3.5 rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50/60 dark:bg-amber-950/20">
                      <h3 className="text-xs font-bold text-amber-700 dark:text-amber-300 mb-1.5">Areas to Improve</h3>
                      <ul className="list-disc pl-4 space-y-1 text-xs text-slate-700 dark:text-slate-300">
                        {result.weaknesses.map((w, i) => <li key={i}>{w}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              ) : null}

              {result.improved_text && (
                <div className="p-4 rounded-xl border border-indigo-200 dark:border-indigo-900 bg-indigo-50/40 dark:bg-indigo-950/20">
                  <h3 className="text-xs font-bold text-indigo-700 dark:text-indigo-300 mb-1.5">Band 8.0+ Improved Rewrite</h3>
                  <p className="text-xs sm:text-sm whitespace-pre-wrap text-slate-800 dark:text-slate-200 leading-relaxed">
                    {result.improved_text}
                  </p>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
