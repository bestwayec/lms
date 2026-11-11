import { useState, useRef } from 'react';
import type { FormEvent, DragEvent } from 'react';
import { Link } from 'react-router-dom';
import { useLang } from '../i18n/LangContext';
import { PaymentsApi } from '../lib/api';
import { CreditCardIcon, CheckIcon, CopyIcon, ZapIcon } from '../components/icons';
import CardPaymentModal from '../components/CardPaymentModal';
import SafeBoldText from '../components/SafeBoldText';
import {
  DEFAULT_CARD_HOLDER,
  DEFAULT_CARD_NUMBER,
  DEFAULT_CARD_NUMBER_RAW,
  useCardInfo,
} from '../lib/useCardInfo';

export const PLAN_PRICES = {
  starter: 7000,
  pro: 15000,
  premium: 27000,
} as const;

export default function Pricing() {
  const { t } = useLang();
  const [selectedPlan, setSelectedPlan] = useState<'starter' | 'pro' | 'premium'>('pro');
  const [paymentModalOpen, setPaymentModalOpen] = useState(false);
  const card = useCardInfo();
  const cardInfo = {
    card_number: card.info?.card_number || DEFAULT_CARD_NUMBER,
    card_holder: card.info?.card_holder || DEFAULT_CARD_HOLDER,
  };
  const [copied, setCopied] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const [isSuccess, setIsSuccess] = useState<boolean | null>(null);
  const [isBanned, setIsBanned] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleCopy = (text: string) => {
    const raw = (text || DEFAULT_CARD_NUMBER).replace(/\s+/g, '') || DEFAULT_CARD_NUMBER_RAW;
    navigator.clipboard.writeText(raw);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleFileChange = (file: File | null) => {
    if (!file) return;
    setSelectedFile(file);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    setResultMessage(null);
    setIsSuccess(null);
    setIsBanned(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileChange(e.dataTransfer.files[0]);
    }
  };

  const handleVerifySubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setResultMessage("Iltimos, to'lov cheki rasmini tanlang.");
      setIsSuccess(false);
      return;
    }

    setUploading(true);
    setResultMessage(null);
    setIsSuccess(null);
    setIsBanned(false);

    try {
      const res = await PaymentsApi.verifyReceipt(selectedPlan, selectedFile);
      if (res.success) {
        setIsSuccess(true);
        setResultMessage(res.message);
        setSelectedFile(null);
        setPreviewUrl(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
      } else {
        setIsSuccess(false);
        setIsBanned(Boolean(res.is_banned));
        setResultMessage(res.message);
      }
    } catch (err: unknown) {
      setIsSuccess(false);
      const errMsg = err instanceof Error ? err.message : "Chekni tekshirishda xatolik yuz berdi.";
      if (errMsg.includes('403') || errMsg.toLowerCase().includes('bloklandi')) {
        setIsBanned(true);
      }
      setResultMessage(errMsg);
    } finally {
      setUploading(false);
    }
  };

  const currentPrice = PLAN_PRICES[selectedPlan];

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '24px 16px 60px' }}>
      <p style={{ marginBottom: 16 }}>
        <Link to="/plans" className="muted" style={{ textDecoration: 'none' }}>
          ← {t('pay_back_to_plans')}
        </Link>
      </p>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 14,
            background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.25), rgba(217, 119, 6, 0.15))',
            border: '1px solid rgba(245, 158, 11, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fbbf24',
          }}
        >
          <CreditCardIcon size={24} className="ico" />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800 }}>{t('pricing_title')}</h1>
          <p className="muted small" style={{ margin: 0 }}>
            {t('pricing_subtitle')}
          </p>
        </div>
      </div>

      {/* Pricing Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(280px, 100%), 1fr))', gap: 16, marginBottom: 24 }}>
        {/* Starter */}
        <div
          onClick={() => setSelectedPlan('starter')}
          className={`card ${selectedPlan === 'starter' ? 'card-selected' : ''}`}
          style={{
            cursor: 'pointer',
            padding: 24,
            borderRadius: 16,
            border: selectedPlan === 'starter' ? '2px solid #38bdf8' : '1px solid var(--border)',
            background: selectedPlan === 'starter' ? 'rgba(56, 189, 248, 0.04)' : 'var(--card)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontSize: 32 }}>⚡</span>
            {selectedPlan === 'starter' && <span className="badge" style={{ background: '#38bdf8', color: '#000' }}>{t('sub_plan_selected')}</span>}
          </div>
          <strong style={{ fontSize: 20 }}>STARTER</strong>
          <p style={{ fontSize: 24, fontWeight: 700, margin: '8px 0 16px', color: 'var(--ink)' }}>
            7 000 <span style={{ fontSize: 14, color: 'var(--muted)' }}>{t('pricing_per_month')}</span>
          </p>
          <ul className="muted small" style={{ paddingLeft: 18, lineHeight: 1.7, margin: '0 0 16px' }}>
            <li>{t('pricing_starter_tests')}</li>
            <li>{t('pricing_starter_essays')}</li>
            <li>{t('pricing_mistake_analysis')}</li>
          </ul>
          <button
            type="button"
            className="btn sm"
            style={{
              width: '100%',
              justifyContent: 'center',
              fontWeight: 600,
              background: selectedPlan === 'starter' ? '#38bdf8' : 'rgba(56, 189, 248, 0.1)',
              color: selectedPlan === 'starter' ? '#000' : '#38bdf8',
              border: '1px solid rgba(56, 189, 248, 0.4)',
            }}
            onClick={(e) => {
              e.stopPropagation();
              setSelectedPlan('starter');
              setPaymentModalOpen(true);
            }}
          >
            {selectedPlan === 'starter' ? t('pricing_pay_now') : t('pricing_select_pay')}
          </button>
        </div>

        {/* PRO */}
        <div
          onClick={() => setSelectedPlan('pro')}
          className={`card ${selectedPlan === 'pro' ? 'card-selected' : ''}`}
          style={{
            cursor: 'pointer',
            padding: 24,
            borderRadius: 16,
            border: selectedPlan === 'pro' ? '2px solid #fbbf24' : '1px solid var(--border)',
            background: selectedPlan === 'pro' ? 'rgba(245, 158, 11, 0.05)' : 'var(--card)',
            position: 'relative',
          }}
        >
          <span style={{ position: 'absolute', top: -10, right: 16, background: '#f59e0b', color: '#000', fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 10 }}>
            {t('pricing_recommended')}
          </span>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontSize: 32 }}>🚀</span>
            {selectedPlan === 'pro' && <span className="badge yellow">{t('sub_plan_selected')}</span>}
          </div>
          <strong style={{ fontSize: 20 }}>PRO</strong>
          <p style={{ fontSize: 24, fontWeight: 700, margin: '8px 0 16px', color: 'var(--ink)' }}>
            15 000 <span style={{ fontSize: 14, color: 'var(--muted)' }}>{t('pricing_per_month')}</span>
          </p>
          <ul className="muted small" style={{ paddingLeft: 18, lineHeight: 1.7, margin: '0 0 16px' }}>
            <li>{t('pricing_pro_essays')}</li>
            <li>{t('plan_feat_mocks')}</li>
            <li>{t('pricing_tutor_explanations')}</li>
          </ul>
          <button
            type="button"
            className="btn sm"
            style={{
              width: '100%',
              justifyContent: 'center',
              fontWeight: 700,
              background: selectedPlan === 'pro' ? '#f59e0b' : 'rgba(245, 158, 11, 0.1)',
              color: selectedPlan === 'pro' ? '#000' : '#fbbf24',
              border: '1px solid rgba(245, 158, 11, 0.4)',
            }}
            onClick={(e) => {
              e.stopPropagation();
              setSelectedPlan('pro');
              setPaymentModalOpen(true);
            }}
          >
            {selectedPlan === 'pro' ? t('pricing_pay_now') : t('pricing_select_pay')}
          </button>
        </div>

        {/* PREMIUM */}
        <div
          onClick={() => setSelectedPlan('premium')}
          className={`card ${selectedPlan === 'premium' ? 'card-selected' : ''}`}
          style={{
            cursor: 'pointer',
            padding: 24,
            borderRadius: 16,
            border: selectedPlan === 'premium' ? '2px solid #10b981' : '1px solid var(--border)',
            background: selectedPlan === 'premium' ? 'rgba(16, 185, 129, 0.04)' : 'var(--card)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontSize: 32 }}>👑</span>
            {selectedPlan === 'premium' && <span className="badge green">{t('sub_plan_selected')}</span>}
          </div>
          <strong style={{ fontSize: 20 }}>PREMIUM</strong>
          <p style={{ fontSize: 24, fontWeight: 700, margin: '8px 0 16px', color: 'var(--ink)' }}>
            27 000 <span style={{ fontSize: 14, color: 'var(--muted)' }}>{t('pricing_per_month')}</span>
          </p>
          <ul className="muted small" style={{ paddingLeft: 18, lineHeight: 1.7, margin: '0 0 16px' }}>
            <li>{t('pricing_unlimited_essays')}</li>
            <li>{t('pricing_cbt_arena')}</li>
            <li>{t('pricing_teacher_review')}</li>
          </ul>
          <button
            type="button"
            className="btn sm"
            style={{
              width: '100%',
              justifyContent: 'center',
              fontWeight: 600,
              background: selectedPlan === 'premium' ? '#10b981' : 'rgba(16, 185, 129, 0.1)',
              color: selectedPlan === 'premium' ? '#000' : '#34d399',
              border: '1px solid rgba(16, 185, 129, 0.4)',
            }}
            onClick={(e) => {
              e.stopPropagation();
              setSelectedPlan('premium');
              setPaymentModalOpen(true);
            }}
          >
            {selectedPlan === 'premium' ? t('pricing_pay_now') : t('pricing_select_pay')}
          </button>
        </div>
      </div>

      {/* Card Info Box */}
      <div className="card" style={{ marginBottom: 24, padding: 24, background: 'linear-gradient(135deg, #1e293b, #0f172a)', color: '#fff', borderRadius: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <span style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 1.5, color: '#94a3b8' }}>
            Uzcard / Humo / Click / Payme
          </span>
          <span style={{ fontSize: 13, color: '#38bdf8', fontWeight: 600 }}>GRAND EDUCATION</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 24, fontFamily: '"JetBrains Mono", monospace', letterSpacing: 2, fontWeight: 700 }}>
            {cardInfo.card_number || DEFAULT_CARD_NUMBER}
          </span>
          <button
            type="button"
            className="btn sm"
            onClick={() => handleCopy(cardInfo.card_number || DEFAULT_CARD_NUMBER)}
            style={{
              background: copied ? '#10b981' : 'rgba(255, 255, 255, 0.1)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: '#fff',
            }}
          >
            {copied ? <><CheckIcon size={14} className="ico" /> {t('sub_card_copied')}</> : <><CopyIcon size={14} className="ico" /> {t('sub_copy_card')}</>}
          </button>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 12, marginBottom: 16 }}>
          <div>
            <span style={{ fontSize: 11, color: '#94a3b8', display: 'block', textTransform: 'uppercase' }}>{t('sub_card_holder')}:</span>
            <strong>{cardInfo.card_holder || DEFAULT_CARD_HOLDER}</strong>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span style={{ fontSize: 11, color: '#94a3b8', display: 'block', textTransform: 'uppercase' }}>{t('sub_transfer_amount')}:</span>
            <strong style={{ color: '#fbbf24', fontSize: 16 }}>{currentPrice.toLocaleString()} {t('sub_per_month').split('/')[0].trim()}</strong>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setPaymentModalOpen(true)}
          className="btn primary btn-glow"
          style={{ width: '100%', justifyContent: 'center', padding: '12px 16px', fontWeight: 700 }}
        >
          <ZapIcon size={16} className="ico" /> Karta orqali to'lash va chek yuklash (Telegram 1-click)
        </button>
      </div>

      {/* Drag & Drop Receipt Verification Form */}
      <div className="card" style={{ padding: 24, borderRadius: 16 }}>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>📸 {t('pricing_upload_title')}</h2>
        <p className="muted small" style={{ marginBottom: 16 }}>
          Click, Payme yoki Uzum ilovasidan to'lov muvaffaqiyatli o'tgan kvitansiyani yuklang.
        </p>

        {isSuccess === true && resultMessage && (
          <div
            style={{
              padding: '14px 18px',
              borderRadius: 10,
              background: 'rgba(16, 185, 129, 0.15)',
              border: '1px solid rgba(16, 185, 129, 0.4)',
              color: '#34d399',
              marginBottom: 16,
              fontSize: 14,
            }}
          >
            <SafeBoldText text={resultMessage} />
          </div>
        )}

        {isSuccess === false && resultMessage && (
          <div
            style={{
              padding: '14px 18px',
              borderRadius: 10,
              background: isBanned ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.15)',
              border: isBanned ? '2px solid #ef4444' : '1px solid rgba(245, 158, 11, 0.4)',
              color: isBanned ? '#f87171' : '#fbbf24',
              marginBottom: 16,
              fontSize: 14,
            }}
          >
            <SafeBoldText text={resultMessage} />
          </div>
        )}

        <form onSubmit={handleVerifySubmit}>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: dragOver ? '2px dashed #fbbf24' : '2px dashed var(--border)',
              borderRadius: 14,
              padding: '36px 20px',
              textAlign: 'center',
              cursor: 'pointer',
              background: dragOver ? 'rgba(245, 158, 11, 0.05)' : 'var(--card-2)',
              transition: 'all 0.2s ease',
              marginBottom: 16,
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/jpg"
              style={{ display: 'none' }}
              onChange={(e) => handleFileChange(e.target.files ? e.target.files[0] : null)}
            />

            {previewUrl ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                <img
                  src={previewUrl}
                  alt={t('pricing_receipt_alt')}
                  style={{ maxHeight: 200, maxWidth: '100%', borderRadius: 8, border: '1px solid var(--border)' }}
                />
                <span className="small muted">{t('pricing_choose_another')}</span>
              </div>
            ) : (
              <div>
                <span style={{ fontSize: 36, display: 'block', marginBottom: 8 }}>📥</span>
                <strong style={{ display: 'block', marginBottom: 4 }}>{t('pricing_drop_receipt')}</strong>
                <span className="small muted">{t('pricing_file_formats')}</span>
              </div>
            )}
          </div>

          <button
            type="submit"
            className="btn primary btn-glow"
            disabled={uploading || !selectedFile}
            style={{ width: '100%', justifyContent: 'center', fontWeight: 700, padding: '12px 20px' }}
          >
            {uploading ? t('pricing_sending') : t('pricing_submit')}
          </button>
        </form>
      </div>

      <CardPaymentModal
        isOpen={paymentModalOpen}
        initialTariff={selectedPlan.toUpperCase() as 'STARTER' | 'PRO' | 'PREMIUM'}
        onClose={() => setPaymentModalOpen(false)}
        onSuccess={() => setPaymentModalOpen(false)}
      />
    </div>
  );
}
