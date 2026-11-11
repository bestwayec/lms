import { useState } from 'react';
import { useLang } from '../i18n/LangContext';
import { FeedbackApi } from '../lib/api';
import { buildFeedbackContext } from '../lib/feedbackContext';

const LAST_KEY = 'fb_prompt_last';
const SNOOZE_KEY = 'fb_prompt_snooze_until';
const DAY = 24 * 60 * 60 * 1000;

const read = (key: string): number => {
  try {
    return Number(localStorage.getItem(key)) || 0;
  } catch {
    return 0;
  }
};
const write = (key: string, value: number) => {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    /* private mode: the prompt may simply show again */
  }
};

/**
 * Post-test 5-star rating + optional short comment ("Imtihon va savollar sifati
 * sizga yoqdimi?"). Selecting a star expands a comment field; submitting sends
 * both rating and comment via FeedbackApi.submit (backed by /api/feedback/).
 */
export default function FeedbackPrompt() {
  const { t, lang } = useLang();
  const [visible, setVisible] = useState(() => {
    const now = Date.now();
    return read(SNOOZE_KEY) < now && now - read(LAST_KEY) > DAY;
  });
  const [rating, setRating] = useState<number>(0);
  const [hover, setHover] = useState<number>(0);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  if (!visible) return null;

  const submit = async (chosenRating?: number) => {
    const r = chosenRating ?? rating;
    if (!r || busy) return;
    setBusy(true);
    write(LAST_KEY, Date.now());
    const trimmed = comment.trim();
    const fallback = (t('feedback_quick_message') || 'Rated {n}/5').replace('{n}', String(r));
    try {
      await FeedbackApi.submit({
        rating: r,
        category: 'feedback',
        message: trimmed || fallback,
        context: { ...buildFeedbackContext({ category: 'feedback', lang, source: 'result' }) },
      });
    } catch {
      /* a failed quick rating is not worth interrupting the result page */
    } finally {
      setBusy(false);
      setSent(true);
    }
  };

  const later = () => {
    write(SNOOZE_KEY, Date.now() + 7 * DAY);
    setVisible(false);
  };

  const activeStars = hover || rating;

  return (
    <div
      className="card fb-prompt bento-card"
      role="group"
      aria-label={t('feedback_prompt_q') || 'Imtihon va savollar sifati sizga yoqdimi?'}
      style={{ padding: '16px 20px', borderRadius: 18, marginBottom: 16 }}
    >
      {sent ? (
        <p style={{ margin: 0, fontWeight: 700, color: '#10b981' }}>
          ✓ {t('feedback_thanks_title') || 'Fikringiz uchun rahmat!'}
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
            <strong style={{ fontSize: 14 }}>
              ⭐ {t('feedback_prompt_q')}
            </strong>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <div className="fb-stars" onMouseLeave={() => setHover(0)}>
                {[1, 2, 3, 4, 5].map((n) => {
                  const lit = n <= activeStars;
                  return (
                    <button
                      key={n}
                      type="button"
                      className={`fb-star${lit ? ' is-lit' : ''}`}
                      aria-label={`${n} / 5`}
                      aria-pressed={rating === n}
                      onMouseEnter={() => setHover(n)}
                      onClick={() => setRating(n)}
                      style={{
                        color: lit ? '#fbbf24' : 'var(--muted, #64748b)',
                        fontSize: 22,
                        transform: lit ? 'scale(1.08)' : 'none',
                        transition: 'transform .12s ease, color .12s ease',
                      }}
                    >
                      ★
                    </button>
                  );
                })}
              </div>
              <button type="button" className="btn ghost sm" onClick={later}>
                {t('feedback_prompt_later')}
              </button>
            </div>
          </div>

          {rating > 0 && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                type="text"
                value={comment}
                maxLength={500}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Qisqa izoh qoldiring (ixtiyoriy)..."
                aria-label="Qisqa izoh"
                style={{ flex: '1 1 220px', minHeight: 38, fontSize: 13 }}
              />
              <button
                type="button"
                className="bento-btn bento-btn-gold"
                disabled={busy}
                onClick={() => submit()}
                style={{ height: 38, padding: '0 16px', fontSize: 12.5, fontWeight: 800 }}
              >
                {busy ? '…' : 'Fikr qoldirish'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
