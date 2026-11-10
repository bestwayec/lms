import { useState } from 'react';
import { X, Search } from 'lucide-react';

interface SolubilityTableModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// Cations (vertical or horizontal)
const CATIONS = ['H⁺', 'Li⁺', 'Na⁺', 'K⁺', 'NH₄⁺', 'Mg²⁺', 'Ca²⁺', 'Ba²⁺', 'Al³⁺', 'Fe²⁺', 'Fe³⁺', 'Cu²⁺', 'Zn²⁺', 'Pb²⁺', 'Ag⁺'];

// Anions
const ANIONS = ['OH⁻', 'NO₃⁻', 'Cl⁻', 'Br⁻', 'I⁻', 'S²⁻', 'SO₃²⁻', 'SO₄²⁻', 'CO₃²⁻', 'SiO₃²⁻', 'PO₄³⁻'];

// Solubility matrix: [anionIndex][cationIndex] -> 'E' | 'K' | 'CH' | '-'
// E: Eruvchan, K: Kam eruvchan, CH: Cho'kma, -: Suvda parchalanadi yoki mavjud emas
const MATRIX: string[][] = [
  // OH-
  ['E', 'E', 'E', 'E', 'E', 'CH', 'K', 'E', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH', '-'],
  // NO3-
  ['E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E'],
  // Cl-
  ['E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'K', 'CH'],
  // Br-
  ['E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'K', 'CH'],
  // I-
  ['E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'E', 'K', 'CH'],
  // S2-
  ['E', 'E', 'E', 'E', 'E', '-', '-', '-', '-', 'CH', '-', 'CH', 'CH', 'CH', 'CH'],
  // SO3 2-
  ['E', 'E', 'E', 'E', 'E', 'CH', 'CH', 'CH', '-', 'CH', '-', 'CH', 'CH', 'CH', 'CH'],
  // SO4 2-
  ['E', 'E', 'E', 'E', 'E', 'E', 'K', 'CH', 'E', 'E', 'E', 'E', 'E', 'CH', 'K'],
  // CO3 2-
  ['E', 'E', 'E', 'E', 'E', 'CH', 'CH', 'CH', '-', 'CH', '-', 'CH', 'CH', 'CH', 'CH'],
  // SiO3 2-
  ['CH', 'E', 'E', 'E', '-', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH'],
  // PO4 3-
  ['E', 'CH', 'E', 'E', 'E', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH', 'CH'],
];

const CELL_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  E: { bg: 'rgba(16, 185, 129, 0.18)', text: '#10b981', label: 'Eruvchan' },
  K: { bg: 'rgba(245, 158, 11, 0.22)', text: '#f59e0b', label: 'Kam eruvchan' },
  CH: { bg: 'rgba(239, 68, 68, 0.22)', text: '#ef4444', label: 'Cho‘kma' },
  '-': { bg: 'rgba(148, 163, 184, 0.12)', text: '#94a3b8', label: 'Parchalanadi / Mavjud emas' },
};

export default function SolubilityTableModal({ isOpen, onClose }: SolubilityTableModalProps) {
  const [filter, setFilter] = useState('');

  if (!isOpen) return null;

  const q = filter.trim().toUpperCase();

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/70 backdrop-blur-md animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="bento-card bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 sm:p-5 border-b border-slate-800 bg-slate-950/60 shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-2xl">💧</span>
            <div>
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                Tuzlar, asoslar va kislotalarning suvda eruvchanlik jadvali
              </h2>
              <p className="text-xs text-slate-400">Milliy Sertifikat va DTM kimyo imtihonlari uchun rasmiy ma’lumotnoma</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative hidden sm:block">
              <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Ionni izlash..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="pl-8 pr-3 py-1.5 text-xs rounded-xl bg-slate-800 border border-slate-700 text-white placeholder-slate-500 outline-none focus:border-emerald-500 font-mono"
              />
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              aria-label="Yopish"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-3 px-4 py-2 bg-slate-950/40 border-b border-slate-800/80 text-[11px] font-bold flex-wrap shrink-0">
          <span className="text-slate-400 uppercase tracking-wider text-[10px]">Belgilar:</span>
          <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            E — Eruvchan
          </span>
          <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
            K — Kam eruvchan
          </span>
          <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">
            CH — Cho‘kma
          </span>
          <span className="px-2 py-0.5 rounded bg-slate-700/40 text-slate-400 border border-slate-600/30">
            — — Parchalanadi / Mavjud emas
          </span>
        </div>

        {/* Table Content */}
        <div className="overflow-auto p-4 flex-1 font-mono text-xs">
          <table className="w-full border-collapse text-center">
            <thead>
              <tr className="sticky top-0 bg-slate-900 z-10">
                <th className="p-2 border border-slate-800 bg-slate-950/80 text-amber-400 font-bold">
                  Anion \ Kation
                </th>
                {CATIONS.map((c) => {
                  const match = q && c.toUpperCase().includes(q);
                  return (
                    <th
                      key={c}
                      className={`p-2 border border-slate-800 font-extrabold ${
                        match ? 'bg-emerald-500/30 text-emerald-300' : 'bg-slate-950/80 text-sky-400'
                      }`}
                    >
                      {c}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {ANIONS.map((anion, aIdx) => {
                const matchA = q && anion.toUpperCase().includes(q);
                return (
                  <tr key={anion} className={matchA ? 'bg-emerald-500/10' : ''}>
                    <td className="p-2 border border-slate-800 font-extrabold text-amber-300 bg-slate-950/50 sticky left-0 z-0">
                      {anion}
                    </td>
                    {CATIONS.map((cation, cIdx) => {
                      const val = MATRIX[aIdx]?.[cIdx] ?? 'E';
                      const st = CELL_STYLES[val] || CELL_STYLES['-'];
                      const isHighlighted = q && (cation.toUpperCase().includes(q) || anion.toUpperCase().includes(q));
                      return (
                        <td
                          key={cation}
                          className="p-2 border border-slate-800 font-bold text-center transition-colors"
                          style={{
                            background: isHighlighted ? 'rgba(16, 185, 129, 0.35)' : st.bg,
                            color: st.text,
                          }}
                          title={`${cation} + ${anion} → ${st.label}`}
                        >
                          {val}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs text-slate-400 shrink-0">
          <span>Har bir katak ustiga borganda birikmaning to‘liq xossasi ko‘rinadi.</span>
          <button
            type="button"
            onClick={onClose}
            className="bento-btn bento-btn-gold text-xs h-8 px-4 font-bold"
          >
            Yopish
          </button>
        </div>
      </div>
    </div>
  );
}
