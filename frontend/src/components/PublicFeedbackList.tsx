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

  const showcaseCards = [
    {
      id: 'showcase-cbt',
      icon: '🎯',
      title: 'BMB Milliy Sertifikat 45 talik CBT Arena',
      badge: 'CBT Arena',
      badgeColor: '#0EA5E9',
      badgeBg: 'rgba(14, 165, 233, 0.12)',
      badgeBorder: 'rgba(14, 165, 233, 0.3)',
      desc: 'Haqiqiy davlat test markazi standarti, qat’iy vaqt nazorati, ko‘p tanlovli va ochiq savollar hamda avtomatik ball hisoblash.',
    },
    {
      id: 'showcase-essay',
      icon: '✍️',
      title: '12-Mezonli AI Esse Studiyasi',
      badge: 'AI Esse',
      badgeColor: '#D97706',
      badgeBg: 'rgba(217, 119, 6, 0.12)',
      badgeBorder: 'rgba(217, 119, 6, 0.3)',
      desc: 'O‘zbek va ingliz tillarida grammatika, uslub, mavzuni yoritish va leksika bo‘yicha soniyalar ichida professional xulosa va band ball.',
    },
    {
      id: 'showcase-ielts',
      icon: '🎧',
      title: 'CD-IELTS & CEFR Audio CBT Imtihon',
      badge: 'Audio CBT',
      badgeColor: '#3B82F6',
      badgeBg: 'rgba(59, 130, 246, 0.12)',
      badgeBorder: 'rgba(59, 130, 246, 0.3)',
      desc: 'Sinxron audio tinglash, matn bo‘ylab split-screen va to‘g‘ridan-to‘g‘ri gap-fill (bo‘sh joy to‘ldirish) bilan to‘liq xalqaro format muhiti.',
    },
    {
      id: 'showcase-converter',
      icon: '⚡',
      title: '10-Soniyalik AI Test Konvertor',
      badge: 'AI Vision',
      badgeColor: '#10B981',
      badgeBg: 'rgba(16, 185, 129, 0.12)',
      badgeBorder: 'rgba(16, 185, 129, 0.3)',
      desc: 'Qog‘ozdagi test fotosurati yoki PDF faylni bir zumda raqamli testga aylantirish va guruh o‘quvchilariga darhol biriktirish imkoniyati.',
    },
  ];

  if (items.length === 0) {
    return (
      <div className="fb-samples-section" style={{ width: '100%', margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <span
            style={{
              fontSize: '11.5px',
              fontWeight: 800,
              padding: '4px 14px',
              borderRadius: '999px',
              backgroundColor: 'rgba(200, 146, 42, 0.12)',
              color: '#C8922A',
              border: '1px solid rgba(200, 146, 42, 0.35)',
              display: 'inline-block',
              marginBottom: '8px',
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
            }}
          >
            Platforma Imkoniyatlari Vitrinasi
          </span>
          <p style={{ margin: 0, fontSize: '13.5px', color: 'var(--muted, #64748b)' }}>
            GRANDEC 2.0 intellektual LMS platformasining ilg‘or imkoniyatlari
          </p>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: '16px',
            marginBottom: '28px',
          }}
        >
          {showcaseCards.map((sc) => (
            <div
              key={sc.id}
              className="bento-card"
              style={{
                borderRadius: '18px',
                border: '1px solid var(--border-subtle, rgba(226, 232, 240, 0.8))',
                backgroundColor: 'var(--bg-surface, #ffffff)',
                padding: '22px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                transition: 'transform 0.2s ease, box-shadow 0.2s ease',
              }}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                  <span style={{ fontSize: '26px' }}>{sc.icon}</span>
                  <span
                    style={{
                      fontSize: '10.5px',
                      fontWeight: 800,
                      padding: '3px 10px',
                      borderRadius: '999px',
                      backgroundColor: sc.badgeBg,
                      color: sc.badgeColor,
                      border: `1px solid ${sc.badgeBorder}`,
                      letterSpacing: '0.03em',
                    }}
                  >
                    {sc.badge}
                  </span>
                </div>
                <h4 style={{ margin: '0 0 8px 0', fontSize: '15px', fontWeight: 800, color: 'var(--text-primary, #0f172a)', lineHeight: 1.35 }}>
                  {sc.title}
                </h4>
                <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary, #64748b)', lineHeight: 1.6 }}>
                  {sc.desc}
                </p>
              </div>
            </div>
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
