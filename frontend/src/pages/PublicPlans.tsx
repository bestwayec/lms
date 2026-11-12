import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Billing, type BillingPlan } from '../lib/api';
import { useLang } from '../i18n/LangContext';
import { formatPrice, planLines } from '../lib/planFeatures';
import SEO from '../components/SEO';

/** Public discovery only. Checkout, receipts and account data stay guarded. */
export default function PublicPlans() {
  const { t } = useLang();
  const [plans, setPlans] = useState<BillingPlan[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    Billing.plans().then((r) => { if (alive) setPlans(r.results); }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [attempt]);
  return <main className="public-plans">
    <SEO title={t('pay_plans_title')} canonical="/pricing" />
    <header><Link to="/" className="btn">GRANDEC</Link><h1>{t('pay_plans_title')}</h1><p className="muted">{t('pl_subtitle')}</p></header>
    {!plans && !failed && <p role="status">{t('loading')}</p>}
    {failed && <div role="alert" className="ui-error"><p>{t('error_network')}</p><button className="btn" onClick={() => { setFailed(false); setPlans(null); setAttempt((n) => n + 1); }}>{t('retry')}</button></div>}
    {plans?.length === 0 && <p role="status">{t('public_plans_empty')}</p>}
    <div className="public-plan-grid">{plans?.map((plan) => <article className="card" key={plan.id}>
      <h2>{plan.name}</h2><p className="public-plan-price">{formatPrice(Number(plan.price_uzs ?? plan.price_monthly ?? 0))} UZS</p>
      <ul>{planLines(plan).map((line, i) => <li key={i}>{t(line.key).replace('{n}', String(line.n ?? ''))}</li>)}</ul>
      <Link className="btn primary" to={`/subscribe/${plan.id}`}>{t('login')}</Link>
    </article>)}</div>
  </main>;
}
