import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, GraduationCap, Sparkles, XCircle } from 'lucide-react';
import { useLang } from '../i18n/LangContext';
import { apiFetch } from '../lib/api';

interface GrammarTopicSummary {
  slug: string;
  title: string;
  cefr_level: string;
  description: string;
  formula: string;
  example_correct: string;
  example_incorrect: string;
  exercise_count: number;
  attempts: number;
  correct: number;
  accuracy_pct: number | null;
}

interface GrammarRecommendation {
  slug: string;
  title: string;
  cefr_level: string;
  matched_keywords: string[];
  reason: string;
}

interface GrammarExerciseItem {
  id: number;
  prompt: string;
  options: string[];
  cefr_level: string;
}

export default function GrammarStudio() {
  const { t } = useLang();
  const [topics, setTopics] = useState<GrammarTopicSummary[]>([]);
  const [recommended, setRecommended] = useState<GrammarRecommendation[]>([]);
  const [activeSlug, setActiveSlug] = useState<string | null>(null);
  const [exercises, setExercises] = useState<GrammarExerciseItem[]>([]);
  const [answers, setAnswers] = useState<Record<number, { is_correct: boolean; correct_answer: string; explanation: string }>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<{ topics: GrammarTopicSummary[]; recommended: GrammarRecommendation[] }>('/api/v1/vocabulary/grammar/topics/')
      .then((res) => {
        setTopics(res.topics || []);
        setRecommended(res.recommended || []);
        if (res.topics?.length) {
          setActiveSlug(res.topics[0].slug);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!activeSlug) return;
    apiFetch<{ exercises: GrammarExerciseItem[] }>(`/api/v1/vocabulary/grammar/topics/${activeSlug}/`)
      .then((res) => setExercises(res.exercises || []))
      .catch(() => setExercises([]));
  }, [activeSlug]);

  const activeTopic = topics.find((item) => item.slug === activeSlug) || null;

  const submitExercise = async (exId: number, option: string) => {
    const res = await apiFetch<{ ok: boolean; is_correct: boolean; correct_answer: string; explanation: string }>(
      '/api/v1/vocabulary/grammar/submit/',
      {
        method: 'POST',
        body: JSON.stringify({ exercise_id: exId, answer: option }),
      },
    );
    setAnswers((prev) => ({
      ...prev,
      [exId]: { is_correct: res.is_correct, correct_answer: res.correct_answer, explanation: res.explanation },
    }));
  };

  return (
    <div className="max-w-[1200px] mx-auto w-full px-3 sm:px-6 py-4 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to="/english" className="btn ghost sm">
            <ArrowLeft size={15} /> {t('english_center_title')}
          </Link>
          <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
            <GraduationCap size={22} className="text-indigo-600 dark:text-indigo-400" />
            <span>{t('gram_studio_title')}</span>
          </h1>
        </div>
        <Link to="/vocabulary" className="btn sm ghost">
          {t('voc_studio_title')} →
        </Link>
      </div>

      {recommended.length > 0 && (
        <div className="bento-card p-4 space-y-2 border-amber-500/30">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase text-amber-600 dark:text-amber-400">
            <Sparkles size={14} /> {t('gram_recommended_mistakes')}
          </div>
          <div className="flex flex-wrap gap-2">
            {recommended.map((rec) => (
              <button
                key={rec.slug}
                type="button"
                className="btn sm ghost"
                onClick={() => setActiveSlug(rec.slug)}
              >
                [{rec.cefr_level}] {rec.title}
              </button>
            ))}
          </div>
        </div>
      )}

      {loading ? (
        <div className="bento-card p-8 text-center muted">{t('loading')}</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <aside className="lg:col-span-4 space-y-2">
            {topics.map((topic) => (
              <button
                key={topic.slug}
                type="button"
                onClick={() => setActiveSlug(topic.slug)}
                className={`w-full text-left p-3.5 rounded-xl border transition-colors ${
                  topic.slug === activeSlug
                    ? 'border-indigo-500 bg-indigo-500/10 text-slate-900 dark:text-white'
                    : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 text-slate-700 dark:text-slate-300'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-sm">{topic.title}</span>
                  <span className="badge blue">{topic.cefr_level}</span>
                </div>
                {topic.accuracy_pct !== null && (
                  <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    {topic.correct}/{topic.attempts} ({topic.accuracy_pct}%)
                  </div>
                )}
              </button>
            ))}
          </aside>

          <main className="lg:col-span-8 space-y-4">
            {activeTopic && (
              <>
                <div className="bento-card p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <h2 className="text-lg font-extrabold text-slate-900 dark:text-white">{activeTopic.title}</h2>
                    <span className="badge blue">{activeTopic.cefr_level}</span>
                  </div>
                  <p className="text-sm text-slate-600 dark:text-slate-300">{activeTopic.description}</p>
                  <div className="p-3 rounded-xl bg-slate-100 dark:bg-slate-800/80 font-mono text-xs text-slate-800 dark:text-slate-200">
                    {activeTopic.formula}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
                      <strong className="block text-emerald-700 dark:text-emerald-300 mb-1">✓ {t('gram_correct_example')}</strong>
                      <span>{activeTopic.example_correct}</span>
                    </div>
                    <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30">
                      <strong className="block text-rose-700 dark:text-rose-300 mb-1">✗ {t('gram_incorrect_example')}</strong>
                      <span>{activeTopic.example_incorrect}</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  {exercises.map((ex, i) => {
                    const result = answers[ex.id];
                    return (
                      <div key={ex.id} className="bento-card p-5 space-y-3">
                        <p className="font-bold text-sm text-slate-900 dark:text-white">
                          {i + 1}. {ex.prompt}
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {ex.options.map((opt) => (
                            <button
                              key={opt}
                              type="button"
                              disabled={Boolean(result)}
                              onClick={() => void submitExercise(ex.id, opt)}
                              className="btn ghost sm justify-start text-left"
                            >
                              {opt}
                            </button>
                          ))}
                        </div>
                        {result && (
                          <div className={`p-3 rounded-xl text-xs space-y-1 ${
                            result.is_correct
                              ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                              : 'bg-rose-500/10 text-rose-700 dark:text-rose-300'
                          }`}>
                            <div className="font-bold flex items-center gap-1.5">
                              {result.is_correct ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                              <span>{result.correct_answer}</span>
                            </div>
                            <p className="m-0">{result.explanation}</p>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
