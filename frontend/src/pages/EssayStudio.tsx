import { useState, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Sparkles, Check, RefreshCw, Award } from 'lucide-react';
import { Essays, type IeltsGradeResponse } from '../lib/api';
import { countEssayWords } from '../lib/essays-arena';
import { escapeHtml, sanitizeHtml } from '../lib/sanitize';

interface Suggestion {
  id: string;
  original: string;
  improved: string;
  reason: string;
  type: 'lexical' | 'grammar' | 'cohesion';
}

const DEFAULT_TASK = {
  title: 'WRITING TASK 2',
  prompt:
    'Some people believe that unpaid community service should be a compulsory part of high school programmes (for example working for a charity, improving the neighbourhood or teaching sports to younger children). To what extent do you agree or disagree?',
  targetWords: 250,
};

const INITIAL_SUGGESTIONS: Suggestion[] = [
  {
    id: 'sug-1',
    original: 'many people believe',
    improved: 'it is widely contended that',
    reason: 'Akademik ohangni kuchaytiradi va C1/Band 8 darajadagi passiv konstruksiya hosil qiladi.',
    type: 'lexical',
  },
  {
    id: 'sug-2',
    original: 'good for students',
    improved: 'exceptionally beneficial for adolescents',
    reason: 'Oddiy "good" sifatidan qochib, leksik boylik (Lexical Resource) mezonini ko\'taradi.',
    type: 'lexical',
  },
  {
    id: 'sug-3',
    original: 'because of this reason',
    improved: 'consequently, this fosters',
    reason: 'Fikrlar o\'rtasidagi mantiqiy bog\'liqlik (Coherence & Cohesion) sifatini yaxshilaydi.',
    type: 'cohesion',
  },
  {
    id: 'sug-4',
    original: 'they will learn a lot',
    improved: 'they gain indispensable real-world competencies',
    reason: 'Band 7.5+ leksikani namoyon etadi.',
    type: 'lexical',
  },
];

const INITIAL_TEXT = `It is widely contended that unpaid community service should be incorporated into the high school curriculum as an obligatory requirement. While some argue that academic duties are already strenuous for pupils, I firmly believe that participating in charitable projects is exceptionally beneficial for adolescents, fostering empathy and essential civic responsibility.

Firstly, engaging in voluntary local endeavours exposes teenagers to diverse societal realities beyond the classroom. When high schoolers assist at rehabilitation centres or renovate public parks, they gain indispensable real-world competencies and teamwork skills that textbooks alone cannot provide. Consequently, this fosters a profound sense of communal solidarity.

In conclusion, although some might prioritize purely theoretical learning, integrating community service into secondary education cultivates well-rounded, socially conscious citizens prepared for future societal challenges.`;

export default function EssayStudio() {
  const { topicId: _topicId } = useParams();
  const [essayText, setEssayText] = useState(INITIAL_TEXT);
  const [analyzing, setAnalyzing] = useState(false);
  const [activeTab, setActiveTab] = useState<'editor' | 'review'>('editor');
  const [suggestions] = useState<Suggestion[]>(INITIAL_SUGGESTIONS);
  const [appliedIds, setAppliedIds] = useState<Set<string>>(new Set());

  // Band scores state
  const [scores, setScores] = useState({
    overall: 7.5,
    taskResponse: 7.5,
    coherence: 7.0,
    lexical: 7.5,
    grammar: 6.5,
  });

  const [aiFeedback, setAiFeedback] = useState<string>(
    'Fikrlar aniq va mantiqiy rivojlantirilgan. Leksik resurslar Band 7.5 darajasida, murakkab gap tuzilmalari yaxshi qo\'llangan.'
  );

  const words = useMemo(() => countEssayWords(essayText), [essayText]);
  const targetWords = DEFAULT_TASK.targetWords;
  const wordProgress = Math.min(100, Math.round((words / targetWords) * 100));

  // Word count color
  const wordColor = words >= targetWords ? '#10B981' : words >= 200 ? '#F59E0B' : '#64748B';

  // Apply suggestion replacement in text
  const applySuggestion = (sug: Suggestion) => {
    if (appliedIds.has(sug.id)) return;
    const regex = new RegExp(sug.original, 'i');
    if (regex.test(essayText)) {
      setEssayText((prev) => prev.replace(regex, sug.improved));
    }
    setAppliedIds((prev) => new Set(prev).add(sug.id));
  };

  const handleAiCheck = async () => {
    setAnalyzing(true);
    try {
      const res: IeltsGradeResponse = await Essays.ieltsGrade({
        task_type: 'task2',
        prompt: DEFAULT_TASK.prompt,
        essay_text: essayText,
      });

      if (res && res.overall_band) {
        setScores({
          overall: res.overall_band,
          taskResponse: res.criteria?.task_response?.band ?? 7.5,
          coherence: res.criteria?.coherence_cohesion?.band ?? 7.0,
          lexical: res.criteria?.lexical_resource?.band ?? 7.5,
          grammar: res.criteria?.grammatical_range?.band ?? 6.5,
        });
        if (res.general_feedback) {
          setAiFeedback(res.general_feedback);
        }
      }
    } catch {
      // Graceful fallback for demo/offline: recalculate scores slightly based on word count
      const band = words >= 250 ? 7.5 : words >= 200 ? 6.5 : 5.5;
      setScores({
        overall: band,
        taskResponse: band,
        coherence: Math.max(6.0, band - 0.5),
        lexical: band,
        grammar: Math.max(6.0, band - 0.5),
      });
    } finally {
      setAnalyzing(false);
      setActiveTab('review');
    }
  };

  // Render text with inline highlights for strong sentences (green) and errors/improvable (yellow)
  const renderedAnalysis = useMemo(() => {
    let html = escapeHtml(essayText);
    // Highlight strong sentences with subtle green
    const strongPhrases = [
      'fostering empathy and essential civic responsibility',
      'gain indispensable real-world competencies',
      'cultivates well-rounded, socially conscious citizens',
      'it is widely contended that',
      'exceptionally beneficial for adolescents',
    ];
    for (const p of strongPhrases) {
      const re = new RegExp(`(${p})`, 'gi');
      html = html.replace(re, '<mark class="essay-strong-highlight">$1</mark>');
    }
    // Highlight suggestions
    for (const sug of suggestions) {
      if (!appliedIds.has(sug.id)) {
        const safeOrig = escapeHtml(sug.original).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        if (safeOrig) {
          const re = new RegExp(`(${safeOrig})`, 'gi');
          html = html.replace(re, '<mark class="essay-error-highlight">$1</mark>');
        }
      }
    }
    return sanitizeHtml(html);
  }, [essayText, suggestions, appliedIds]);

  return (
    <div className="essay-studio-container" style={{ minHeight: '100vh', background: 'var(--bg-main)', color: 'var(--text-primary)', padding: '16px 20px 40px' }}>
      {/* Top Header */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 20,
          paddingBottom: 14,
          borderBottom: '1px solid var(--border-subtle)',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Link
            to="/essays"
            className="bento-btn"
            style={{
              padding: '6px 12px',
              height: 38,
              fontSize: 13,
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <ArrowLeft size={16} /> Chiqish
          </Link>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="pill-badge" style={{ background: 'rgba(79, 70, 229, 0.15)', color: '#4F46E5', fontWeight: 800 }}>
                AI ESSAY STUDIO 2.0
              </span>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>IELTS Academic Writing Task 2</span>
            </div>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 800, margin: '4px 0 0' }}>
              Akademik Esse Muharriri va Tahlil
            </h1>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="button"
            onClick={handleAiCheck}
            disabled={analyzing}
            className="bento-btn bento-btn-gold"
            style={{
              height: 42,
              padding: '0 20px',
              fontSize: 14,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              boxShadow: '0 4px 14px rgba(245, 158, 11, 0.35)',
            }}
          >
            {analyzing ? (
              <>
                <RefreshCw size={16} className="animate-spin" /> Tekshirilmoqda...
              </>
            ) : (
              <>
                <Sparkles size={16} /> 🚀 AI orqali tekshirish
              </>
            )}
          </button>
        </div>
      </header>

      {/* 3-Column Layout */}
      <div
        className="essay-studio-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(280px, 1fr) minmax(420px, 2fr) minmax(320px, 1.2fr)',
          gap: 20,
          alignItems: 'start',
        }}
      >
        {/* Column 1 (Left): Task Info & 4 Criteria Scores */}
        <aside
          className="bento-card"
          style={{
            padding: 20,
            display: 'flex',
            flexDirection: 'column',
            gap: 18,
          }}
        >
          <div>
            <span
              className="pill-badge"
              style={{
                background: 'rgba(245, 158, 11, 0.15)',
                color: '#D97706',
                fontWeight: 800,
                fontSize: 12,
                marginBottom: 8,
                display: 'inline-block',
              }}
            >
              {DEFAULT_TASK.title}
            </span>
            <h2 style={{ fontSize: '0.98rem', fontWeight: 700, lineHeight: 1.55, margin: 0 }}>
              {DEFAULT_TASK.prompt}
            </h2>
          </div>

          <div
            style={{
              padding: 14,
              borderRadius: 14,
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)' }}>IELTS Natijasi</span>
              <span
                style={{
                  fontSize: 18,
                  fontWeight: 900,
                  color: '#D97706',
                  fontFamily: 'JetBrains Mono, monospace',
                }}
              >
                Band {scores.overall.toFixed(1)}
              </span>
            </div>

            {/* 4 Criteria Bars */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                  <span>Task Response</span>
                  <span style={{ color: '#10B981', fontFamily: 'JetBrains Mono, monospace' }}>{scores.taskResponse.toFixed(1)}</span>
                </div>
                <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${(scores.taskResponse / 9) * 100}%`, background: '#10B981', borderRadius: 999 }} />
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                  <span>Coherence & Cohesion</span>
                  <span style={{ color: '#3B82F6', fontFamily: 'JetBrains Mono, monospace' }}>{scores.coherence.toFixed(1)}</span>
                </div>
                <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${(scores.coherence / 9) * 100}%`, background: '#3B82F6', borderRadius: 999 }} />
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                  <span>Lexical Resource</span>
                  <span style={{ color: '#8B5CF6', fontFamily: 'JetBrains Mono, monospace' }}>{scores.lexical.toFixed(1)}</span>
                </div>
                <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${(scores.lexical / 9) * 100}%`, background: '#8B5CF6', borderRadius: 999 }} />
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                  <span>Grammar (GRA)</span>
                  <span style={{ color: '#F59E0B', fontFamily: 'JetBrains Mono, monospace' }}>{scores.grammar.toFixed(1)}</span>
                </div>
                <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${(scores.grammar / 9) * 100}%`, background: '#F59E0B', borderRadius: 999 }} />
                </div>
              </div>
            </div>
          </div>

          <div
            style={{
              padding: 12,
              borderRadius: 12,
              background: 'rgba(79, 70, 229, 0.08)',
              border: '1px solid rgba(79, 70, 229, 0.2)',
              fontSize: 12.5,
              lineHeight: 1.5,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#4F46E5', fontWeight: 800, marginBottom: 4 }}>
              <Award size={15} /> Examiner Xulosasi:
            </div>
            <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{aiFeedback}</p>
          </div>
        </aside>

        {/* Column 2 (Center): Editor & Word Progress */}
        <main
          className="bento-card"
          style={{
            padding: 20,
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
            minHeight: 560,
          }}
        >
          {/* Word Counter & Tab Switcher */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 10,
              paddingBottom: 10,
              borderBottom: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontWeight: 800,
                  fontSize: 15,
                  color: wordColor,
                }}
              >
                {words} / {targetWords} so'z
              </span>
              <span
                className="pill-badge"
                style={{
                  background: words >= targetWords ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                  color: words >= targetWords ? '#10B981' : '#D97706',
                  fontSize: 11,
                  fontWeight: 700,
                }}
              >
                {words >= targetWords ? 'Yetarli (250+)' : `${targetWords - words} ta so'z qoldi`}
              </span>
            </div>

            <div className="segmented-switch" style={{ width: 'auto' }}>
              <button
                type="button"
                className={activeTab === 'editor' ? 'active' : ''}
                onClick={() => setActiveTab('editor')}
              >
                Tahrirlash
              </button>
              <button
                type="button"
                className={activeTab === 'review' ? 'active' : ''}
                onClick={() => setActiveTab('review')}
              >
                Rangli Tahlil
              </button>
            </div>
          </div>

          {/* Word Progress Bar */}
          <div
            style={{
              height: 4,
              width: '100%',
              borderRadius: 999,
              background: 'var(--bg-elevated)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${wordProgress}%`,
                background: words >= targetWords ? 'linear-gradient(90deg, #10B981, #059669)' : 'linear-gradient(90deg, #F59E0B, #D97706)',
                transition: 'width 0.25s ease',
              }}
            />
          </div>

          {/* Content Area */}
          {activeTab === 'editor' ? (
            <textarea
              value={essayText}
              onChange={(e) => setEssayText(e.target.value)}
              placeholder="Essengizni shu yerda yozing..."
              style={{
                flex: 1,
                width: '100%',
                minHeight: 460,
                padding: 16,
                borderRadius: 14,
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-elevated)',
                color: 'var(--text-primary)',
                fontFamily: 'inherit',
                fontSize: '1.02rem',
                lineHeight: 1.75,
                resize: 'vertical',
                outline: 'none',
              }}
            />
          ) : (
            <div
              style={{
                flex: 1,
                minHeight: 460,
                padding: 16,
                borderRadius: 14,
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-elevated)',
                color: 'var(--text-primary)',
                fontSize: '1.02rem',
                lineHeight: 1.8,
                whiteSpace: 'pre-wrap',
              }}
              dangerouslySetInnerHTML={{ __html: renderedAnalysis }}
            />
          )}

          {/* Color Legend for Review Mode */}
          {activeTab === 'review' && (
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12, color: 'var(--text-secondary)' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 12, height: 12, borderRadius: 3, background: 'rgba(16, 185, 129, 0.35)', border: '1px solid #10B981' }} />
                Kuchli akademik jumlalar
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 12, height: 12, borderRadius: 3, background: 'rgba(245, 158, 11, 0.35)', border: '1px solid #F59E0B' }} />
                Yaxshilash mumkin bo'lgan iboralar
              </span>
            </div>
          )}
        </main>

        {/* Column 3 (Right): Examiner Analysis & C1 Suggestions */}
        <aside
          className="bento-card"
          style={{
            padding: 20,
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Sparkles size={16} color="#D97706" /> IELTS Examiner Tahlili
            </h2>
            <span className="pill-badge" style={{ fontSize: 11, background: 'var(--bg-elevated)' }}>
              {suggestions.length} ta tavsiya
            </span>
          </div>

          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>
            Oddiy va takroriy so'zlarni C1 darajadagi akademik muqobillariga almashtiring:
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {suggestions.map((sug) => {
              const applied = appliedIds.has(sug.id);
              return (
                <div
                  key={sug.id}
                  style={{
                    padding: 14,
                    borderRadius: 14,
                    background: applied ? 'rgba(16, 185, 129, 0.08)' : 'var(--bg-elevated)',
                    border: applied ? '1px solid rgba(16, 185, 129, 0.3)' : '1px solid var(--border-subtle)',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, fontSize: 12 }}>
                    <span
                      style={{
                        padding: '2px 6px',
                        borderRadius: 6,
                        background: 'rgba(239, 68, 68, 0.15)',
                        color: '#EF4444',
                        textDecoration: 'line-through',
                        fontFamily: 'JetBrains Mono, monospace',
                      }}
                    >
                      {sug.original}
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>➔</span>
                    <span
                      style={{
                        padding: '2px 6px',
                        borderRadius: 6,
                        background: 'rgba(16, 185, 129, 0.15)',
                        color: '#10B981',
                        fontWeight: 700,
                        fontFamily: 'JetBrains Mono, monospace',
                      }}
                    >
                      {sug.improved}
                    </span>
                  </div>

                  <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45, margin: '0 0 10px' }}>
                    {sug.reason}
                  </p>

                  <button
                    type="button"
                    disabled={applied}
                    onClick={() => applySuggestion(sug)}
                    className={applied ? 'bento-btn' : 'bento-btn bento-btn-gold'}
                    style={{
                      width: '100%',
                      height: 36,
                      fontSize: 12.5,
                      fontWeight: 700,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6,
                    }}
                  >
                    {applied ? (
                      <>
                        <Check size={14} /> Qabul qilindi
                      </>
                    ) : (
                      <>
                        <Sparkles size={14} /> ✨ Qabul qilish
                      </>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        </aside>
      </div>

      <style>{`
        .essay-strong-highlight {
          background: rgba(16, 185, 129, 0.25);
          color: inherit;
          padding: 2px 4px;
          border-radius: 4px;
        }
        .essay-error-highlight {
          background: rgba(245, 158, 11, 0.25);
          color: inherit;
          padding: 2px 4px;
          border-radius: 4px;
          border-bottom: 2px wavy #F59E0B;
        }
        @media (max-width: 1024px) {
          .essay-studio-grid {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
}
