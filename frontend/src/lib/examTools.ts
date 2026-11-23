/**
 * Which helper tools an exam may show. One rule for the whole runner:
 * a tool appears only when the subject's examination policy allows it, so an
 * Ona tili or IELTS exam never shows chemistry tables or a calculator.
 */
export interface ExamToolPolicy {
  periodicTable: boolean;
  solubilityTable: boolean;
  calculator: boolean;
}

const NONE: ExamToolPolicy = { periodicTable: false, solubilityTable: false, calculator: false };

const BY_SUBJECT: Record<string, ExamToolPolicy> = {
  chemistry: { periodicTable: true, solubilityTable: true, calculator: true },
  physics: { periodicTable: false, solubilityTable: false, calculator: true },
  mathematics: { periodicTable: false, solubilityTable: false, calculator: true },
};

export function examToolPolicy(subject: string | null | undefined, examType?: string | null): ExamToolPolicy {
  // Official language exams never get extra tools, whatever the subject field says.
  if (examType && /ielts|cefr|national_cert/.test(examType)) return NONE;
  return BY_SUBJECT[(subject || '').toLowerCase()] ?? NONE;
}

export function hasAnyExamTool(policy: ExamToolPolicy): boolean {
  return policy.periodicTable || policy.solubilityTable || policy.calculator;
}
