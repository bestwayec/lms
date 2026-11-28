import { useLang } from '../../i18n/LangContext';

export interface IeltsSectionScore {
  code: string;
  name: string;
  status: 'scored' | 'pending' | 'missing';
  earned: number;
  maximum: number;
  band: number | null;
}

export interface IeltsSummary {
  correct: number;
  total: number;
  band: number | null;
  grading_status?: string;
  sections?: Record<string, IeltsSectionScore>;
}

/**
 * IELTS result: raw score, per-section breakdown when present, and an estimated band.
 * Always labelled as an estimate; holds overall band hidden until Writing/Speaking are graded.
 */
export default function IeltsResultSummary({ data, showEstimateNotice = false }: { data: IeltsSummary; showEstimateNotice?: boolean }) {
  const { t } = useLang();
  const sectionRows = data.sections ? Object.values(data.sections) : [];
  return (
    <div className="card cefr-result">
      {showEstimateNotice && <p className="cefr-result-note">{t('ielts_result_estimate_note')}</p>}
      <p className="cefr-result-overall">
        <span className="muted">{t('ielts_result_raw')}</span>
        <strong>
          {data.correct} / {data.total}
        </strong>
      </p>
      {sectionRows.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="data">
            <thead>
              <tr>
                <th>{t('cefr_result_section')}</th>
                <th>{t('ielts_result_raw')}</th>
                <th>{t('ielts_result_band')}</th>
              </tr>
            </thead>
            <tbody>
              {sectionRows.map((s) => (
                <tr key={s.code}>
                  <td>{s.name}</td>
                  <td>{s.earned} / {s.maximum}</td>
                  <td>{s.status === 'scored' && s.band != null ? s.band.toFixed(1) : t('cefr_result_pending')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.band != null ? (
        <p className="cefr-result-overall">
          <span className="muted">{t('ielts_result_band')}</span>
          <strong>{data.band.toFixed(1)}</strong>
        </p>
      ) : data.grading_status === 'pending_grading' ? (
        <p className="cefr-result-overall muted">{t('cefr_result_pending')}</p>
      ) : null}
    </div>
  );
}
