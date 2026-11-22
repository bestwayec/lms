import { useEffect, useState } from 'react';
import { useLang } from '../i18n/LangContext';
import {
  HomeworkAPI,
  type HomeworkCatalogResponse,
  type SchoolGroup,
} from '../lib/school';
import { School } from '../lib/api';
import {
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Eye,
  Sparkles,
  User,
  Users,
  X,
} from 'lucide-react';

interface TeacherHomeworkWizardProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  groups: SchoolGroup[];
  initialGroupId?: number | null;
}

export default function TeacherHomeworkWizard({
  isOpen,
  onClose,
  onSuccess,
  groups,
  initialGroupId,
}: TeacherHomeworkWizardProps) {
  const { t } = useLang();

  // Wizard Step (1, 2, 3)
  const [step, setStep] = useState<1 | 2 | 3>(1);

  // Step 1: Recipient
  const [recipientType, setRecipientType] = useState<'group' | 'student'>('group');
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(
    initialGroupId || (groups.length > 0 ? groups[0].id : null)
  );
  const [selectedStudentId, setSelectedStudentId] = useState<number | null>(null);

  // Step 2: Content Selection
  const [contentType, setContentType] = useState<'test' | 'essay' | 'vocabulary' | 'lesson' | 'custom'>('test');
  const [catalog, setCatalog] = useState<HomeworkCatalogResponse>({
    tests: [],
    essays: [],
    vocabulary: [],
    lessons: [],
  });
  const [loadingCatalog, setLoadingCatalog] = useState(false);

  const [selectedTestId, setSelectedTestId] = useState<number | null>(null);
  const [selectedEssayId, setSelectedEssayId] = useState<number | null>(null);
  const [selectedVocabId, setSelectedVocabId] = useState<number | null>(null);
  const [selectedLessonId, setSelectedLessonId] = useState<number | null>(null);

  // Step 3: Scheduling & Limits
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [timeLimit, setTimeLimit] = useState<number>(0);
  const [maxAttempts, setMaxAttempts] = useState<number>(1);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Submission & Validation
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Load catalog on open
  useEffect(() => {
    if (isOpen) {
      setLoadingCatalog(true);
      setErrorMsg(null);
      HomeworkAPI.getTeacherCatalog('all')
        .then((data) => {
          setCatalog(data);
          if (data.tests.length > 0 && !selectedTestId) {
            setSelectedTestId(data.tests[0].id);
            if (!title) setTitle(data.tests[0].title);
          }
        })
        .catch((err) => {
          console.error('Failed to load homework catalog:', err);
        })
        .finally(() => {
          setLoadingCatalog(false);
        });

      // Default due date: 3 days from now at 23:59
      const defaultDate = new Date();
      defaultDate.setDate(defaultDate.getDate() + 3);
      defaultDate.setHours(23, 59, 0, 0);
      setDueDate(defaultDate.toISOString().slice(0, 16));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  // Selected group object & student list
  const activeGroup = groups.find((g) => g.id === selectedGroupId) || null;
  const eligibleStudents = activeGroup?.students || [];

  // Handle content selection changes and auto-fill title
  const handleSelectTest = (testId: number) => {
    setSelectedTestId(testId);
    const item = catalog.tests.find((t) => t.id === testId);
    if (item) {
      setTitle(item.title);
      if (item.time_limit) setTimeLimit(item.time_limit);
    }
  };

  const handleSelectEssay = (essayId: number) => {
    setSelectedEssayId(essayId);
    const item = catalog.essays.find((e) => e.id === essayId);
    if (item) setTitle(`Esse: ${item.title}`);
  };

  const handleSelectVocab = (vocabId: number) => {
    setSelectedVocabId(vocabId);
    const item = catalog.vocabulary.find((v) => v.id === vocabId);
    if (item) setTitle(`Lug'at: ${item.title}`);
  };

  const handleSelectLesson = (lessonId: number) => {
    setSelectedLessonId(lessonId);
    const item = catalog.lessons.find((l) => l.id === lessonId);
    if (item) setTitle(`Dars vazifasi: ${item.title}`);
  };

  // Step 1 Validation
  const canProceedStep1 =
    recipientType === 'group' ? Boolean(selectedGroupId) : Boolean(selectedStudentId);

  // Step 2 Validation
  const canProceedStep2 =
    contentType === 'test'
      ? Boolean(selectedTestId)
      : contentType === 'essay'
      ? Boolean(selectedEssayId)
      : contentType === 'vocabulary'
      ? Boolean(selectedVocabId)
      : contentType === 'lesson'
      ? Boolean(selectedLessonId)
      : Boolean(title.trim());

  // Final Submit
  const handlePublishHomework = async () => {
    if (!title.trim()) {
      setErrorMsg('Vazifa sarlavhasini kiriting.');
      return;
    }
    if (!dueDate) {
      setErrorMsg('Topshirish muddatini tanlang.');
      return;
    }
    setErrorMsg(null);
    setSubmitting(true);

    const idempotencyKey = `hw_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;

    try {
      await School.createHomework({
        group_id: recipientType === 'group' && selectedGroupId ? selectedGroupId : undefined,
        student_id: recipientType === 'student' && selectedStudentId ? selectedStudentId : undefined,
        title: title.trim(),
        due_date: new Date(dueDate).toISOString(),
        description: description.trim(),
        content_type: contentType,
        test_id: contentType === 'test' && selectedTestId ? selectedTestId : undefined,
        essay_topic_id: contentType === 'essay' && selectedEssayId ? selectedEssayId : undefined,
        vocabulary_pack_id: contentType === 'vocabulary' && selectedVocabId ? selectedVocabId : undefined,
        lesson_id: contentType === 'lesson' && selectedLessonId ? selectedLessonId : undefined,
        time_limit: timeLimit,
        max_attempts: maxAttempts,
        idempotency_key: idempotencyKey,
      });

      onSuccess();
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(msg || 'Vazifani yaratishda xatolik yuz berdi.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1100,
        padding: 16,
      }}
    >
      <div
        style={{
          background: 'var(--card-bg, #fff)',
          borderRadius: 18,
          maxWidth: 640,
          width: '100%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
          overflow: 'hidden',
        }}
      >
        {/* Wizard Header */}
        <div
          style={{
            padding: '20px 24px 16px',
            borderBottom: '1px solid var(--border-color, #E5E7EB)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: '1.35rem', fontWeight: 900, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Sparkles size={20} color="#F59E0B" />
              <span>{t('hw_wizard_title') || 'Yangi uy vazifasi berish'}</span>
            </h2>
            <div style={{ display: 'flex', gap: 16, marginTop: 10, fontSize: 13, fontWeight: 700 }}>
              <span style={{ color: step >= 1 ? '#4F46E5' : '#9CA3AF' }}>1. Qabul qiluvchi</span>
              <span style={{ color: '#D1D5DB' }}>&gt;</span>
              <span style={{ color: step >= 2 ? '#4F46E5' : '#9CA3AF' }}>2. Topshiriq turi</span>
              <span style={{ color: '#D1D5DB' }}>&gt;</span>
              <span style={{ color: step === 3 ? '#4F46E5' : '#9CA3AF' }}>3. Muddat va Sozlamalar</span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4 }}
          >
            <X size={22} color="#6B7280" />
          </button>
        </div>

        {/* Wizard Body */}
        <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>
          {errorMsg && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: 8,
                background: '#FEE2E2',
                color: '#DC2626',
                fontSize: 13,
                fontWeight: 600,
                marginBottom: 16,
              }}
            >
              {errorMsg}
            </div>
          )}

          {/* STEP 1: SELECT RECIPIENT */}
          {step === 1 && (
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 8 }}>
                Vazifa kimga beriladi?
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 18 }}>
                <button
                  type="button"
                  onClick={() => setRecipientType('group')}
                  style={{
                    padding: 14,
                    borderRadius: 10,
                    border: recipientType === 'group' ? '2px solid #4F46E5' : '1px solid #D1D5DB',
                    background: recipientType === 'group' ? '#EEF2FF' : '#fff',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, fontSize: 14, color: recipientType === 'group' ? '#4338CA' : '#374151' }}>
                    <Users size={18} />
                    <span>Butun guruhga</span>
                  </div>
                  <div style={{ fontSize: 12, color: '#6B7280', marginTop: 4 }}>
                    Guruhdagi barcha o'quvchilarga biriktiriladi
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setRecipientType('student')}
                  style={{
                    padding: 14,
                    borderRadius: 10,
                    border: recipientType === 'student' ? '2px solid #4F46E5' : '1px solid #D1D5DB',
                    background: recipientType === 'student' ? '#EEF2FF' : '#fff',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, fontSize: 14, color: recipientType === 'student' ? '#4338CA' : '#374151' }}>
                    <User size={18} />
                    <span>Alohida o'quvchiga</span>
                  </div>
                  <div style={{ fontSize: 12, color: '#6B7280', marginTop: 4 }}>
                    Shaxsiy individual vazifa qilib beriladi
                  </div>
                </button>
              </div>

              {/* Group Selector */}
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                  {recipientType === 'group' ? 'Guruhni tanlang:' : "O'quvchi guruhini tanlang:"}
                </label>
                <select
                  value={selectedGroupId || ''}
                  onChange={(e) => setSelectedGroupId(Number(e.target.value) || null)}
                  style={{
                    width: '100%',
                    padding: 10,
                    borderRadius: 8,
                    border: '1px solid #D1D5DB',
                    fontSize: 14,
                  }}
                >
                  <option value="">-- Guruhni tanlang --</option>
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name} ({g.student_count} ta o'quvchi)
                    </option>
                  ))}
                </select>
              </div>

              {/* Individual Student Selector if applicable */}
              {recipientType === 'student' && selectedGroupId && (
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                    O'quvchini tanlang:
                  </label>
                  {eligibleStudents.length === 0 ? (
                    <div style={{ fontSize: 13, color: '#9CA3AF' }}>Bu guruhda o'quvchilar yo'q.</div>
                  ) : (
                    <select
                      value={selectedStudentId || ''}
                      onChange={(e) => setSelectedStudentId(Number(e.target.value) || null)}
                      style={{
                        width: '100%',
                        padding: 10,
                        borderRadius: 8,
                        border: '1px solid #D1D5DB',
                        fontSize: 14,
                      }}
                    >
                      <option value="">-- O'quvchini tanlang --</option>
                      {eligibleStudents.map((st) => (
                        <option key={st.id} value={st.id}>
                          {st.full_name || `${st.first_name} ${st.last_name}`} ({st.email})
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}
            </div>
          )}

          {/* STEP 2: CONTENT SELECTION */}
          {step === 2 && (
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 8 }}>
                Topshiriq turini tanlang:
              </label>

              {/* Content Type Tabs */}
              <div
                style={{
                  display: 'flex',
                  gap: 8,
                  marginBottom: 16,
                  overflowX: 'auto',
                  paddingBottom: 4,
                }}
              >
                {(
                  [
                    { id: 'test', label: 'Test sinovi' },
                    { id: 'essay', label: 'Esse (Writing)' },
                    { id: 'vocabulary', label: "Lug'at" },
                    { id: 'lesson', label: 'Dars' },
                    { id: 'custom', label: 'Maxsus yozma' },
                  ] as const
                ).map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setContentType(tab.id)}
                    style={{
                      padding: '8px 14px',
                      borderRadius: 8,
                      border: 'none',
                      background: contentType === tab.id ? '#4F46E5' : '#F3F4F6',
                      color: contentType === tab.id ? '#fff' : '#374151',
                      fontWeight: 700,
                      fontSize: 13,
                      cursor: 'pointer',
                    }}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {loadingCatalog ? (
                <div style={{ textAlign: 'center', padding: 30, color: '#6B7280' }}>
                  Katalog yuklanmoqda...
                </div>
              ) : (
                <div>
                  {/* Test Picker */}
                  {contentType === 'test' && (
                    <div>
                      <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                        E'lon qilingan testni tanlang:
                      </label>
                      {catalog.tests.length === 0 ? (
                        <div style={{ fontSize: 13, color: '#DC2626' }}>
                          E'lon qilingan testlar topilmadi. Avval Teacher Studio orqali test yarating va e'lon qiling.
                        </div>
                      ) : (
                        <select
                          value={selectedTestId || ''}
                          onChange={(e) => handleSelectTest(Number(e.target.value))}
                          style={{
                            width: '100%',
                            padding: 10,
                            borderRadius: 8,
                            border: '1px solid #D1D5DB',
                            fontSize: 14,
                          }}
                        >
                          <option value="">-- Testni tanlang --</option>
                          {catalog.tests.map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.title} ({t.questions_count} ta savol{t.time_limit ? `, ${t.time_limit} daq` : ''})
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  )}

                  {/* Essay Picker */}
                  {contentType === 'essay' && (
                    <div>
                      <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                        Esse mavzusini tanlang:
                      </label>
                      {catalog.essays.length === 0 ? (
                        <div style={{ fontSize: 13, color: '#9CA3AF' }}>Faol esse mavzulari topilmadi.</div>
                      ) : (
                        <select
                          value={selectedEssayId || ''}
                          onChange={(e) => handleSelectEssay(Number(e.target.value))}
                          style={{
                            width: '100%',
                            padding: 10,
                            borderRadius: 8,
                            border: '1px solid #D1D5DB',
                            fontSize: 14,
                          }}
                        >
                          <option value="">-- Mavzuni tanlang --</option>
                          {catalog.essays.map((e) => (
                            <option key={e.id} value={e.id}>
                              {e.title} ({e.task_type || 'Task'}, {e.min_words}-{e.max_words} so'z)
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  )}

                  {/* Vocabulary Picker */}
                  {contentType === 'vocabulary' && (
                    <div>
                      <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                        Lug'at to'plamini tanlang:
                      </label>
                      {catalog.vocabulary.length === 0 ? (
                        <div style={{ fontSize: 13, color: '#9CA3AF' }}>Lug'at to'plamlari topilmadi.</div>
                      ) : (
                        <select
                          value={selectedVocabId || ''}
                          onChange={(e) => handleSelectVocab(Number(e.target.value))}
                          style={{
                            width: '100%',
                            padding: 10,
                            borderRadius: 8,
                            border: '1px solid #D1D5DB',
                            fontSize: 14,
                          }}
                        >
                          <option value="">-- To'plamni tanlang --</option>
                          {catalog.vocabulary.map((v) => (
                            <option key={v.id} value={v.id}>
                              {v.title} ({v.words_count} ta so'z)
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  )}

                  {/* Lesson Picker */}
                  {contentType === 'lesson' && (
                    <div>
                      <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                        Darsni tanlang:
                      </label>
                      {catalog.lessons.length === 0 ? (
                        <div style={{ fontSize: 13, color: '#9CA3AF' }}>Darslar topilmadi.</div>
                      ) : (
                        <select
                          value={selectedLessonId || ''}
                          onChange={(e) => handleSelectLesson(Number(e.target.value))}
                          style={{
                            width: '100%',
                            padding: 10,
                            borderRadius: 8,
                            border: '1px solid #D1D5DB',
                            fontSize: 14,
                          }}
                        >
                          <option value="">-- Darsni tanlang --</option>
                          {catalog.lessons.map((l) => (
                            <option key={l.id} value={l.id}>
                              {l.title} ({l.course_title})
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  )}

                  {/* Custom Prompt */}
                  {contentType === 'custom' && (
                    <div>
                      <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                        Vazifa nomi:
                      </label>
                      <input
                        type="text"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="Masalan: Uyga berilgan matnni tahlil qilish"
                        style={{
                          width: '100%',
                          padding: 10,
                          borderRadius: 8,
                          border: '1px solid #D1D5DB',
                          fontSize: 14,
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* STEP 3: SCHEDULING, LIMITS & LIVE PREVIEW */}
          {step === 3 && (
            <div>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                  Vazifa sarlavhasi:
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  style={{
                    width: '100%',
                    padding: 10,
                    borderRadius: 8,
                    border: '1px solid #D1D5DB',
                    fontSize: 14,
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                  Topshirish muddati (Deadline):
                </label>
                <input
                  type="datetime-local"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  style={{
                    width: '100%',
                    padding: 10,
                    borderRadius: 8,
                    border: '1px solid #D1D5DB',
                    fontSize: 14,
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                  Qo'shimcha izoh yoki ko'rsatmalar (ixtiyoriy):
                </label>
                <textarea
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="O'quvchilar uchun topshiriq talablari..."
                  style={{
                    width: '100%',
                    padding: 10,
                    borderRadius: 8,
                    border: '1px solid #D1D5DB',
                    fontSize: 14,
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              {/* Collapsible Advanced Options */}
              <div style={{ marginBottom: 16 }}>
                <button
                  type="button"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    fontSize: 13,
                    fontWeight: 700,
                    color: '#4F46E5',
                    cursor: 'pointer',
                    padding: 0,
                  }}
                >
                  <ChevronDown
                    size={16}
                    style={{
                      transform: showAdvanced ? 'rotate(180deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s',
                    }}
                  />
                  <span>Qo'shimcha sozlamalar (Vaqt chegarasi, urinishlar)</span>
                </button>

                {showAdvanced && (
                  <div
                    style={{
                      marginTop: 10,
                      padding: 14,
                      background: '#F9FAFB',
                      borderRadius: 10,
                      border: '1px solid #E5E7EB',
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr',
                      gap: 12,
                    }}
                  >
                    <div>
                      <label style={{ display: 'block', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                        Vaqt chegarasi (daqiqa):
                      </label>
                      <input
                        type="number"
                        min={0}
                        max={300}
                        value={timeLimit}
                        onChange={(e) => setTimeLimit(Number(e.target.value) || 0)}
                        placeholder="0 = cheklanmagan"
                        style={{
                          width: '100%',
                          padding: 8,
                          borderRadius: 6,
                          border: '1px solid #D1D5DB',
                          fontSize: 13,
                        }}
                      />
                      <span style={{ fontSize: 11, color: '#6B7280' }}>0 = cheklanmagan</span>
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                        Maksimal urinishlar soni:
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={maxAttempts}
                        onChange={(e) => setMaxAttempts(Math.max(1, Number(e.target.value) || 1))}
                        style={{
                          width: '100%',
                          padding: 8,
                          borderRadius: 6,
                          border: '1px solid #D1D5DB',
                          fontSize: 13,
                        }}
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* LIVE PREVIEW BOX */}
              <div
                style={{
                  background: '#F0FDF4',
                  border: '1px dashed #86EFAC',
                  borderRadius: 12,
                  padding: 14,
                  marginTop: 10,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, color: '#15803D', marginBottom: 6 }}>
                  <Eye size={14} />
                  <span>O'quvchi ko'rinishi (Live Preview):</span>
                </div>
                <div style={{ fontWeight: 800, fontSize: 14, color: '#14532D' }}>{title || 'Topshiriq sarlavhasi'}</div>
                <div style={{ fontSize: 12, color: '#166534', marginTop: 4 }}>
                  Muddati: {dueDate ? new Date(dueDate).toLocaleString() : 'Ko\'rsatilmagan'} |{' '}
                  {recipientType === 'group' ? `Guruh: ${activeGroup?.name || ''}` : 'Individual o\'quvchi'}
                  {timeLimit > 0 ? ` | Vaqt: ${timeLimit} daqiqa` : ''}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Wizard Footer / Buttons */}
        <div
          style={{
            padding: '16px 24px',
            borderTop: '1px solid var(--border-color, #E5E7EB)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          {step > 1 ? (
            <button
              type="button"
              onClick={() => setStep((step - 1) as 1 | 2)}
              className="btn sm"
            >
              Orqaga
            </button>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="btn sm"
            >
              Bekor qilish
            </button>
          )}

          {step < 3 ? (
            <button
              type="button"
              onClick={() => setStep((step + 1) as 2 | 3)}
              disabled={step === 1 ? !canProceedStep1 : !canProceedStep2}
              className="btn sm primary"
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <span>Keyingisi</span>
              <ChevronRight size={14} />
            </button>
          ) : (
            <button
              type="button"
              onClick={handlePublishHomework}
              disabled={submitting || !title.trim() || !dueDate}
              className="btn sm primary"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontWeight: 800,
                background: '#059669',
              }}
            >
              <CheckCircle size={15} />
              <span>{submitting ? 'E\'lon qilinmoqda...' : 'Vazifani e\'lon qilish'}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
