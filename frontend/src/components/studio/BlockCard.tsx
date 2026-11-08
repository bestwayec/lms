import { useRef, useState } from 'react';
import { ArrowDown, ArrowUp, ImagePlus, Music, Plus, Trash2, X } from 'lucide-react';
import { useLang } from '../../i18n/LangContext';
import {
  BLOCK_TYPES,
  LETTERS,
  SECTION_CODES,
  StudioApi,
  TF_LABELS,
  YN_LABELS,
  convertBlock,
  gapQuestions,
  type BlockType,
  type SectionCode,
  type StudioBlock,
  type StudioIssue,
  type StudioQuestion,
} from '../../lib/studio';

interface Props {
  block: StudioBlock;
  index: number;
  count: number;
  issues: StudioIssue[];
  nextNumber: number;
  onChange: (b: StudioBlock) => void;
  onRemove: () => void;
  onMove: (dir: -1 | 1) => void;
}

const has = (issues: StudioIssue[], code: string, number: number | null = null, option: number | null = null) =>
  issues.some((i) => i.code === code && i.number === number && (option === null || i.option === option));

/** Editor for one block (one question group). Keyboard: Enter in the last question adds one. */
export default function BlockCard({ block, index, count, issues, nextNumber, onChange, onRemove, onMove }: Props) {
  const { t } = useLang();
  const [uploading, setUploading] = useState<'audio' | 'image' | null>(null);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const audioRef = useRef<HTMLInputElement>(null);
  const imageRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLElement>(null);

  const set = (patch: Partial<StudioBlock>) => onChange({ ...block, ...patch });
  const setQ = (qi: number, patch: Partial<StudioQuestion>) =>
    set({ questions: block.questions.map((q, i) => (i === qi ? { ...q, ...patch } : q)) });

  const addQuestion = (focus = true) => {
    const q: StudioQuestion = {
      number: nextNumber,
      text: '',
      options: block.type === 'mcq' ? Array(Math.max(block.questions.at(-1)?.options.length ?? 3, 2)).fill('') : [],
      answer: '',
    };
    set({ questions: [...block.questions, q] });
    if (focus) {
      requestAnimationFrame(() => {
        const inputs = rootRef.current?.querySelectorAll<HTMLTextAreaElement>('.studio-q__text');
        inputs?.[inputs.length - 1]?.focus();
      });
    }
  };

  const upload = async (file: File | undefined, kind: 'audio' | 'image') => {
    if (!file) return;
    setUploading(kind);
    setUploadErr(null);
    try {
      const res = await StudioApi.uploadMedia(file, kind);
      set(kind === 'audio' ? { audio_path: res.path, audio_url: res.url } : { image_path: res.path, image_url: res.url });
    } catch (e) {
      const code = (e as { code?: string }).code;
      setUploadErr(code ? t(`studio_err_${code}`) : e instanceof Error ? e.message : t('err_retry_js'));
    } finally {
      setUploading(null);
    }
  };

  const blockIssue = (code: string) => has(issues, code);
  const gapQs = block.type === 'gap' ? gapQuestions(block.gap_text) : [];
  const tfLabels = block.options[0] === 'YES' ? YN_LABELS : TF_LABELS;

  return (
    <section
      ref={rootRef}
      className={`studio-block${issues.length ? ' has-issues' : ''}`}
      id={`studio-block-${index}`}
      aria-label={`${t('studio_block')} ${index + 1}`}
    >
      <header className="studio-block__head">
        <span className="studio-block__num">{index + 1}</span>
        <select
          aria-label={t('studio_block_type')}
          value={block.type}
          onChange={(e) => onChange(convertBlock(block, e.target.value as BlockType))}
        >
          {BLOCK_TYPES.map((bt) => (
            <option key={bt} value={bt}>
              {t(`studio_type_${bt}`)}
            </option>
          ))}
        </select>
        <select
          aria-label={t('studio_section')}
          value={block.section}
          onChange={(e) => set({ section: e.target.value as SectionCode })}
        >
          {SECTION_CODES.map((s) => (
            <option key={s} value={s}>
              {t(`studio_section_${s.toLowerCase()}`)}
            </option>
          ))}
        </select>
        <div className="studio-block__tools">
          <button type="button" className="studio-icon" onClick={() => onMove(-1)} disabled={index === 0} aria-label={t('studio_move_up')}>
            <ArrowUp size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="studio-icon"
            onClick={() => onMove(1)}
            disabled={index === count - 1}
            aria-label={t('studio_move_down')}
          >
            <ArrowDown size={16} aria-hidden="true" />
          </button>
          <button type="button" className="studio-icon is-danger" onClick={onRemove} aria-label={t('studio_remove_block')}>
            <Trash2 size={16} aria-hidden="true" />
          </button>
        </div>
      </header>

      {(blockIssue('no_questions') || blockIssue('gap_no_markers') || blockIssue('too_few_options')) && (
        <ul className="studio-block__issues">
          {['no_questions', 'gap_no_markers', 'too_few_options'].filter((c) => blockIssue(c)).map((c) => (
            <li key={c}>{t(`studio_issue_${c}`)}</li>
          ))}
        </ul>
      )}

      <div className="studio-grid2">
        <label className="studio-field">
          <span>{t('studio_block_title')}</span>
          <input value={block.title} onChange={(e) => set({ title: e.target.value })} maxLength={255} />
        </label>
        <label className="studio-field">
          <span>{t('studio_instructions')}</span>
          <input value={block.instructions} onChange={(e) => set({ instructions: e.target.value })} maxLength={3000} />
        </label>
      </div>

      <label className="studio-field">
        <span>{t('studio_passage')}</span>
        <textarea
          rows={block.passage ? 5 : 2}
          value={block.passage}
          placeholder={t('studio_passage_ph')}
          onChange={(e) => set({ passage: e.target.value })}
        />
      </label>

      <div className="studio-media">
        <input
          ref={audioRef}
          type="file"
          accept=".mp3,.m4a,.wav,.ogg,audio/*"
          hidden
          onChange={(e) => {
            void upload(e.target.files?.[0], 'audio');
            e.target.value = '';
          }}
        />
        <input
          ref={imageRef}
          type="file"
          accept=".png,.jpg,.jpeg,.webp"
          hidden
          onChange={(e) => {
            void upload(e.target.files?.[0], 'image');
            e.target.value = '';
          }}
        />
        <button
          type="button"
          className={`btn sm${blockIssue('audio_missing') ? ' is-invalid' : ''}`}
          onClick={() => audioRef.current?.click()}
          disabled={uploading !== null}
        >
          <Music size={14} aria-hidden="true" /> {uploading === 'audio' ? t('studio_uploading') : t('studio_audio_upload')}
        </button>
        {block.audio_path && (
          <span className="studio-chip">
            {t('studio_audio_linked')}
            <button type="button" aria-label={t('studio_remove_media')} onClick={() => set({ audio_path: '', audio_url: '' })}>
              <X size={12} aria-hidden="true" />
            </button>
          </span>
        )}
        <button type="button" className="btn sm" onClick={() => imageRef.current?.click()} disabled={uploading !== null}>
          <ImagePlus size={14} aria-hidden="true" /> {uploading === 'image' ? t('studio_uploading') : t('studio_image_upload')}
        </button>
        {block.image_path && (
          <span className="studio-chip">
            {t('studio_image_linked')}
            <button type="button" aria-label={t('studio_remove_media')} onClick={() => set({ image_path: '', image_url: '' })}>
              <X size={12} aria-hidden="true" />
            </button>
          </span>
        )}
        {blockIssue('audio_missing') && <span className="studio-err-text">{t('studio_issue_audio_missing')}</span>}
        {uploadErr && <span className="studio-err-text" role="alert">{uploadErr}</span>}
      </div>

      {block.type === 'tfng' && (
        <label className="studio-field studio-field--inline">
          <span>{t('studio_tf_labels')}</span>
          <select value={tfLabels[0]} onChange={(e) => set({ options: e.target.value === 'YES' ? [...YN_LABELS] : [...TF_LABELS], questions: block.questions.map((q) => ({ ...q, answer: '' })) })}>
            <option value="TRUE">{TF_LABELS.join(' / ')}</option>
            <option value="YES">{YN_LABELS.join(' / ')}</option>
          </select>
        </label>
      )}

      {block.type === 'matching' && (
        <fieldset className="studio-options">
          <legend>{t('studio_shared_options')}</legend>
          {block.options.map((o, oi) => (
            <div key={oi} className="studio-opt">
              <span className="studio-opt__letter">{LETTERS[oi]}</span>
              <input
                className={has(issues, 'empty_option', null, oi) ? 'is-invalid' : ''}
                value={o}
                aria-label={`${t('studio_option')} ${LETTERS[oi]}`}
                onChange={(e) => set({ options: block.options.map((x, i) => (i === oi ? e.target.value : x)) })}
              />
              <button
                type="button"
                className="studio-icon"
                aria-label={t('studio_remove_option')}
                onClick={() => set({ options: block.options.filter((_, i) => i !== oi) })}
              >
                <X size={14} aria-hidden="true" />
              </button>
            </div>
          ))}
          {block.options.length < 12 && (
            <button type="button" className="btn sm ghost" onClick={() => set({ options: [...block.options, ''] })}>
              <Plus size={14} aria-hidden="true" /> {t('studio_add_option')}
            </button>
          )}
        </fieldset>
      )}

      {block.type === 'gap' ? (
        <div className="studio-field">
          <label htmlFor={`gap-${index}`}>
            <span>{t('studio_gap_text')}</span>
          </label>
          <textarea
            id={`gap-${index}`}
            rows={5}
            className={`studio-mono${blockIssue('gap_no_markers') ? ' is-invalid' : ''}`}
            value={block.gap_text}
            placeholder={t('studio_gap_ph')}
            onChange={(e) => set({ gap_text: e.target.value, questions: gapQuestions(e.target.value) })}
          />
          <p className="studio-hint">{t('studio_gap_hint')}</p>
          {gapQs.length > 0 && (
            <ul className="studio-gaplist">
              {gapQs.map((q) => (
                <li
                  key={q.number}
                  className={has(issues, 'missing_answer', q.number) || has(issues, 'duplicate_number', q.number) ? 'is-invalid' : ''}
                >
                  <b>{q.number}</b> {q.answer ? q.answer.split('|').join(' / ') : t('studio_no_answer')}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <ol className="studio-qs">
          {block.questions.map((q, qi) => {
            const missing = has(issues, 'missing_answer', q.number);
            return (
              <li key={qi} className={`studio-q${missing || has(issues, 'duplicate_number', q.number) ? ' has-issue' : ''}`}>
                <div className="studio-q__row">
                  <input
                    className={`studio-q__num${has(issues, 'duplicate_number', q.number) ? ' is-invalid' : ''}`}
                    type="number"
                    min={1}
                    max={999}
                    aria-label={t('studio_q_number')}
                    value={q.number}
                    onChange={(e) => setQ(qi, { number: Number(e.target.value) || 0 })}
                  />
                  <textarea
                    className={`studio-q__text${has(issues, 'empty_question', q.number) ? ' is-invalid' : ''}`}
                    rows={1}
                    aria-label={`${t('studio_q_text')} ${q.number}`}
                    placeholder={t(block.type === 'matching' ? 'studio_prompt_ph' : 'studio_q_ph')}
                    value={q.text}
                    onChange={(e) => setQ(qi, { text: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey && qi === block.questions.length - 1) {
                        e.preventDefault();
                        addQuestion();
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="studio-icon"
                    aria-label={t('studio_remove_question')}
                    onClick={() => set({ questions: block.questions.filter((_, i) => i !== qi) })}
                  >
                    <X size={14} aria-hidden="true" />
                  </button>
                </div>

                {block.type === 'mcq' && (
                  <div className="studio-q__opts" role="radiogroup" aria-label={`${t('studio_correct')} ${q.number}`}>
                    {q.options.map((o, oi) => (
                      <div key={oi} className={`studio-opt${q.answer === LETTERS[oi] ? ' is-correct' : ''}`}>
                        <label className="studio-opt__pick">
                          <input
                            type="radio"
                            name={`ans-${block.key}-${qi}`}
                            checked={q.answer === LETTERS[oi]}
                            onChange={() => setQ(qi, { answer: LETTERS[oi] })}
                          />
                          <span className="studio-opt__letter">{LETTERS[oi]}</span>
                        </label>
                        <input
                          className={has(issues, 'empty_option', q.number, oi) ? 'is-invalid' : ''}
                          value={o}
                          aria-label={`${t('studio_option')} ${LETTERS[oi]}`}
                          onChange={(e) => setQ(qi, { options: q.options.map((x, i) => (i === oi ? e.target.value : x)) })}
                        />
                        <button
                          type="button"
                          className="studio-icon"
                          aria-label={t('studio_remove_option')}
                          onClick={() =>
                            setQ(qi, {
                              options: q.options.filter((_, i) => i !== oi),
                              answer: q.answer === LETTERS[oi] ? '' : q.answer,
                            })
                          }
                        >
                          <X size={14} aria-hidden="true" />
                        </button>
                      </div>
                    ))}
                    {q.options.length < 12 && (
                      <button type="button" className="btn sm ghost" onClick={() => setQ(qi, { options: [...q.options, ''] })}>
                        <Plus size={14} aria-hidden="true" /> {t('studio_add_option')}
                      </button>
                    )}
                    {has(issues, 'too_few_options', q.number) && (
                      <span className="studio-err-text">{t('studio_issue_too_few_options')}</span>
                    )}
                  </div>
                )}

                {(block.type === 'tfng' || block.type === 'matching') && (
                  <div className="studio-q__answer">
                    <span>{t('studio_correct')}</span>
                    <div className="studio-seg" role="radiogroup">
                      {(block.type === 'tfng' ? tfLabels : block.options.map((_, i) => LETTERS[i])).map((label) => (
                        <button
                          key={label}
                          type="button"
                          role="radio"
                          aria-checked={q.answer === label}
                          className={q.answer === label ? 'is-on' : ''}
                          onClick={() => setQ(qi, { answer: label })}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {block.type === 'short' && (
                  <label className="studio-q__answer">
                    <span>{t('studio_correct')}</span>
                    <input
                      className={missing ? 'is-invalid' : ''}
                      value={q.answer}
                      placeholder={t('studio_short_ph')}
                      onChange={(e) => setQ(qi, { answer: e.target.value })}
                    />
                  </label>
                )}
                {missing && <span className="studio-err-text">{t('studio_issue_missing_answer')}</span>}
                {has(issues, 'duplicate_number', q.number) && (
                  <span className="studio-err-text">{t('studio_issue_duplicate_number')}</span>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {block.type !== 'gap' && (
        <button type="button" className="btn sm" onClick={() => addQuestion()}>
          <Plus size={14} aria-hidden="true" /> {t('studio_add_question')}
        </button>
      )}
    </section>
  );
}
