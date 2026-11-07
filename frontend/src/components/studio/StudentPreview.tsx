import { useState } from 'react';
import { Monitor, Smartphone } from 'lucide-react';
import { useLang } from '../../i18n/LangContext';
import { LETTERS, gapContext, gapQuestions, gapSentence, type StudioBlock } from '../../lib/studio';

/**
 * Live student view of the blocks being edited. Uses the CD exam screen's own
 * classes (styles/exam.css) so it looks like the real test; answers typed here
 * are local and never saved. Keys are never shown.
 */
export default function StudentPreview({ title, blocks }: { title: string; blocks: StudioBlock[] }) {
  const { t } = useLang();
  const [device, setDevice] = useState<'desktop' | 'mobile'>('desktop');
  const [picked, setPicked] = useState<Record<string, string>>({});
  const pick = (k: string, v: string) => setPicked((p) => ({ ...p, [k]: v }));

  return (
    <div className="studio-preview">
      <div className="studio-preview__bar">
        <strong>{t('studio_preview')}</strong>
        <div className="studio-seg" role="group" aria-label={t('studio_preview_device')}>
          <button
            type="button"
            className={device === 'desktop' ? 'is-on' : ''}
            aria-pressed={device === 'desktop'}
            onClick={() => setDevice('desktop')}
          >
            <Monitor size={15} aria-hidden="true" /> {t('studio_desktop')}
          </button>
          <button
            type="button"
            className={device === 'mobile' ? 'is-on' : ''}
            aria-pressed={device === 'mobile'}
            onClick={() => setDevice('mobile')}
          >
            <Smartphone size={15} aria-hidden="true" /> {t('studio_mobile')}
          </button>
        </div>
      </div>

      <div className={`studio-preview__frame is-${device}`}>
        <div className="studio-preview__screen">
          <h2 className="studio-preview__title">{title || t('studio_untitled')}</h2>
          {blocks.length === 0 && <p className="muted">{t('studio_preview_empty')}</p>}
          {blocks.map((b, bi) => {
            const passage = [b.passage.trim(), b.type === 'gap' ? gapContext(b.gap_text) : '']
              .filter(Boolean)
              .join('\n\n');
            return (
              <section key={b.key ?? bi} className="cd-part studio-preview__part">
                {b.section !== 'GENERAL' && (
                  <p className="studio-preview__section">{t(`studio_section_${b.section.toLowerCase()}`)}</p>
                )}
                {passage && (
                  <article className="cd-passage studio-preview__passage">
                    {b.title && <h2>{b.title}</h2>}
                    {passage.split(/\n{2,}/).map((para, i) => (
                      <p key={i}>{para}</p>
                    ))}
                  </article>
                )}
                {(b.audio_url || b.audio_path) && (
                  <audio className="studio-preview__audio" controls preload="none" src={b.audio_url || undefined} />
                )}
                <div className="cd-group">
                  {!passage && b.title && <h3>{b.title}</h3>}
                  {b.instructions && <p className="cd-instructions">{b.instructions}</p>}
                  {(b.image_url || b.image_path) && b.image_url && (
                    <img className="cd-image" src={b.image_url} alt={b.title || t('cd_picture')} />
                  )}
                  {b.type === 'matching' && b.options.length > 0 && (
                    <div className="cd-shared-options">
                      <p className="cd-options-label">A–{LETTERS[b.options.length - 1]}</p>
                      <ol>
                        {b.options.map((o, i) => (
                          <li key={i}>
                            <b>{LETTERS[i]}</b> {o || '…'}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                  <div className="cd-questions">
                    {b.type === 'gap' &&
                      gapQuestions(b.gap_text).map((q) => {
                        const k = `${bi}-${q.number}`;
                        const [before, after] = gapSentence(b.gap_text, q.number);
                        return (
                          <div key={q.number} className="cd-question cd-inline">
                            <span className="cd-num">{q.number}</span>
                            <p>
                              {before}
                              <input
                                className="cd-gap"
                                aria-label={`${t('cd_question')} ${q.number}`}
                                value={picked[k] ?? ''}
                                onChange={(e) => pick(k, e.target.value)}
                              />
                              {after}
                            </p>
                          </div>
                        );
                      })}
                    {b.type !== 'gap' &&
                      b.questions.map((q) => {
                        const k = `${bi}-${q.number}`;
                        if (b.type === 'short') {
                          return (
                            <div key={q.number} className="cd-question cd-inline">
                              <span className="cd-num">{q.number}</span>
                              <p>
                                {q.text || '…'}{' '}
                                <input
                                  className="cd-gap"
                                  aria-label={`${t('cd_question')} ${q.number}`}
                                  value={picked[k] ?? ''}
                                  onChange={(e) => pick(k, e.target.value)}
                                />
                              </p>
                            </div>
                          );
                        }
                        if (b.type === 'matching') {
                          return (
                            <div key={q.number} className="cd-question cd-select">
                              <span className="cd-num">{q.number}</span>
                              <label className="cd-select-text" htmlFor={`pv-${k}`}>
                                {q.text || '…'}
                              </label>
                              <select id={`pv-${k}`} value={picked[k] ?? ''} onChange={(e) => pick(k, e.target.value)}>
                                <option value="">{t('cd_choose')}</option>
                                {b.options.map((o, i) => (
                                  <option key={i} value={LETTERS[i]}>
                                    {LETTERS[i]}. {o}
                                  </option>
                                ))}
                              </select>
                            </div>
                          );
                        }
                        const tfng = b.type === 'tfng';
                        const opts = tfng ? b.options : q.options;
                        return (
                          <fieldset key={q.number} className="cd-question cd-choice">
                            <legend>
                              <span className="cd-num">{q.number}</span> {q.text || '…'}
                            </legend>
                            <div className={tfng ? 'cd-options inline' : 'cd-options'}>
                              {opts.map((o, i) => (
                                <label key={i} className={picked[k] === String(i) ? 'cd-option selected' : 'cd-option'}>
                                  <input
                                    type="radio"
                                    name={`pv-${k}`}
                                    checked={picked[k] === String(i)}
                                    onChange={() => pick(k, String(i))}
                                  />
                                  <span>
                                    {!tfng && <b>{LETTERS[i]}</b>} {o || '…'}
                                  </span>
                                </label>
                              ))}
                            </div>
                          </fieldset>
                        );
                      })}
                  </div>
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}
