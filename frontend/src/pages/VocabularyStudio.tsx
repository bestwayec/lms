import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, BookOpen, CheckCircle2, Sparkles, XCircle } from 'lucide-react';
import PronounceButton from '../components/english/PronounceButton';
import { useLang } from '../i18n/LangContext';
import { apiFetch } from '../lib/api';

interface VocabCard {
  id: number;
  word: string;
  meaning: string;
  definition: string;
  streak: number;
  mistake_count: number;
  is_mastered: boolean;
}

interface VocabQuizQuestion {
  id: number;
  token: string;
  type: 'listen_choose' | 'listen_type' | 'fill_blank' | 'context_meaning' | 'synonym';
  audio_url?: string | null;
  pronunciation_text?: string | null;
  prompt: string;
  context_sentence?: string | null;
  options: string[];
  first_letter?: string;
  hint_length?: number;
  streak: number;
}

export default function VocabularyStudio() {
  const { t } = useLang();
  const [tab, setTab] = useState<'deck' | 'quiz'>('deck');
  const [cards, setCards] = useState<VocabCard[]>([]);
  const [dueCount, setDueCount] = useState(0);
  const [masteredCount, setMasteredCount] = useState(0);
  const [questions, setQuestions] = useState<VocabQuizQuestion[]>([]);
  const [qIdx, setQIdx] = useState(0);
  const [typedAnswer, setTypedAnswer] = useState('');
  const [feedback, setFeedback] = useState<{ is_correct: boolean; correct_answer: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiFetch<{ due_count: number; mastered_count: number; cards: VocabCard[] }>('/api/v1/vocabulary/deck/'),
      apiFetch<{ status: string; questions: VocabQuizQuestion[] }>('/api/v1/vocabulary/student-quiz/'),
    ])
      .then(([deckRes, quizRes]) => {
        if (!active) return;
        setCards(deckRes.cards || []);
        setDueCount(deckRes.due_count || 0);
        setMasteredCount(deckRes.mastered_count || 0);
        setQuestions(quizRes.questions || []);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const currentQ = questions[qIdx];

  const submitAnswer = async (ans: string) => {
    if (!currentQ || !ans.trim()) return;
    const res = await apiFetch<{
      ok: boolean;
      is_correct: boolean;
      correct_answer: string;
      due_count?: number;
      mastered_count?: number;
      streak?: number;
    }>('/api/v1/vocabulary/student-quiz/submit/', {
      method: 'POST',
      body: JSON.stringify({
        id: currentQ.id,
        token: currentQ.token,
        word: currentQ.pronunciation_text || (currentQ.type !== 'fill_blank' ? currentQ.prompt : '') || '',
        type: currentQ.type,
        answer: ans.trim(),
      }),
    });
    setFeedback({ is_correct: res.is_correct, correct_answer: res.correct_answer });
    if (typeof res.due_count === 'number') {
      setDueCount(res.due_count);
    }
    if (typeof res.mastered_count === 'number') {
      setMasteredCount(res.mastered_count);
    }
  };

  const nextQuestion = () => {
    setFeedback(null);
    setTypedAnswer('');
    setQIdx((prev) => (prev + 1 < questions.length ? prev + 1 : 0));
  };

  return (
    <div className="max-w-[1100px] mx-auto w-full px-3 sm:px-6 py-4 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to="/english" className="btn ghost sm">
            <ArrowLeft size={15} /> {t('english_center_title')}
          </Link>
          <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
            <BookOpen size={20} className="text-indigo-600 dark:text-indigo-400" />
            <span>{t('voc_studio_title')}</span>
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className={`btn sm ${tab === 'deck' ? 'primary' : 'ghost'}`} onClick={() => setTab('deck')}>
            {t('voc_flashcards_tab')} ({cards.length})
          </button>
          <button type="button" className={`btn sm ${tab === 'quiz' ? 'primary' : 'ghost'}`} onClick={() => setTab('quiz')}>
            <Sparkles size={14} /> {t('voc_quiz_tab')} ({questions.length})
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="bento-card p-4">
          <div className="text-xs text-slate-500 dark:text-slate-400">{t('voc_due_review')}</div>
          <div className="text-2xl font-black text-amber-600 dark:text-amber-400">{dueCount}</div>
        </div>
        <div className="bento-card p-4">
          <div className="text-xs text-slate-500 dark:text-slate-400">{t('voc_mastered')}</div>
          <div className="text-2xl font-black text-emerald-600 dark:text-emerald-400">{masteredCount}</div>
        </div>
        <div className="bento-card p-4 col-span-2 sm:col-span-1 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500 dark:text-slate-400">{t('gram_studio_title')}</div>
            <Link to="/grammar" className="text-sm font-bold text-indigo-600 dark:text-indigo-400 hover:underline">
              {t('gram_open_studio')} →
            </Link>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="bento-card p-8 text-center muted">{t('loading')}</div>
      ) : tab === 'deck' ? (
        cards.length === 0 ? (
          <div className="bento-card p-8 text-center text-sm text-slate-600 dark:text-slate-400">
            {t('voc_deck_empty')}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {cards.map((c) => (
              <div key={c.id} className="bento-card p-4 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <strong className="text-base font-extrabold text-slate-900 dark:text-white">{c.word}</strong>
                  <PronounceButton word={c.word} />
                </div>
                <p className="text-sm text-slate-700 dark:text-slate-200">{c.meaning}</p>
                {c.definition && c.definition !== c.meaning && (
                  <p className="text-xs text-slate-500 dark:text-slate-400">{c.definition}</p>
                )}
                <div className="text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                  {c.is_mastered ? `✓ ${t('voc_mastered')}` : `${c.streak}/3`}
                </div>
              </div>
            ))}
          </div>
        )
      ) : !currentQ ? (
        <div className="bento-card p-8 text-center text-sm text-slate-600 dark:text-slate-400">
          {t('voc_deck_empty')}
        </div>
      ) : (
        <div className="bento-card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <span className="badge blue">{currentQ.type}</span>
            <span className="muted small">
              {qIdx + 1} / {questions.length}
            </span>
          </div>

          {currentQ.pronunciation_text && (
            <div>
              <PronounceButton
                word={currentQ.pronunciation_text}
                audioUrl={currentQ.audio_url}
                doublePlay
              />
            </div>
          )}

          {currentQ.prompt && (
            <p className="text-base font-bold text-slate-900 dark:text-white">{currentQ.prompt}</p>
          )}
          {currentQ.context_sentence && (
            <p className="text-sm italic text-slate-600 dark:text-slate-300">{currentQ.context_sentence}</p>
          )}

          {currentQ.options.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {currentQ.options.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  className="btn ghost text-left justify-start"
                  disabled={Boolean(feedback)}
                  onClick={() => void submitAnswer(opt)}
                >
                  {opt}
                </button>
              ))}
            </div>
          ) : (
            <form
              className="flex flex-wrap gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void submitAnswer(typedAnswer);
              }}
            >
              <input
                type="text"
                className="input flex-1"
                value={typedAnswer}
                onChange={(e) => setTypedAnswer(e.target.value)}
                placeholder={currentQ.first_letter ? `${currentQ.first_letter}...` : '...'}
                disabled={Boolean(feedback)}
              />
              <button type="submit" className="btn primary" disabled={Boolean(feedback) || !typedAnswer.trim()}>
                {t('submit')}
              </button>
            </form>
          )}

          {feedback && (
            <div className={`p-3 rounded-xl border text-sm flex items-center justify-between gap-3 ${
              feedback.is_correct
                ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                : 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300'
            }`}>
              <span className="flex items-center gap-2 font-bold">
                {feedback.is_correct ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                <span>{feedback.correct_answer}</span>
              </span>
              <button type="button" className="btn sm primary" onClick={nextQuestion}>
                {t('next')} →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
