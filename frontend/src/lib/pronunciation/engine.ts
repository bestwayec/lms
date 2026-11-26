/** Shared English Pronunciation Engine: stored audio first, Web Speech API fallback. */

export interface SpeakOptions {
  audioUrl?: string | null;
  slow?: boolean;
  doublePlay?: boolean;
  lang?: string;
}

class PronunciationEngineImpl {
  private currentAudio: HTMLAudioElement | null = null;
  private pauseTimer: number | null = null;
  private cancelled = false;

  cancel(): void {
    this.cancelled = true;
    if (this.pauseTimer !== null && typeof window !== 'undefined') {
      window.clearTimeout(this.pauseTimer);
      this.pauseTimer = null;
    }
    if (this.currentAudio) {
      try {
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
      } catch {
        /* ignore */
      }
      this.currentAudio = null;
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {
        /* ignore */
      }
    }
  }

  private playOnce(word: string, opts: SpeakOptions): Promise<boolean> {
    if (opts.audioUrl && typeof Audio !== 'undefined') {
      return new Promise((resolve) => {
        const audio = new Audio(opts.audioUrl!);
        this.currentAudio = audio;
        audio.playbackRate = opts.slow ? 0.75 : 1.0;
        audio.onended = () => resolve(true);
        audio.onerror = () => resolve(this.playSpeech(word, opts));
        audio.play().catch(() => resolve(this.playSpeech(word, opts)));
      });
    }
    return this.playSpeech(word, opts);
  }

  private playSpeech(word: string, opts: SpeakOptions): Promise<boolean> {
    if (typeof window === 'undefined' || !('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
      return Promise.resolve(false);
    }
    return new Promise((resolve) => {
      try {
        const u = new SpeechSynthesisUtterance(word);
        u.lang = opts.lang || 'en-GB';
        u.rate = opts.slow ? 0.72 : 0.96;
        u.onend = () => resolve(true);
        u.onerror = () => resolve(false);
        window.speechSynthesis.speak(u);
      } catch {
        resolve(false);
      }
    });
  }

  async speak(word: string, opts: SpeakOptions = {}): Promise<boolean> {
    const clean = (word || '').trim();
    if (!clean) return false;
    this.cancel();
    this.cancelled = false;

    const ok1 = await this.playOnce(clean, opts);
    if (!ok1 || this.cancelled || !opts.doublePlay) return ok1;

    await new Promise<void>((resolve) => {
      this.pauseTimer = window.setTimeout(() => resolve(), 650);
    });
    if (this.cancelled) return true;
    return this.playOnce(clean, opts);
  }
}

export const pronunciationEngine = new PronunciationEngineImpl();
