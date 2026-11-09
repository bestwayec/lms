import { MessageSquare, Star } from 'lucide-react';
import { useTranslation } from '../i18n/useTranslation';
import type { PublicFeedbackItem } from '../lib/api';

interface Props {
  items: PublicFeedbackItem[];
  loading: boolean;
  onOpen: () => void;
}

const KNOWN_CATS = ['praise', 'suggestion', 'bug', 'feedback'];

function initialsOf(name: string): string {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0] || '?').slice(0, 2).toUpperCase();
}

export default function PublicFeedbackList({ items, loading, onOpen }: Props) {
  const { t } = useTranslation();

  const openBtn = (
    <button type="button" className="ui-btn ui-btn--primary" onClick={onOpen}>
      <MessageSquare size={18} aria-hidden="true" />
      <span>{t('feedback_open_btn')}</span>
    </button>
  );

  if (loading) return null;

  const sampleCards = [
    {
      id: 'sample-1',
      title: 'Milliy sertifikat (BMB) & Esse tahlili',
      message: 'BMB standarti bo‘yicha 45 talik testlar va 12 mezonli AI Esse tekshiruvi orqali xatolar ustida chuqur ishlash imkoniyati.',
      topic: 'Milliy Sertifikat',
      tag: 'Namunaviy ko‘rinish',
    },
    {
      id: 'sample-2',
      title: 'IELTS Academic & CEFR Multi-Level',
      message: 'Listening gap-fill, Reading moslashtirish va Writing Task tahlili bo‘yicha xalqaro imtihon muhiti simulyatsiyasi.',
      topic: 'IELTS / CEFR',
      tag: 'Namunaviy ko‘rinish',
    },
    {
      id: 'sample-3',
      title: 'AI Vision Konvertor (5 ta fan)',
      message: 'Qog‘ozdagi va PDF dagi testlarni soniyalar ichida raqamli CBT formatiga o‘tkazib, guruhlarga biriktirish tizimi.',
      topic: 'AI Konvertor',
      tag: 'Namunaviy ko‘rinish',
    },
  ];

  if (items.length === 0) {
    return (
      <div className="fb-samples-section" style={{ width: '100%', margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '20px' }}>
          <span
            style={{
              fontSize: '11.5px',
              fontWeight: 800,
              padding: '4px 12px',
              borderRadius: '999px',
              backgroundColor: 'rgba(200, 146, 42, 0.12)',
              color: '#C8922A',
              border: '1px solid rgba(200, 146, 42, 0.35)',
              display: 'inline-block',
              marginBottom: '8px',
            }}
          >
            Namunaviy taqrizlar (Platforma imkoniyatlari)
          </span>
          <p style={{ margin: 0, fontSize: '13px', color: 'var(--muted, #64748b)' }}>
            Hozircha foydalanuvchilar sharhi tasdiqlanmoqda. Birinchi bo‘lib o‘z fikringizni qoldiring!
          </p>
        </div>

        <div className="fb-grid" style={{ marginBottom: '24px' }}>
          {sampleCards.map((sc) => (
            <figure
              key={sc.id}
              className="fb-card"
              style={{
                position: 'relative',
                borderRadius: '16px',
                border: '1.5px dashed var(--border, rgba(226, 232, 240, 0.8))',
                backgroundColor: 'var(--card, #ffffff)',
                padding: '20px',
              }}
            >
              <div className="fb-card__top" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div className="fb-card__stars" role="img" aria-label="5/5" style={{ display: 'flex', gap: '3px', color: '#f59e0b' }}>
                  {[1, 2, 3, 4, 5].map((s) => (
                    <Star key={s} size={15} fill="currentColor" />
                  ))}
                </div>
                <span
                  style={{
                    fontSize: '10.5px',
                    fontWeight: 800,
                    padding: '2px 8px',
                    borderRadius: '999px',
                    backgroundColor: 'rgba(56, 189, 248, 0.12)',
                    color: '#0284c7',
                    border: '1px solid rgba(56, 189, 248, 0.3)',
                  }}
                >
                  {sc.tag}
                </span>
              </div>
              <h4 style={{ margin: '0 0 6px 0', fontSize: '14.5px', fontWeight: 800, color: 'var(--ink, #0f172a)' }}>
                {sc.title}
              </h4>
              <blockquote className="fb-card__quote" style={{ margin: 0, fontSize: '13px', color: 'var(--ink-soft, #475569)', lineHeight: 1.5 }}>
                “{sc.message}”
              </blockquote>
            </figure>
          ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'center' }}>
          {openBtn}
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="fb-cta">{openBtn}</div>
      <div className="fb-grid">
        {items.map((item) => (
          <figure key={item.id} className="fb-card">
            <div className="fb-card__top">
              <div className="fb-card__stars" role="img" aria-label={`${item.rating || 5}/5`}>
                {[1, 2, 3, 4, 5].map((s) => (
                  <Star
                    key={s}
                    size={16}
                    aria-hidden="true"
                    fill={s <= (item.rating || 5) ? 'currentColor' : 'none'}
                    className={s <= (item.rating || 5) ? 'is-on' : 'is-off'}
                  />
                ))}
              </div>
              <span className="fb-card__badge">{t(`feedback_cat_${KNOWN_CATS.includes((item.category || '').toLowerCase()) ? item.category.toLowerCase() : 'feedback'}`)}</span>
            </div>
            <blockquote className="fb-card__quote">“{item.message}”</blockquote>
            <figcaption className="fb-card__author">
              <span className="fb-card__avatar" aria-hidden="true">{initialsOf(item.name)}</span>
              <span className="fb-card__who">
                <b>{item.name}</b>
                <small>{item.role || t('feedback_role_default')} · {item.created_at}</small>
              </span>
            </figcaption>
          </figure>
        ))}
      </div>
    </>
  );
}
