import { useState } from 'react';
import { X } from 'lucide-react';

interface CalculatorModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function CalculatorModal({ isOpen, onClose }: CalculatorModalProps) {
  const [display, setDisplay] = useState('0');
  const [prev, setPrev] = useState<number | null>(null);
  const [op, setOp] = useState<string | null>(null);
  const [resetNext, setResetNext] = useState(false);

  if (!isOpen) return null;

  const handleDigit = (digit: string) => {
    if (display === '0' || resetNext) {
      setDisplay(digit);
      setResetNext(false);
    } else if (display.length < 12) {
      setDisplay(display + digit);
    }
  };

  const handleDot = () => {
    if (resetNext) {
      setDisplay('0.');
      setResetNext(false);
    } else if (!display.includes('.')) {
      setDisplay(display + '.');
    }
  };

  const handleClear = () => {
    setDisplay('0');
    setPrev(null);
    setOp(null);
    setResetNext(false);
  };

  const handleToggleSign = () => {
    const val = Number(display);
    if (!isNaN(val)) {
      setDisplay(String(-val));
    }
  };

  const handleSqrt = () => {
    const val = Number(display);
    if (val >= 0) {
      setDisplay(String(Math.sqrt(val)));
      setResetNext(true);
    }
  };

  const handlePercent = () => {
    const val = Number(display);
    setDisplay(String(val / 100));
    setResetNext(true);
  };

  const handleOp = (nextOp: string) => {
    const current = Number(display);
    if (prev !== null && op && !resetNext) {
      let res = prev;
      if (op === '+') res = prev + current;
      if (op === '−') res = prev - current;
      if (op === '×') res = prev * current;
      if (op === '÷') res = current !== 0 ? prev / current : 0;
      setDisplay(String(Number(res.toFixed(8))));
      setPrev(res);
    } else {
      setPrev(current);
    }
    setOp(nextOp);
    setResetNext(true);
  };

  const handleEquals = () => {
    if (prev === null || !op) return;
    const current = Number(display);
    let res = prev;
    if (op === '+') res = prev + current;
    if (op === '−') res = prev - current;
    if (op === '×') res = prev * current;
    if (op === '÷') res = current !== 0 ? prev / current : 0;
    setDisplay(String(Number(res.toFixed(8))));
    setPrev(null);
    setOp(null);
    setResetNext(true);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="bento-card bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-xs overflow-hidden shadow-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Title bar */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
          <div className="flex items-center gap-2">
            <span className="text-xl">🧮</span>
            <span className="font-bold text-sm text-white">Imtihon Kalkulyatori</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            aria-label="Yopish"
          >
            <X size={18} />
          </button>
        </div>

        {/* Display */}
        <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 mb-4 text-right">
          <div className="text-[11px] font-mono text-slate-500 h-4">
            {prev !== null && op ? `${prev} ${op}` : ''}
          </div>
          <div className="text-2xl font-black font-mono text-white tracking-wider truncate">
            {display}
          </div>
        </div>

        {/* Keypad Grid */}
        <div className="grid grid-cols-4 gap-2 font-mono text-sm font-bold">
          <button
            type="button"
            onClick={handleClear}
            className="p-3 rounded-xl bg-rose-500/20 text-rose-400 border border-rose-500/30 hover:bg-rose-500/30 active:scale-95 transition-all"
          >
            C
          </button>
          <button
            type="button"
            onClick={handleSqrt}
            className="p-3 rounded-xl bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 active:scale-95 transition-all"
          >
            √
          </button>
          <button
            type="button"
            onClick={handlePercent}
            className="p-3 rounded-xl bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 active:scale-95 transition-all"
          >
            %
          </button>
          <button
            type="button"
            onClick={() => handleOp('÷')}
            className={`p-3 rounded-xl border transition-all active:scale-95 ${
              op === '÷' ? 'bg-amber-500 text-slate-950 border-amber-400' : 'bg-indigo-600/30 text-indigo-300 border-indigo-500/40 hover:bg-indigo-600/40'
            }`}
          >
            ÷
          </button>

          {['7', '8', '9'].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => handleDigit(d)}
              className="p-3 rounded-xl bg-slate-800/80 text-white border border-slate-700/80 hover:bg-slate-700 active:scale-95 transition-all"
            >
              {d}
            </button>
          ))}
          <button
            type="button"
            onClick={() => handleOp('×')}
            className={`p-3 rounded-xl border transition-all active:scale-95 ${
              op === '×' ? 'bg-amber-500 text-slate-950 border-amber-400' : 'bg-indigo-600/30 text-indigo-300 border-indigo-500/40 hover:bg-indigo-600/40'
            }`}
          >
            ×
          </button>

          {['4', '5', '6'].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => handleDigit(d)}
              className="p-3 rounded-xl bg-slate-800/80 text-white border border-slate-700/80 hover:bg-slate-700 active:scale-95 transition-all"
            >
              {d}
            </button>
          ))}
          <button
            type="button"
            onClick={() => handleOp('−')}
            className={`p-3 rounded-xl border transition-all active:scale-95 ${
              op === '−' ? 'bg-amber-500 text-slate-950 border-amber-400' : 'bg-indigo-600/30 text-indigo-300 border-indigo-500/40 hover:bg-indigo-600/40'
            }`}
          >
            −
          </button>

          {['1', '2', '3'].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => handleDigit(d)}
              className="p-3 rounded-xl bg-slate-800/80 text-white border border-slate-700/80 hover:bg-slate-700 active:scale-95 transition-all"
            >
              {d}
            </button>
          ))}
          <button
            type="button"
            onClick={() => handleOp('+')}
            className={`p-3 rounded-xl border transition-all active:scale-95 ${
              op === '+' ? 'bg-amber-500 text-slate-950 border-amber-400' : 'bg-indigo-600/30 text-indigo-300 border-indigo-500/40 hover:bg-indigo-600/40'
            }`}
          >
            +
          </button>

          <button
            type="button"
            onClick={handleToggleSign}
            className="p-3 rounded-xl bg-slate-800/80 text-slate-300 border border-slate-700/80 hover:bg-slate-700 active:scale-95 transition-all"
          >
            ±
          </button>
          <button
            type="button"
            onClick={() => handleDigit('0')}
            className="p-3 rounded-xl bg-slate-800/80 text-white border border-slate-700/80 hover:bg-slate-700 active:scale-95 transition-all"
          >
            0
          </button>
          <button
            type="button"
            onClick={handleDot}
            className="p-3 rounded-xl bg-slate-800/80 text-white border border-slate-700/80 hover:bg-slate-700 active:scale-95 transition-all"
          >
            .
          </button>
          <button
            type="button"
            onClick={handleEquals}
            className="p-3 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 border border-amber-400 shadow-md shadow-amber-500/20 active:scale-95 transition-all"
          >
            =
          </button>
        </div>
      </div>
    </div>
  );
}
