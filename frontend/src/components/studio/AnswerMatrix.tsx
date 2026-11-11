import { useState } from 'react';
import { useLang } from '../../i18n/LangContext';
import {
  LETTERS,
  StudioApi,
  answerChoices,
  blockQuestions,
  setGapAnswer,
  type StudioBlock,
  type StudioIssue,
} from '../../lib/studio';

function normalizeFor(b: StudioBlock, optionCount: number, raw: string): string {
  const v = raw.trim();
  if (b.type === 'mcq' || b.type === 'matching') {
    const letter = v.replace(/[.)]/g, '').toUpperCase();
    return letter.length === 1 && LETTERS.slice(0, optionCount).includes(letter) ? letter : '';
  }
  if (b.type === 'tfng') {
    const u = v.toUpperCase().replace(/[\s_.-]+/g, ' ').trim();
    const labels = b.options.length ? b.options : ['TRUE', 'FALSE', 'NOT GIVEN'];
    if (['T', 'TRUE', 'Y', 'YES'].includes(u)) return labels[0];
    if (['F', 'FALSE', 'N', 'NO'].includes(u)) return labels[1];
    if (['NG', 'NOT GIVEN'].includes(u)) return labels[2];
    return '';
  }
  return v;
}

/** Apply `{number: answer}` to every matching question across blocks. */
function applyKey(blocks: StudioBlock[], key: Record<string, string>): StudioBlock[] {
  return blocks.map((b) => {
    if (b.type === 'gap') {
      let text = b.gap_text;
      for (const q of blockQuestions(b)) {
        const raw = key[String(q.number)];
        if (raw !== undefined) text = setGapAnswer(text, q.number, raw);
      }
      return text === b.gap_text ? b : { ...b, gap_text: text, questions: blockQuestions({ ...b, gap_text: text }) };
    }
    return {
      ...b,
      questions: b.questions.map((q) => {
        const raw = key[String(q.number)];
        if (raw === undefined) return q;
        const count = b.type === 'mcq' ? q.options.length : b.options.length;
        return { ...q, answer: normalizeFor(b, count, raw) || q.answer };
      }),
    };
  });
}

interface Props {
  blocks: StudioBlock[];
  issues: StudioIssue[];
  onChange: (blocks: StudioBlock[]) => void;
}

/** Every question's key in one grid, plus "1: A, 2: bees" bulk paste. */
export default function AnswerMatrix({ blocks, issues, onChange }: Props) {
  const { t } = useLang();
  const [bulk, setBulk] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const setAnswer = (bi: number, number: number, value: string) => {
    onChange(
      blocks.map((b, i) => {
        if (i !== bi) return b;
        if (b.type === 'gap') {
          const text = setGapAnswer(b.gap_text, number, value);
          return { ...b, gap_text: text, questions: blockQuestions({ ...b, gap_text: text }) };
        }
        return { ...b, questions: b.questions.map((q) => (q.number === number ? { ...q, answer: value } : q)) };
      }),
    );
  };

  const applyBulk = async () => {
    if (!bulk.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      // The server parser owns the key syntax ("1: A, 2: bees", "1-A", one per line…).
      const res = await StudioApi.parse(`Answers:\n${bulk}`);
      const n = Object.keys(res.answer_key).length;
      if (!n) {
        setNote(t('studio_key_none'));
        return;
      }
      onChange(applyKey(blocks, res.answer_key));
      setNote(t('studio_key_applied').replace('{n}', String(n)));
      setBulk('');
    } catch (e) {
      setNote(e instanceof Error ? e.message : t('err_retry_js'));
    } finally {
      setBusy(false);
    }
  };

  const rows = blocks.flatMap((b, bi) => blockQuestions(b).map((q) => ({ b, bi, q })));

  return (
    <div className="studio-matrix">
      <div className="studio-field">
        <label htmlFor="studio-bulk-key">
          <span>{t('studio_key_bulk')}</span>
        </label>
        <textarea
          id="studio-bulk-key"
          rows={3}
          className="studio-mono"
          value={bulk}
          placeholder={t('studio_key_ph')}
          onChange={(e) => setBulk(e.target.value)}
        />
        <div className="studio-row">
          <button type="button" className="btn sm primary" onClick={() => void applyBulk()} disabled={busy || !bulk.trim()}>
            {t('studio_key_apply')}
          </button>
          {note && <span className="muted small" role="status">{note}</span>}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="muted">{t('studio_key_empty')}</p>
      ) : (
        <div className="studio-matrix__grid" role="table" aria-label={t('studio_tab_key')}>
          {rows.map(({ b, bi, q }) => {
            const choices = answerChoices(b, q);
            const missing = issues.some((i) => i.code === 'missing_answer' && i.number === q.number);
            return (
              <div key={`${bi}-${q.number}`} className={`studio-matrix__cell${missing ? ' is-invalid' : ''}`} role="row">
                <span className="studio-matrix__num" role="rowheader">
                  {q.number}
                </span>
                {choices ? (
                  <div className="studio-matrix__choices" role="radiogroup" aria-label={`${t('studio_correct')} ${q.number}`}>
                    {choices.map((c) => (
                      <button
                        key={c}
                        type="button"
                        role="radio"
                        aria-checked={q.answer === c}
                        className={q.answer === c ? 'is-on' : ''}
                        onClick={() => setAnswer(bi, q.number, c)}
                        title={c}
                      >
                        {b.type === 'tfng' ? c.split(' ').map((w) => w[0]).join('') : c}
                      </button>
                    ))}
                  </div>
                ) : (
                  <input
                    aria-label={`${t('studio_correct')} ${q.number}`}
                    value={q.answer}
                    placeholder={t('studio_short_ph')}
                    onChange={(e) => setAnswer(bi, q.number, e.target.value)}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
