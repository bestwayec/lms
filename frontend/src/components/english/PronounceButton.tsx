import { useState } from 'react';
import { Volume2 } from 'lucide-react';
import { useLang } from '../../i18n/LangContext';
import { pronunciationEngine } from '../../lib/pronunciation/engine';

interface PronounceButtonProps {
  word: string;
  audioUrl?: string | null;
  doublePlay?: boolean;
  showSlowToggle?: boolean;
}

export default function PronounceButton({
  word,
  audioUrl,
  doublePlay = false,
  showSlowToggle = true,
}: PronounceButtonProps) {
  const { t } = useLang();
  const [slow, setSlow] = useState(false);
  const [playing, setPlaying] = useState(false);

  const play = async () => {
    setPlaying(true);
    try {
      await pronunciationEngine.speak(word, { audioUrl, slow, doublePlay });
    } finally {
      setPlaying(false);
    }
  };

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <button
        type="button"
        className="btn sm ghost"
        onClick={() => void play()}
        aria-label={t('voc_pronounce')}
        disabled={playing}
      >
        <Volume2 size={15} /> {playing ? t('voc_playing') : t('voc_pronounce')}
      </button>
      {showSlowToggle && (
        <button
          type="button"
          className={`btn sm ${slow ? 'primary' : 'ghost'}`}
          onClick={() => setSlow((s) => !s)}
          aria-pressed={slow}
        >
          0.7x
        </button>
      )}
    </span>
  );
}
