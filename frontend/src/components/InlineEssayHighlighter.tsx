import { useMemo, useState } from 'react';
import { Sparkles, Check, X, AlertCircle } from 'lucide-react';

export interface HighlightError {
  word: string;
  correction: string;
  explanation?: string;
  type?: 'spelling' | 'grammar' | 'style' | string;
}

export interface InlineEssayHighlighterProps {
  essayText: string;
  errors?: HighlightError[];
  strengths?: string[];
  onApplyFix?: (error: HighlightError) => void;
  title?: string;
  readOnly?: boolean;
}

interface TextSegment {
  start: number;
  end: number;
  type: 'error' | 'strength';
  errorData?: HighlightError;
  strengthData?: string;
}

const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export default function InlineEssayHighlighter({
  essayText,
  errors = [],
  strengths = [],
  onApplyFix,
  title = "Esse Matni Ustida Rangli Tahlil",
  readOnly = false,
}: InlineEssayHighlighterProps) {
  const [activeError, setActiveError] = useState<HighlightError | null>(null);
  const [hoveredStrength, setHoveredStrength] = useState<string | null>(null);

  // Compute non-overlapping highlights
  const segments = useMemo(() => {
    if (!essayText) return [];

    const rawSegments: TextSegment[] = [];

    // 1. Find all error locations
    for (const err of errors) {
      if (!err || !err.word || !err.word.trim()) continue;
      const target = err.word.trim();
      try {
        const re = new RegExp(`(?<![\\p{L}\\p{N}])${escapeRegex(target)}(?![\\p{L}\\p{N}])`, 'giu');
        let m: RegExpExecArray | null;
        while ((m = re.exec(essayText)) !== null) {
          rawSegments.push({
            start: m.index,
            end: m.index + m[0].length,
            type: 'error',
            errorData: err,
          });
        }
      } catch {
        // Fallback simple search
        let pos = 0;
        const lowerText = essayText.toLowerCase();
        const lowerTarget = target.toLowerCase();
        while (pos < lowerText.length) {
          const idx = lowerText.indexOf(lowerTarget, pos);
          if (idx === -1) break;
          rawSegments.push({
            start: idx,
            end: idx + target.length,
            type: 'error',
            errorData: err,
          });
          pos = idx + target.length;
        }
      }
    }

    // 2. Find strength phrases/sentences
    for (const str of strengths) {
      if (!str || typeof str !== 'string' || str.trim().length < 5) continue;
      const trimmed = str.trim();
      // Check if strength exists verbatim or as a quote
      const quotesMatch = trimmed.match(/["“«']([^"”»']+)["”»']/);
      const searchPhrase = quotesMatch ? quotesMatch[1] : trimmed;
      if (searchPhrase.length < 5) continue;

      let pos = 0;
      const lowerText = essayText.toLowerCase();
      const lowerSearch = searchPhrase.toLowerCase();
      while (pos < lowerText.length) {
        const idx = lowerText.indexOf(lowerSearch, pos);
        if (idx === -1) break;
        rawSegments.push({
          start: idx,
          end: idx + searchPhrase.length,
          type: 'strength',
          strengthData: trimmed,
        });
        pos = idx + searchPhrase.length;
      }
    }

    // Sort by start index ascending, errors take priority over strengths on tie
    rawSegments.sort((a, b) => {
      if (a.start !== b.start) return a.start - b.start;
      if (a.type === 'error' && b.type !== 'error') return -1;
      if (b.type === 'error' && a.type !== 'error') return 1;
      return (b.end - b.start) - (a.end - a.start);
    });

    // Remove overlapping intervals
    const clean: TextSegment[] = [];
    let lastEnd = 0;
    for (const seg of rawSegments) {
      if (seg.start >= lastEnd) {
        clean.push(seg);
        lastEnd = seg.end;
      }
    }

    return clean;
  }, [essayText, errors, strengths]);

  // Build rendered tokens
  const renderedContent = useMemo(() => {
    if (!essayText) return null;
    if (segments.length === 0) {
      return <span>{essayText}</span>;
    }

    const tokens: React.ReactNode[] = [];
    let cursor = 0;

    segments.forEach((seg, idx) => {
      // Plain text before segment
      if (seg.start > cursor) {
        tokens.push(
          <span key={`plain-${cursor}`}>{essayText.slice(cursor, seg.start)}</span>
        );
      }

      const chunk = essayText.slice(seg.start, seg.end);

      if (seg.type === 'error' && seg.errorData) {
        const err = seg.errorData;
        const isSelected = activeError?.word.toLowerCase() === err.word.toLowerCase();
        tokens.push(
          <button
            key={`err-${seg.start}-${idx}`}
            type="button"
            onClick={() => setActiveError(isSelected ? null : err)}
            className={`inline-block px-1.5 py-0.5 mx-0.5 rounded cursor-pointer transition-all border-b-2 text-left font-medium ${
              isSelected
                ? 'bg-red-500/35 border-red-400 text-white shadow-sm ring-2 ring-red-400/40'
                : 'bg-red-500/20 border-b border-red-400 text-red-200 hover:bg-red-500/30'
            }`}
            title={`Xato: "${err.word}" → "${err.correction}". Tafsilotlar uchun bosing.`}
          >
            {chunk}
          </button>
        );
      } else if (seg.type === 'strength') {
        tokens.push(
          <span
            key={`str-${seg.start}-${idx}`}
            onMouseEnter={() => setHoveredStrength(seg.strengthData || 'Kuchli argument')}
            onMouseLeave={() => setHoveredStrength(null)}
            className="inline-block px-1.5 py-0.5 mx-0.5 rounded border-b-2 bg-emerald-500/20 border-emerald-400 text-emerald-200 font-medium transition-all hover:bg-emerald-500/30 cursor-help"
            title="🌟 Kuchli argument / Yuqori darajadagi jumla"
          >
            {chunk}
          </span>
        );
      }

      cursor = seg.end;
    });

    if (cursor < essayText.length) {
      tokens.push(<span key={`plain-${cursor}`}>{essayText.slice(cursor)}</span>);
    }

    return tokens;
  }, [essayText, segments, activeError]);

  return (
    <div
      style={{
        borderRadius: 20,
        background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.9) 100%)',
        border: '1.5px solid rgba(245, 158, 11, 0.25)',
        padding: '22px 20px',
        boxShadow: '0 12px 30px rgba(0, 0, 0, 0.35)',
        position: 'relative',
      }}
    >
      {/* Header & Stats */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
          borderBottom: '1px solid rgba(148, 163, 184, 0.15)',
          paddingBottom: 16,
          marginBottom: 16,
        }}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#F8FAFC', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span>🎨</span>
            <span>{title}</span>
          </h3>
          <p style={{ margin: '3px 0 0', fontSize: 12, color: '#94A3B8' }}>
            Qizil chiziqlar — imlo, grammatika va uslub xatolari; yashil chiziqlar — kuchli argumentlar
          </p>
        </div>

        {/* Legend Pills */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <div
            style={{
              padding: '4px 10px',
              borderRadius: 8,
              background: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid rgba(239, 68, 68, 0.35)',
              color: '#FCA5A5',
              fontSize: 12,
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: 5,
            }}
          >
            <span>🔴</span>
            <span>{errors.length} ta xato</span>
          </div>

          <div
            style={{
              padding: '4px 10px',
              borderRadius: 8,
              background: 'rgba(16, 185, 129, 0.15)',
              border: '1px solid rgba(16, 185, 129, 0.35)',
              color: '#6EE7B7',
              fontSize: 12,
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: 5,
            }}
          >
            <span>🟢</span>
            <span>{strengths.length} ta kuchli tomon</span>
          </div>
        </div>
      </div>

      {/* Strength Hover Tooltip */}
      {hoveredStrength && (
        <div
          style={{
            marginBottom: 14,
            padding: '10px 14px',
            borderRadius: 12,
            background: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid rgba(16, 185, 129, 0.4)',
            color: '#A7F3D0',
            fontSize: 13,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Sparkles size={16} color="#34D399" />
          <span>
            <b>Kuchli argument / Boy lug‘at:</b> {hoveredStrength}
          </span>
        </div>
      )}

      {/* Active Error Popover Card */}
      {activeError && (
        <div
          style={{
            marginBottom: 16,
            padding: '14px 18px',
            borderRadius: 14,
            background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.18) 0%, rgba(15, 23, 42, 0.95) 100%)',
            border: '1.5px solid rgba(239, 68, 68, 0.45)',
            boxShadow: '0 8px 24px rgba(239, 68, 68, 0.25)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 800, color: '#F87171' }}>
              <AlertCircle size={16} />
              <span>
                {activeError.type === 'spelling'
                  ? 'Imlo xatosi'
                  : activeError.type === 'grammar'
                  ? 'Grammatika xatosi'
                  : 'Uslubiy tavsiya'}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setActiveError(null)}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#94A3B8',
                cursor: 'pointer',
                padding: 4,
              }}
              title="Yopish"
            >
              <X size={16} />
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
            <div style={{ background: 'rgba(0, 0, 0, 0.3)', padding: '8px 12px', borderRadius: 8 }}>
              <span style={{ fontSize: 11, color: '#94A3B8', display: 'block' }}>Talaba yozgan:</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: '#FCA5A5', textDecoration: 'line-through' }}>
                {activeError.word}
              </span>
            </div>
            <div style={{ background: 'rgba(16, 185, 129, 0.15)', padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(16, 185, 129, 0.3)' }}>
              <span style={{ fontSize: 11, color: '#A7F3D0', display: 'block' }}>To‘g‘ri variant:</span>
              <span style={{ fontSize: 14, fontWeight: 800, color: '#34D399' }}>
                {activeError.correction}
              </span>
            </div>
          </div>

          {activeError.explanation && (
            <p style={{ margin: 0, fontSize: 12.5, color: '#E2E8F0', lineHeight: 1.5 }}>
              💡 <b>Izoh:</b> {activeError.explanation}
            </p>
          )}

          {!readOnly && onApplyFix && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
              <button
                type="button"
                onClick={() => {
                  onApplyFix(activeError);
                  setActiveError(null);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '7px 14px',
                  borderRadius: 8,
                  background: 'linear-gradient(135deg, #10B981, #059669)',
                  color: '#FFFFFF',
                  fontWeight: 800,
                  fontSize: 12.5,
                  border: 'none',
                  cursor: 'pointer',
                  boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
                }}
              >
                <Check size={14} />
                <span>To‘g‘rilashni qo‘llash</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* Main Text Content */}
      <div
        style={{
          lineHeight: 1.85,
          fontSize: '1.02rem',
          color: '#F1F5F9',
          whiteSpace: 'pre-line',
          wordBreak: 'break-word',
          background: 'rgba(15, 23, 42, 0.55)',
          padding: '18px 20px',
          borderRadius: 14,
          border: '1px solid rgba(148, 163, 184, 0.12)',
        }}
      >
        {renderedContent || <span style={{ color: '#94A3B8' }}>Esse matni topilmadi.</span>}
      </div>
    </div>
  );
}
