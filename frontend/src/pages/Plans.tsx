import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Check, Copy, CreditCard, Crown, Rocket, Sparkles, Zap } from 'lucide-react';
import { useLang } from '../i18n/LangContext';
import { Billing, type BillingPlan } from '../lib/api';
import { formatPrice, planLines } from '../lib/planFeatures';
import {
  DEFAULT_CARD_HOLDER,
  DEFAULT_CARD_NUMBER,
  DEFAULT_CARD_NUMBER_RAW,
  useCardInfo,
} from '../lib/useCardInfo';
import UsageLimits from '../components/UsageLimits';

interface MySub {
  plan?: { id?: number; name?: string; plan_type?: string } | null;
  days_remaining?: number;
  is_active?: boolean;
  status?: string;
}

const ICONS: Record<string, typeof Zap> = { starter: Zap, start: Zap, pro: Rocket, premium: Crown };

/**
 * /plans. Deduplicates start & starter so only one unified 7 000 UZS plan
 * appears alongside Pro (15 000 UZS - Recommended) and Premium (27 000 UZS).
 */
export default function Plans() {
  const { t } = useLang();
  const [plans, setPlans] = useState<BillingPlan[] | null>(null);
  const [myPlanId, setMyPlanId] = useState<number | null>(null);
  const [mySub, setMySub] = useState<MySub | null>(null);
  const [failed, setFailed] = useState(false);
  const [copiedCard, setCopiedCard] = useState(false);

  const card = useCardInfo();
  const cardNumber = card.info?.card_number || DEFAULT_CARD_NUMBER;
  const cardHolder = card.info?.card_holder || DEFAULT_CARD_HOLDER;

  const handleCopyCard = async () => {
    const raw = (cardNumber || DEFAULT_CARD_NUMBER).replace(/\s+/g, '') || DEFAULT_CARD_NUMBER_RAW;
    try {
      await navigator.clipboard.writeText(raw);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = raw;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    setCopiedCard(true);
    setTimeout(() => setCopiedCard(false), 2000);
  };

  const fetchAll = useCallback(() => {
    Billing.plans()
      .then((r) => {
        const price = (p: BillingPlan) => Number(p.price_uzs ?? p.price_monthly ?? 0);
        const sorted = r.results.filter((p) => price(p) > 0).sort((a, b) => price(a) - price(b));
        const seenTypes = new Set<string>();
        const deduped: BillingPlan[] = [];
        for (const p of sorted) {
          const canonical = p.plan_type === 'start' ? 'starter' : p.plan_type;
          if (seenTypes.has(canonical)) continue;
          seenTypes.add(canonical);
          deduped.push(canonical === 'starter' ? { ...p, name: 'Starter', plan_type: 'starter' } : p);
        }
        setPlans(deduped);
        setMyPlanId(r.my_plan_id);
      })
      .catch(() => setFailed(true));
    Billing.my()
      .then((r) => setMySub((r.subscription as MySub | null) ?? null))
      .catch(() => setMySub(null));
  }, []);

  useEffect(fetchAll, [fetchAll]);

  const retry = () => {
    setFailed(false);
    setPlans(null);
    fetchAll();
  };

  const active = Boolean(mySub && (mySub.is_active ?? mySub.status === 'active'));
  const days = Number(mySub?.days_remaining ?? 0);

  return (
    <div className="pl">
      <header className="pl-head">
        <h1>{t('pay_plans_title')}</h1>
        <p className="muted">{t('pl_subtitle')}</p>
      </header>

      <UsageLimits showManage={false} />

      {active && mySub?.plan && (
        <section className="ui-card pl-current" aria-label={t('pay_current_sub')}>
          <span className="ic-chip">
            <Crown size={18} aria-hidden="true" />
          </span>
          <div className="pl-current__text">
            <small>{t('pay_current_sub')}</small>
            <strong>{mySub.plan.name}</strong>
            <span>{days > 0 ? t('pl_days_left').replace('{n}', String(days)) : t('pay_expired')}</span>
          </div>
          <Link className="ui-btn ui-btn--sm" to="/my-subscription" style={{ textDecoration: 'none' }}>
            {t('pay_manage')}
          </Link>
        </section>
      )}

      {failed ? (
        <div className="ui-state ui-state--error" role="alert">
          <span className="ic-chip ic-chip--danger">
            <AlertTriangle size={22} aria-hidden="true" />
          </span>
          <p>{t('pl_load_error')}</p>
          <button type="button" className="ui-btn" onClick={retry}>
            {t('pl_retry')}
          </button>
        </div>
      ) : plans === null ? (
        <div className="pl-grid" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="ui-card pl-card">
              <span className="ui-skel" style={{ width: 40, height: 40 }} />
              <span className="ui-skel ui-skel-line" style={{ width: '50%' }} />
              <span className="ui-skel ui-skel-line" style={{ width: '70%', height: 28 }} />
              <span className="ui-skel ui-skel-line" />
              <span className="ui-skel ui-skel-line" />
            </div>
          ))}
        </div>
      ) : plans.length === 0 ? (
        <div className="ui-state">
          <span className="ic-chip ic-chip--muted">
            <Sparkles size={22} aria-hidden="true" />
          </span>
          <p>{t('pl_empty')}</p>
        </div>
      ) : (
        <div className="pl-grid">
          {plans.map((p) => {
            const Icon = ICONS[p.plan_type] ?? Sparkles;
            const featured = p.plan_type === 'pro';
            const mine = active && (myPlanId === p.id || mySub?.plan?.id === p.id);
            return (
              <article key={p.id} className={`ui-card pl-card${featured ? ' is-featured' : ''}${mine ? ' is-mine' : ''}`}>
                {featured && <span className="pl-card__badge">{t('pl_recommended')}</span>}
                <span className="ic-chip">
                  <Icon size={18} aria-hidden="true" />
                </span>
                <h2 className="pl-card__name">{p.name}</h2>
                <p className="pl-card__price">
                  <b>{formatPrice(p.price_uzs ?? p.price_monthly)}</b> <span>{t('pay_per_month')}</span>
                </p>
                <ul className="pl-card__lines">
                  {planLines(p).map((l) => (
                    <li key={l.key}>
                      <Check size={16} aria-hidden="true" />
                      <span>{l.n === undefined ? t(l.key) : t(l.key).replace('{n}', String(l.n))}</span>
                    </li>
                  ))}
                </ul>
                {mine ? (
                  <span className="pl-card__mine">
                    <Check size={16} aria-hidden="true" /> {t('pl_your_plan')}
                  </span>
                ) : (
                  <Link
                    className={`ui-btn ui-btn--block${featured ? ' ui-btn--primary' : ''}`}
                    to={`/checkout?plan=${encodeURIComponent(p.plan_type)}`}
                    style={{ textDecoration: 'none' }}
                  >
                    {t(active ? 'pl_switch_cta' : 'pl_pay_cta')}
                  </Link>
                )}
              </article>
            );
          })}
        </div>
      )}

      {/* Official Payment Card Banner */}
      <section
        className="ui-card"
        style={{
          marginTop: 20,
          marginBottom: 16,
          padding: '20px 24px',
          background: 'linear-gradient(135deg, #0F172A 0%, #1E293B 100%)',
          color: '#FFFFFF',
          borderRadius: 18,
          border: '1px solid rgba(245, 158, 11, 0.35)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#94A3B8' }}>
            <CreditCard size={16} color="#F59E0B" /> Visa / Humo / Uzcard
          </span>
          <span style={{ fontSize: 12, fontWeight: 800, color: '#38BDF8' }}>GRAND EDUCATION</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
          <span
            style={{
              fontFamily: '"JetBrains Mono", monospace',
              fontSize: 22,
              fontWeight: 800,
              letterSpacing: '0.1em',
              color: '#F8FAFC',
              userSelect: 'all',
            }}
          >
            {cardNumber}
          </span>
          <button
            type="button"
            onClick={() => void handleCopyCard()}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 16px',
              borderRadius: 10,
              border: '1px solid rgba(255,255,255,0.2)',
              background: copiedCard ? '#10B981' : '#F59E0B',
              color: '#FFFFFF',
              fontWeight: 800,
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            {copiedCard ? (
              <>
                <Check size={15} /> {t('sub_card_copied')}
              </>
            ) : (
              <>
                <Copy size={15} /> {t('sub_copy_card')}
              </>
            )}
          </button>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.1)' }}>
          <div>
            <span style={{ fontSize: 11, textTransform: 'uppercase', color: '#94A3B8', display: 'block' }}>{t('sub_card_holder')}</span>
            <strong style={{ fontSize: 14, color: '#F8FAFC' }}>{cardHolder}</strong>
          </div>
          <Link
            to="/checkout?plan=pro"
            className="ui-btn ui-btn--primary ui-btn--sm"
            style={{ textDecoration: 'none' }}
          >
            {t('pl_pay_cta')} →
          </Link>
        </div>
      </section>

      <p className="pl-note muted">{t('pl_pay_note')}</p>

      <section className="ui-card pl-faq">
        <h2>{t('faq_title')}</h2>
        {(['payment', 'cancel', 'premium'] as const).map((k) => (
          <details key={k}>
            <summary>{t(`faq_${k}_q`)}</summary>
            <p>{t(`faq_${k}_a`)}</p>
          </details>
        ))}
      </section>
    </div>
  );
}
