import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useLang } from '../i18n/LangContext';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Copy,
  FileText,
  Plus,
  QrCode,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react';
import ClassroomQrModal from '../components/ClassroomQrModal';
import { type ConvertedQuestion, TestsApi } from '../lib/testing';

const FORMULA_SYMBOLS = [
  '₂', '₃', '₄', '⁺', '⁻', '²⁺', '³⁺', '²⁻', '³⁻',
  '→', '⇌', 'Δ', '℃', '²', '³', 'π', '√', '±', 'α', 'β', 'γ', '≈', '≠', '≤', '≥'
];

export default function TeacherAiConverter() {
  const { t } = useLang();
  // Step 1: Upload state
  const [file, setFile] = useState<File | null>(null);
  const [subject, setSubject] = useState<'uzbek' | 'english' | 'biology' | 'chemistry' | 'law'>('chemistry');
  const [activeGroup] = useState('11-A');
  const [activeInputRef, setActiveInputRef] = useState<{ qIndex: number; choiceCode?: string } | null>(null);
  const [converting, setConverting] = useState(false);
  const [conversionStep, setConversionStep] = useState<1 | 2 | 3>(1);
  const [qrModalOpen, setQrModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 2: Editor state
  const [isConverted, setIsConverted] = useState(false);
  const [testTitle, setTestTitle] = useState('');
  const [timeLimit, setTimeLimit] = useState(60);
  const [readingPassage, setReadingPassage] = useState('');
  const [questions, setQuestions] = useState<ConvertedQuestion[]>([]);

  // Step 3: Saved state
  const [saving, setSaving] = useState(false);
  const [savedResult, setSavedResult] = useState<{
    test_id: number;
    mock_code: string;
    title: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  // Handle file select
  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      const allowedTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'];
      if (!allowedTypes.includes(selected.type) && !selected.name.toLowerCase().endsWith('.pdf')) {
        setError('Faqat PDF yoki JPEG/PNG/WEBP rasm yuklashingiz mumkin.');
        setFile(null);
        return;
      }
      if (selected.size > 15 * 1024 * 1024) {
        setError('Fayl hajmi 15 MB dan oshmasligi kerak.');
        setFile(null);
        return;
      }
      setFile(selected);
      setError(null);
    }
  };

  // Convert document with Vision AI
  const handleConvert = async () => {
    if (!file) {
      setError('Iltimos, test rasmi yoki PDF faylini tanlang.');
      return;
    }

    setConverting(true);
    setConversionStep(1);
    setError(null);

    const stepTimer1 = setTimeout(() => setConversionStep(2), 1800);
    const stepTimer2 = setTimeout(() => setConversionStep(3), 4200);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('subject', subject);

      const res = await TestsApi.aiConvertDocument(formData);
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      if (res.success && res.data) {
        setTestTitle(res.data.test_title || 'AI Test');
        setReadingPassage(res.data.reading_passage || '');
        setQuestions(res.data.questions || []);
        setIsConverted(true);
      } else {
        throw new Error('Test ma\'lumotlarini ajratib olish imkoni bo\'lmadi.');
      }
    } catch (err: unknown) {
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      const msg = err instanceof Error ? err.message : 'Konvertatsiya jarayonida xatolik yuz berdi.';
      setError(msg);
    } finally {
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      setConverting(false);
    }
  };

  // Question editing helpers
  const updateQuestionText = (index: number, text: string) => {
    setQuestions((prev) =>
      prev.map((q, i) => (i === index ? { ...q, text } : q))
    );
  };

  const updateChoiceText = (qIndex: number, code: string, text: string) => {
    setQuestions((prev) =>
      prev.map((q, i) => {
        if (i !== qIndex) return q;
        return {
          ...q,
          choices: q.choices.map((c) => (c.code === code ? { ...c, text } : c)),
        };
      })
    );
  };

  const setCorrectAnswer = (qIndex: number, code: string) => {
    setQuestions((prev) =>
      prev.map((q, i) => (i === qIndex ? { ...q, correct_answer: code } : q))
    );
  };

  const updateExplanation = (index: number, explanation: string) => {
    setQuestions((prev) =>
      prev.map((q, i) => (i === index ? { ...q, explanation } : q))
    );
  };

  const insertFormula = (sym: string) => {
    if (!activeInputRef) {
      if (questions.length > 0) {
        updateQuestionText(0, (questions[0].text || '') + sym);
      }
      return;
    }
    const { qIndex, choiceCode } = activeInputRef;
    if (choiceCode) {
      const curChoice = questions[qIndex]?.choices.find((c) => c.code === choiceCode);
      updateChoiceText(qIndex, choiceCode, (curChoice?.text || '') + sym);
    } else {
      updateQuestionText(qIndex, (questions[qIndex]?.text || '') + sym);
    }
  };

  const removeQuestion = (index: number) => {
    setQuestions((prev) =>
      prev.filter((_, i) => i !== index).map((q, idx) => ({ ...q, order: idx + 1 }))
    );
  };

  const addQuestion = () => {
    setQuestions((prev) => [
      ...prev,
      {
        order: prev.length + 1,
        text: '',
        choices: [
          { code: 'A', text: '' },
          { code: 'B', text: '' },
          { code: 'C', text: '' },
          { code: 'D', text: '' },
        ],
        correct_answer: '',
        explanation: '',
        question_type: 'single_choice',
      },
    ]);
  };

  // Save converted test to database
  const handleSave = async () => {
    if (!testTitle.trim()) {
      setError('Iltimos, test nomini kiriting.');
      return;
    }
    if (questions.length === 0) {
      setError('Kamida 1 ta savol bo\'lishi shart.');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const res = await TestsApi.aiSaveConverted({
        test_title: testTitle,
        subject,
        time_limit_minutes: timeLimit,
        reading_passage: readingPassage.trim() || undefined,
        questions,
      });

      if (res.success) {
        setSavedResult({
          test_id: res.test_id,
          mock_code: res.mock_code,
          title: res.title,
        });
        setQrModalOpen(true);
      } else {
        throw new Error(res.message || 'Saqlashda xatolik yuz berdi.');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Saqlashda xatolik yuz berdi.';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const copyCode = () => {
    if (!savedResult) return;
    navigator.clipboard.writeText(savedResult.mock_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '1.5rem 1rem 4rem' }}>
      {/* Top back navigation */}
      <div style={{ marginBottom: '1.5rem' }}>
        <Link
          to="/panel"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: '0.88rem',
            color: 'var(--muted)',
            textDecoration: 'none',
            fontWeight: 600,
          }}
        >
          <ArrowLeft size={16} /> Boshqaruv paneliga qaytish
        </Link>
      </div>

      {/* Top 3 Command Tabs */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          background: 'var(--bg-surface)',
          padding: 6,
          borderRadius: 16,
          border: '1px solid var(--border-subtle)',
          marginBottom: 24,
          maxWidth: 580,
        }}
      >
        <button
          type="button"
          style={{
            flex: 1,
            padding: '10px 16px',
            borderRadius: 12,
            border: '1px solid rgba(99, 102, 241, 0.5)',
            background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(99, 102, 241, 0.08) 100%)',
            color: '#818cf8',
            fontWeight: 800,
            fontSize: '0.92rem',
            cursor: 'default',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
          }}
        >
          <span>✨</span> AI Konvertor
        </button>

        <Link
          to="/panel?tab=live"
          style={{
            flex: 1,
            padding: '10px 16px',
            borderRadius: 12,
            border: '1px solid transparent',
            background: 'transparent',
            color: 'var(--text-secondary)',
            fontWeight: 800,
            fontSize: '0.92rem',
            textDecoration: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
          }}
        >
          <span>📡</span> Jonli tablo
        </Link>

        <Link
          to="/panel?tab=vedomost"
          style={{
            flex: 1,
            padding: '10px 16px',
            borderRadius: 12,
            border: '1px solid transparent',
            background: 'transparent',
            color: 'var(--text-secondary)',
            fontWeight: 800,
            fontSize: '0.92rem',
            textDecoration: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
          }}
        >
          <span>📊</span> Vedomost
        </Link>
      </div>

      {/* Header */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 12px', borderRadius: 999, background: 'rgba(99, 102, 241, 0.1)', color: 'var(--accent, #6366f1)', fontSize: '0.8rem', fontWeight: 700, marginBottom: 8 }}>
          <Sparkles size={14} /> 10-soniyalik AI Vision Konvertor
        </div>
        <h1 style={{ margin: '0 0 6px 0', fontSize: '1.8rem', fontWeight: 900 }}>
          Qog'oz va PDF testdan 10 soniyada test yasash
        </h1>
        <p className="muted" style={{ margin: 0, fontSize: '0.95rem' }}>
          Kitob sahifasini rasmga oling yoki PDF faylni yuklang. Gemini Vision AI savollar, formulalar va variantlarni avtomatik ajratib oladi.
        </p>
      </div>

      {error && (
        <div
          style={{
            padding: '12px 16px',
            borderRadius: 12,
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#ef4444',
            fontSize: '0.9rem',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: '1.5rem',
          }}
        >
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* STEP 1: UPLOAD SCREEN */}
      {!isConverted && (
        <div className="card bento-card" style={{ padding: '2rem', borderRadius: 20 }}>
          {/* Subject Switcher */}
          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: 8 }}>
              1. Fan yo'nalishini tanlang:
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, padding: 4, background: 'var(--bg-elevated)', borderRadius: 12, border: '1px solid var(--border-subtle)' }}>
              <button
                type="button"
                className={`btn sm ${subject === 'chemistry' ? 'primary' : 'ghost'}`}
                onClick={() => setSubject('chemistry')}
                style={{ borderRadius: 8 }}
              >
                🧪 Kimyo (Milliy sertifikat)
              </button>
              <button
                type="button"
                className={`btn sm ${subject === 'biology' ? 'primary' : 'ghost'}`}
                onClick={() => setSubject('biology')}
                style={{ borderRadius: 8 }}
              >
                🧬 Biologiya (Milliy sertifikat)
              </button>
              <button
                type="button"
                className={`btn sm ${subject === 'english' ? 'primary' : 'ghost'}`}
                onClick={() => setSubject('english')}
                style={{ borderRadius: 8 }}
              >
                🇬🇧 English (IELTS & CEFR)
              </button>
              <button
                type="button"
                className={`btn sm ${subject === 'law' ? 'primary' : 'ghost'}`}
                onClick={() => setSubject('law')}
                style={{ borderRadius: 8 }}
              >
                ⚖️ Huquqshunoslik (Yurisprudensiya)
              </button>
              <button
                type="button"
                className={`btn sm ${subject === 'uzbek' ? 'primary' : 'ghost'}`}
                onClick={() => setSubject('uzbek')}
                style={{ borderRadius: 8 }}
              >
                🇺🇿 Ona tili va Adabiyot
              </button>
            </div>
          </div>

          {/* Drag & Drop Area */}
          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
              <label style={{ fontSize: '0.9rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                2. Test varag'ini tashlang — AI qolganini qiladi
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span
                  style={{
                    padding: '4px 12px',
                    borderRadius: 999,
                    background: 'rgba(16, 185, 129, 0.15)',
                    border: '1px solid rgba(16, 185, 129, 0.35)',
                    color: '#10B981',
                    fontSize: 12,
                    fontWeight: 800,
                  }}
                >
                  🧪 {subject === 'chemistry' ? 'Kimyo' : subject === 'biology' ? 'Biologiya' : subject === 'english' ? 'Ingliz tili' : subject === 'law' ? 'Huquq' : 'Ona tili'} • {activeGroup}
                </span>
              </div>
            </div>

            <label
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '3rem 1.5rem',
                border: '2px dashed rgba(99, 102, 241, 0.4)',
                borderRadius: 20,
                background: file ? 'rgba(99, 102, 241, 0.05)' : 'var(--bg-surface)',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
            >
              <input
                type="file"
                accept=".pdf,image/png,image/jpeg,image/jpg,image/webp,.docx"
                onChange={onFileChange}
                style={{ display: 'none' }}
              />
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: 20,
                  background: 'rgba(99, 102, 241, 0.12)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#6366f1',
                  marginBottom: 16,
                  boxShadow: '0 8px 20px rgba(99, 102, 241, 0.15)',
                }}
              >
                {file ? <FileText size={32} /> : <Upload size={32} />}
              </div>

              <h3 style={{ margin: '0 0 6px', fontSize: '1.25rem', fontWeight: 900, color: 'var(--text-primary)' }}>
                {file ? file.name : "Faylni shu yerga tashlang"}
              </h3>
              <p className="muted" style={{ margin: '0 0 16px', fontSize: '0.9rem', maxWidth: 480, textAlign: 'center', lineHeight: 1.5 }}>
                Word, PDF yoki telefonda olingan rasm. Formulalar, variantlar va javob kalitlari avtomatik ajratiladi
              </p>

              {/* Supported format chips */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center', marginBottom: 18 }}>
                <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 999, background: 'rgba(255, 255, 255, 0.06)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                  📄 .docx
                </span>
                <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 999, background: 'rgba(255, 255, 255, 0.06)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                  📑 .pdf
                </span>
                <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 999, background: 'rgba(255, 255, 255, 0.06)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                  🖼 .jpg / .png
                </span>
              </div>

              {/* Indigo button */}
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '10px 20px',
                  borderRadius: 12,
                  background: 'linear-gradient(135deg, #4F46E5 0%, #4338CA 100%)',
                  color: '#FFFFFF',
                  fontWeight: 800,
                  fontSize: 14,
                  boxShadow: '0 4px 14px rgba(79, 70, 229, 0.35)',
                }}
              >
                📁 Fayl tanlash yoki rasmga olish
              </span>
            </label>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="btn primary"
              disabled={!file || converting}
              onClick={handleConvert}
              style={{ minHeight: 46, padding: '0 24px', fontWeight: 800 }}
            >
              {converting ? (
                <>
                  <Sparkles size={16} className="spin" /> AI hujjatni tahlil qilmoqda...
                </>
              ) : (
                <>
                  <Sparkles size={16} /> AI bilan testga aylantirish
                </>
              )}
            </button>
          </div>

          {converting && (
            <div
              style={{
                marginTop: '1.5rem',
                padding: '1.25rem',
                borderRadius: 14,
                background: 'rgba(99, 102, 241, 0.08)',
                border: '1.5px solid rgba(99, 102, 241, 0.3)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 800, color: 'var(--ink)' }}>
                  ✨ AI Vision tahlil jarayoni...
                </span>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6366f1' }}>
                  {conversionStep === 1 ? '30%' : conversionStep === 2 ? '65%' : '92%'}
                </span>
              </div>
              <div style={{ height: 6, width: '100%', background: 'rgba(255, 255, 255, 0.1)', borderRadius: 999, overflow: 'hidden', marginBottom: 16 }}>
                <div
                  style={{
                    height: '100%',
                    width: conversionStep === 1 ? '30%' : conversionStep === 2 ? '65%' : '92%',
                    background: 'linear-gradient(90deg, #6366f1, #a855f7)',
                    transition: 'width 0.4s ease',
                  }}
                />
              </div>
              <div style={{ display: 'grid', gap: 8, fontSize: '0.85rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: conversionStep >= 1 ? '#10b981' : '#64748b' }}>
                  <span>{conversionStep > 1 ? '✅' : '⏳'}</span>
                  <span style={{ fontWeight: conversionStep === 1 ? 800 : 500 }}>1. Fayl o'qilmoqda...</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: conversionStep >= 2 ? (conversionStep > 2 ? '#10b981' : '#6366f1') : '#64748b' }}>
                  <span>{conversionStep > 2 ? '✅' : conversionStep === 2 ? '⏳' : '⚪'}</span>
                  <span style={{ fontWeight: conversionStep === 2 ? 800 : 500 }}>2. Savollar va formulalar ajratilmoqda...</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: conversionStep === 3 ? '#6366f1' : '#64748b' }}>
                  <span>{conversionStep === 3 ? '⏳' : '⚪'}</span>
                  <span style={{ fontWeight: conversionStep === 3 ? 800 : 500 }}>3. Javob kalitlari tekshirilmoqda...</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* STEP 2: INTERACTIVE TEST EDITOR */}
      {isConverted && !savedResult && (
        <div>
          {/* Top Test Settings Card */}
          <div className="card" style={{ padding: '1.5rem', borderRadius: 16, marginBottom: '1.5rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(280px, 100%), 1fr))', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, marginBottom: 4 }}>
                  Test nomi:
                </label>
                <input
                  type="text"
                  value={testTitle}
                  onChange={(e) => setTestTitle(e.target.value)}
                  placeholder="Masalan: Ona tili 10-sinf diagnostika testi"
                  style={{ width: '100%', fontWeight: 700 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, marginBottom: 4 }}>
                  Vaqt me'yori (daqiqa):
                </label>
                <input
                  type="number"
                  min="5"
                  max="180"
                  value={timeLimit}
                  onChange={(e) => setTimeLimit(Number(e.target.value) || 60)}
                  style={{ width: '100%' }}
                />
              </div>
            </div>

            {/* Reading Passage Accordion */}
            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, marginBottom: 4 }}>
                Umumiy o'qish matni (Reading Passage) — ixtiyoriy:
              </label>
              <textarea
                rows={4}
                value={readingPassage}
                onChange={(e) => setReadingPassage(e.target.value)}
                placeholder="Agar testda bir nechta savolga daxldor umumiy matn bo'lsa, shu yerga kiriting..."
                style={{ width: '100%', fontSize: '0.9rem', lineHeight: 1.5 }}
              />
            </div>
          </div>

          {/* 2-Column Split: Ilmiy Formula Paneli on Left + Savollar on Right */}
          <div className="teacher-editor-layout">
            {/* Left Column: Ilmiy Formula Paneli */}
            <div
              style={{
                position: 'sticky',
                top: 90,
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 16,
                padding: 16,
                boxShadow: '0 8px 24px rgba(0,0,0,0.06)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 20 }}>🧪</span>
                <strong style={{ fontSize: '0.95rem', color: 'var(--text-primary)' }}>Ilmiy Formula Paneli</strong>
              </div>
              <p className="muted small" style={{ margin: '0 0 12px', fontSize: 11, lineHeight: 1.4 }}>
                Belgini bosish orqali oxirgi tahrirlanayotgan savol matni yoki variantiga qo'shing:
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
                {FORMULA_SYMBOLS.map((sym) => (
                  <button
                    key={sym}
                    type="button"
                    onClick={() => insertFormula(sym)}
                    style={{
                      height: 38,
                      borderRadius: 8,
                      border: '1px solid var(--border-subtle)',
                      background: 'var(--bg-elevated)',
                      color: 'var(--text-primary)',
                      fontSize: 16,
                      fontWeight: 800,
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                    title={`${sym} belgisini kiritish`}
                  >
                    {sym}
                  </button>
                ))}
              </div>
            </div>

            {/* Right Column: Savollar ro'yxati */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <h2 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 800 }}>
                  Ajratib olingan savollar ({questions.length} ta)
                </h2>
                <button
                  type="button"
                  className="btn sm ghost"
                  onClick={addQuestion}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                >
                  <Plus size={16} /> Savol qo'shish
                </button>
              </div>

              {/* Questions List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {questions.map((q, qIndex) => (
              <div
                key={qIndex}
                className="card"
                style={{
                  padding: '1.25rem',
                  borderRadius: 14,
                  border: '1px solid var(--border)',
                  background: 'var(--card)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <span
                    className="badge"
                    style={{
                      background: 'rgba(99, 102, 241, 0.15)',
                      color: 'var(--accent, #6366f1)',
                      fontWeight: 800,
                      borderRadius: 8,
                      padding: '4px 10px',
                    }}
                  >
                    #{q.order}-savol
                  </span>
                  <button
                    type="button"
                    className="btn ghost sm"
                    onClick={() => removeQuestion(qIndex)}
                    title="Savolni o'chirish"
                    style={{ color: '#ef4444' }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>

                {/* Question Text */}
                <div style={{ marginBottom: 12 }}>
                  <textarea
                    rows={2}
                    value={q.text}
                    onFocus={() => setActiveInputRef({ qIndex })}
                    onChange={(e) => updateQuestionText(qIndex, e.target.value)}
                    placeholder="Savol matnini kiriting..."
                    style={{ width: '100%', fontWeight: 600, fontSize: '0.95rem' }}
                  />
                </div>

                {/* Choices Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(240px, 100%), 1fr))', gap: 10, marginBottom: 12 }}>
                  {q.choices.map((c) => {
                    const isSelected = q.correct_answer === c.code;
                    return (
                      <div
                        key={c.code}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '6px 10px',
                          borderRadius: 10,
                          border: isSelected ? '2px solid #10b981' : '1px solid var(--border)',
                          background: isSelected ? 'rgba(16, 185, 129, 0.08)' : 'var(--bg)',
                        }}
                      >
                        <button
                          type="button"
                          onClick={() => setCorrectAnswer(qIndex, c.code)}
                          style={{
                            width: 28,
                            height: 28,
                            borderRadius: '50%',
                            border: 'none',
                            background: isSelected ? '#10b981' : 'var(--border)',
                            color: isSelected ? '#ffffff' : 'var(--muted)',
                            fontWeight: 800,
                            fontSize: '0.8rem',
                            cursor: 'pointer',
                            flexShrink: 0,
                          }}
                          title="To'g'ri javob sifatida belgilash"
                        >
                          {c.code}
                        </button>
                        <input
                          type="text"
                          value={c.text}
                          onFocus={() => setActiveInputRef({ qIndex, choiceCode: c.code })}
                          onChange={(e) => updateChoiceText(qIndex, c.code, e.target.value)}
                          placeholder={`${c.code} varianti`}
                          style={{
                            border: 'none',
                            background: 'transparent',
                            padding: 0,
                            fontSize: '0.88rem',
                            width: '100%',
                            outline: 'none',
                          }}
                        />
                      </div>
                    );
                  })}
                </div>

                {!q.correct_answer && (
                  <p className="small" role="alert" style={{ color: 'var(--danger)', margin: '0 0 8px' }}>
                    {t('cv_pick_answer')}
                  </p>
                )}

                {/* Explanation */}
                <div>
                  <input
                    type="text"
                    value={q.explanation || ''}
                    onChange={(e) => updateExplanation(qIndex, e.target.value)}
                    placeholder="💡 Izoh: to'g'ri javobning grammatik yoki ilmiy asosi (ixtiyoriy)..."
                    style={{ width: '100%', fontSize: '0.82rem', color: 'var(--muted)' }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Sticky Bottom Actions Bar */}
          <div
            style={{
              position: 'sticky',
              bottom: '1rem',
              marginTop: '2rem',
              padding: '1rem 1.5rem',
              borderRadius: 16,
              background: 'var(--card)',
              border: '1px solid var(--border)',
              boxShadow: '0 20px 40px rgba(0, 0, 0, 0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              zIndex: 30,
              flexWrap: 'wrap',
              gap: 12,
            }}
          >
            <div>
              <strong style={{ fontSize: '1rem', display: 'block' }}>
                Jami: {questions.length} ta savol
              </strong>
              <span className="muted small">
                Har bir savol to'g'ri javobi belgilanganini tekshiring
              </span>
            </div>

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                type="button"
                className="btn ghost"
                onClick={() => setIsConverted(false)}
                disabled={saving}
              >
                Orqaga
              </button>
              <button
                type="button"
                className="btn primary"
                onClick={handleSave}
                disabled={saving}
                style={{ minHeight: 46, padding: '0 24px', fontWeight: 800 }}
              >
                {saving ? 'Saqlanmoqda...' : '💾 Testni tasdiqlash va saqlash'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )}

      {/* STEP 3: SUCCESS MODAL / SCREEN */}
      {savedResult && (
        <div className="card" style={{ padding: '2.5rem', borderRadius: 20, textAlign: 'center' }}>
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: '50%',
              background: 'rgba(16, 185, 129, 0.15)',
              color: '#10b981',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 16,
            }}
          >
            <CheckCircle2 size={36} />
          </div>
          <h2 style={{ fontSize: '1.6rem', fontWeight: 900, margin: '0 0 8px 0' }}>
            Test muvaffaqiyatli saqlandi!
          </h2>
          <p className="muted" style={{ maxWidth: 500, margin: '0 auto 20px auto', fontSize: '0.95rem' }}>
            Test platformada nashr etildi. O'quvchilaringiz quyidagi unikal kod orqali testga tezkor ulanishlari mumkin:
          </p>

          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 24px',
              borderRadius: 14,
              background: 'rgba(99, 102, 241, 0.1)',
              border: '1px solid rgba(99, 102, 241, 0.3)',
              marginBottom: '2rem',
            }}
          >
            <span style={{ fontSize: '1.5rem', fontWeight: 900, letterSpacing: '0.05em', color: 'var(--accent, #6366f1)' }}>
              {savedResult.mock_code}
            </span>
            <button
              type="button"
              className="btn sm ghost"
              onClick={copyCode}
              title="Kodni nusxalash"
            >
              <Copy size={16} /> {copied ? 'Nusxalandi!' : 'Nusxalash'}
            </button>
          </div>

          <div style={{ display: 'flex', justifyContent: 'center', gap: 12, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn primary"
              onClick={() => setQrModalOpen(true)}
              style={{
                minHeight: 44,
                padding: '0 20px',
                background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                border: 'none',
                fontWeight: 800,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <QrCode size={18} />
              <span>📱 Sinfxona QR-Kodi va Ulashish</span>
            </button>
            <Link to={`/tests/${savedResult.test_id}`} className="btn" style={{ minHeight: 44, padding: '0 20px' }}>
              Testni ko'rish (Preview)
            </Link>
            <button
              type="button"
              className="btn ghost"
              onClick={() => {
                setSavedResult(null);
                setIsConverted(false);
                setFile(null);
              }}
            >
              Yana yangi test yuklash
            </button>
            <Link to="/panel" className="btn ghost">
              Ustoz kabineti
            </Link>
          </div>
        </div>
      )}

      {savedResult && qrModalOpen && (
        <ClassroomQrModal
          isOpen={qrModalOpen}
          onClose={() => setQrModalOpen(false)}
          title={savedResult.title || testTitle}
          code={savedResult.mock_code}
          webUrl={`https://grandec.uz/tests/${savedResult.test_id}`}
          tmaUrl={`https://t.me/uz_essaygrader_bot/app?startapp=test_${savedResult.test_id}`}
          subtitle="Sinfxona doskasiga chiqaring yoki Telegram guruhga yuboring"
        />
      )}
    </div>
  );
}
