import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { Copy, Check, X, Maximize2, Minimize2, Smartphone, Globe, Send } from 'lucide-react';
import { sanitizeSvg } from '../lib/sanitize';

interface ClassroomQrModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  code?: string;
  webUrl: string;
  tmaUrl?: string;
  subtitle?: string;
}

export default function ClassroomQrModal({
  isOpen,
  onClose,
  title,
  code,
  webUrl,
  tmaUrl,
  subtitle = "Sinfxona proyektorida yoki telefonda o'quvchilarga ko'rsating",
}: ClassroomQrModalProps) {
  const [activeTab, setActiveTab] = useState<'tma' | 'web'>(tmaUrl ? 'tma' : 'web');
  const [svgContent, setSvgContent] = useState<string>('');
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const activeUrl = activeTab === 'tma' && tmaUrl ? tmaUrl : webUrl;

  useEffect(() => {
    if (!isOpen || !activeUrl) return;
    QRCode.toString(activeUrl, {
      type: 'svg',
      margin: 1,
      errorCorrectionLevel: 'M',
      color: {
        dark: '#0f172a',
        light: '#ffffff',
      },
    })
      .then((svg) => setSvgContent(svg))
      .catch((err) => console.error('Failed to generate QR code SVG:', err));
  }, [isOpen, activeUrl]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(activeUrl);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    } catch {
      /* ignore */
    }
  };

  const handleCopyCode = async () => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(true);
      setTimeout(() => setCopiedCode(false), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Sinfxona QR-Kodi"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className={`relative w-full ${
          isFullscreen ? 'max-w-4xl h-[95vh]' : 'max-w-md'
        } bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl p-5 sm:p-6 flex flex-col items-center justify-between transition-all duration-300 text-slate-100 overflow-y-auto max-h-[92vh]`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header & Controls */}
        <div className="w-full flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="min-w-0 pr-3">
            <span className="text-xs font-bold uppercase tracking-wider text-amber-400">
              📱 Sinfxona QR-Kodi
            </span>
            <h2 className="text-lg sm:text-xl font-black text-white truncate">{title}</h2>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title={isFullscreen ? 'Kichik oyna' : 'Butun ekranga'}
              aria-label="Fullscreen"
            >
              {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              aria-label="Yopish"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Tab Switcher: Mini App vs Web */}
        {tmaUrl && (
          <div className="flex items-center gap-2 p-1 mt-4 bg-slate-950/70 rounded-xl border border-slate-800 w-full max-w-xs">
            <button
              type="button"
              onClick={() => setActiveTab('tma')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'tma'
                  ? 'bg-amber-500 text-slate-950 shadow-md'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Smartphone size={14} />
              <span>Telegram App</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('web')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'web'
                  ? 'bg-amber-500 text-slate-950 shadow-md'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Globe size={14} />
              <span>Web Sayt</span>
            </button>
          </div>
        )}

        {/* High-Contrast Crisp QR Card (White Container for Projectors) */}
        <div className="my-4 p-4 sm:p-5 bg-white rounded-2xl shadow-xl flex flex-col items-center justify-center">
          {svgContent ? (
            <div
              className={`${
                isFullscreen ? 'w-72 h-72 sm:w-96 sm:h-96' : 'w-56 h-56 sm:w-64 sm:h-64'
              } flex items-center justify-center`}
              dangerouslySetInnerHTML={{ __html: sanitizeSvg(svgContent) }}
            />
          ) : (
            <div className="w-56 h-56 flex items-center justify-center text-slate-500 text-sm">
              QR generatsiya qilinmoqda...
            </div>
          )}
          <span className="text-[11px] font-bold text-slate-600 mt-2 tracking-wide uppercase">
            Kamera orqali skanerlang
          </span>
        </div>

        {/* Test / Join PIN Code Box */}
        {code && (
          <div className="w-full max-w-sm mb-4 text-center">
            <span className="text-xs text-slate-400 font-medium block mb-1">
              Yoki kodni to&apos;g&apos;ridan-to&apos;g&apos;ri kiriting:
            </span>
            <div className="flex items-center justify-center gap-2">
              <span className="font-mono text-2xl sm:text-3xl font-black tracking-widest text-amber-400 bg-slate-950 px-5 py-2 rounded-xl border border-amber-500/40 select-all">
                {code}
              </span>
              <button
                type="button"
                onClick={handleCopyCode}
                className="p-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 active:scale-95 transition-all border border-slate-700"
                title="Kodni nusxalash"
                aria-label="Kodni nusxalash"
              >
                {copiedCode ? <Check size={18} className="text-emerald-400" /> : <Copy size={18} />}
              </button>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="w-full flex flex-col sm:flex-row items-center justify-center gap-2 pt-3 border-t border-slate-800 text-xs">
          <a
            href={`https://t.me/share/url?url=${encodeURIComponent(activeUrl)}&text=${encodeURIComponent(`Test kodi: ${code || ''}\n${title} testiga kirish uchun bosing:`)}`}
            target="_blank"
            rel="noreferrer"
            className="w-full sm:w-auto flex items-center justify-center gap-1.5 py-2 px-4 rounded-xl bg-sky-500 hover:bg-sky-400 text-white font-bold transition-all active:scale-95 shadow-md shadow-sky-500/20"
          >
            <Send size={14} />
            <span>✈️ Telegramga yuborish</span>
          </a>
          <button
            type="button"
            onClick={handleCopyLink}
            className="w-full sm:w-auto flex items-center justify-center gap-1.5 py-2 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold border border-slate-700 transition-all active:scale-95"
          >
            {copiedLink ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
            <span>{copiedLink ? 'Havola nusxalandi' : 'Havolani nusxalash'}</span>
          </button>
          <a
            href={activeUrl}
            target="_blank"
            rel="noreferrer"
            className="w-full sm:w-auto flex items-center justify-center gap-1.5 py-2 px-4 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold transition-all active:scale-95"
          >
            <span>Havolaga o&apos;tish →</span>
          </a>
        </div>

        <p className="text-[11px] text-slate-500 text-center mt-3">
          💡 {subtitle}
        </p>
      </div>
    </div>
  );
}
