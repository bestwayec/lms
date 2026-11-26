/**
 * Teacher Studio client: types + calls for /api/v1/teacher/studio/*
 * (apps/tests/views_studio.py). Block shapes mirror apps/tests/studio_service.py.
 */
import { api } from './api';

export type BlockType = 'mcq' | 'tfng' | 'matching' | 'gap' | 'short';
export type SectionCode = 'GENERAL' | 'READING' | 'LISTENING';

export const BLOCK_TYPES: BlockType[] = ['mcq', 'tfng', 'matching', 'gap', 'short'];
export const SECTION_CODES: SectionCode[] = ['GENERAL', 'READING', 'LISTENING'];
export const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
export const TF_LABELS = ['TRUE', 'FALSE', 'NOT GIVEN'];
export const YN_LABELS = ['YES', 'NO', 'NOT GIVEN'];
export const STUDIO_SUBJECTS = ['uzbek', 'english', 'biology', 'chemistry', 'law'] as const;

export interface StudioQuestion {
  number: number;
  text: string;
  options: string[];
  answer: string;
  points?: number;
  explanation?: string;
  /** Import preview only (PPTX): the slide the question starts on. */
  slide?: number;
}

/** Ona tili & Adabiyot topics — codes match apps.tests.studio_service.TOPICS_BY_SUBJECT. */
export const TOPICS_BY_SUBJECT: Record<string, readonly string[]> = {
  uzbek: [
    'fonetika',
    'leksikologiya',
    'morfologiya',
    'sintaksis',
    'imlo',
    'punktuatsiya',
    'uslubiyat',
    'matn_tahlili',
    'adabiyot',
    'milliy_sertifikat',
    'aralash',
  ],
};

export interface StudioBlock {
  /** Client-only key for React lists; ignored by the API. */
  key?: string;
  type: BlockType;
  section: SectionCode;
  title: string;
  /** Ona tili topic code (fonetika, imlo, …); '' when untagged. */
  topic?: string;
  instructions: string;
  passage: string;
  gap_text: string;
  options: string[];
  questions: StudioQuestion[];
  audio_path?: string;
  audio_url?: string;
  image_path?: string;
  image_url?: string;
}

export interface StudioIssue {
  block: number;
  number: number | null;
  option: number | null;
  code: string;
}

export type AssessmentCategory = 'topic_test' | 'attestation' | 'full_mock' | 'national_cert' | 'classroom_quiz';
export const ASSESSMENT_CATEGORIES: AssessmentCategory[] = [
  'classroom_quiz',
  'topic_test',
  'attestation',
  'full_mock',
  'national_cert',
];

export interface StudioTestSummary {
  id: number;
  title: string;
  subject: string;
  assessment_category?: AssessmentCategory;
  status: 'draft' | 'published' | 'archived';
  time_limit_minutes: number;
  is_timed?: boolean;
  available_from?: string | null;
  available_until?: string | null;
  mock_code: string;
  access_pin: string;
  description: string;
  /** Who may take it: own groups (default), groups + PRO/Premium, or everyone. */
  audience?: StudioAudience;
  editable: boolean;
  is_studio: boolean;
  updated_at: string | null;
}

export interface StudioAssignment {
  id: number;
  group_id: number;
  group_name: string;
  student_count: number;
  due_at: string;
}

export interface StudioLinks {
  join_code: string;
  access_pin: string;
  tma_link: string;
  web_path: string;
}

export interface StudioDetail {
  test: StudioTestSummary;
  blocks: StudioBlock[];
  issues: StudioIssue[];
  assignments: StudioAssignment[];
  links: StudioLinks;
}

export interface StudioListItem {
  id: number;
  title: string;
  subject: string;
  assessment_category?: AssessmentCategory;
  is_timed?: boolean;
  time_limit_minutes?: number;
  status: StudioTestSummary['status'];
  mock_code: string;
  questions: number;
  attempts: number;
  is_studio: boolean;
  updated_at: string | null;
}

export interface ParseResult {
  blocks: StudioBlock[];
  answer_key: Record<string, string>;
  warnings: { code: string; number?: number; line?: number }[];
}

export interface ItemStat {
  question_id: number;
  number: number;
  text: string;
  question_type: string;
  correct: number;
  answered: number;
  total: number;
  accuracy: number | null;
  flagged: boolean;
}

export interface ItemAnalysis {
  test_id: number;
  title: string;
  students: number;
  total_assigned?: number;
  submitted_count?: number;
  unsubmitted_count?: number;
  pending_review_count?: number;
  flag_threshold: number;
  average: number | null;
  median: number | null;
  distribution: { from: number; to: number; count: number }[];
  items: ItemStat[];
  /** Per-topic accuracy from real answers, weakest first (tagged questions only). */
  topics?: { topic: string; questions: number; correct: number; possible: number; accuracy: number | null }[];
  matrix: {
    attempt_id: number;
    student: string;
    percentage: number | null;
    is_pending?: boolean;
    status?: string;
    cells: (boolean | null)[];
  }[];
  assignments: StudioAssignment[];
}

export interface FileImportResult {
  blocks: StudioBlock[];
  questions_count: number;
  detected_answers: number;
  warnings: { row?: number; code: string; question?: number; number?: number; slide?: number }[];
  source?: {
    kind: 'text' | 'csv' | 'xlsx' | 'docx' | 'pdf' | 'pptx';
    filename: string;
    /** PPTX: question number → slide it starts on. */
    question_slides?: Record<string, number>;
  };
  report?: {
    total_questions: number;
    valid_questions: number;
    missing_answers: number;
    duplicate_options: number;
    too_few_options: number;
    duplicate_numbers: number[];
    warnings_count: number;
  };
}

export type StudioAudience = 'GROUP_ONLY' | 'GROUP_AND_SUBSCRIBERS' | 'PUBLIC_FREE';
export const STUDIO_AUDIENCES: StudioAudience[] = ['GROUP_ONLY', 'GROUP_AND_SUBSCRIBERS', 'PUBLIC_FREE'];

export interface TestPayload {
  title: string;
  subject: string;
  assessment_category?: AssessmentCategory;
  time_limit_minutes: number;
  is_timed?: boolean;
  available_from?: string | null;
  available_until?: string | null;
  description?: string;
  audience?: StudioAudience;
  blocks: StudioBlock[];
}

const BASE = '/api/v1/teacher/studio';

/** Drop client-only fields before sending. */
function clean(blocks: StudioBlock[]): StudioBlock[] {
  return blocks.map(({ key: _k, audio_url: _a, image_url: _i, ...rest }) => rest as StudioBlock);
}

export const StudioApi = {
  list: (params?: { q?: string; status?: string; subject?: string; category?: string; assessment_category?: string }) => {
    const sp = new URLSearchParams();
    if (params?.q) sp.set('q', params.q);
    if (params?.status && params.status !== 'all') sp.set('status', params.status);
    if (params?.subject && params.subject !== 'all') sp.set('subject', params.subject);
    const cat = params?.category ?? params?.assessment_category;
    if (cat && cat !== 'all') sp.set('category', cat);
    const qs = sp.toString();
    return api.get<StudioListItem[]>(`${BASE}/tests/${qs ? `?${qs}` : ''}`);
  },
  detail: (id: number | string) => api.get<StudioDetail>(`${BASE}/tests/${id}/`),
  duplicate: (id: number | string) => api.post<StudioDetail>(`${BASE}/tests/${id}/duplicate/`),
  delete: (id: number | string) => api<{ deleted: boolean }>(`${BASE}/tests/${id}/`, { method: 'DELETE' }),
  parse: (text: string, section: SectionCode = 'GENERAL') =>
    api.post<ParseResult>(`${BASE}/parse/`, { text, section }),
  importFile: (file: File, section: SectionCode = 'GENERAL') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('section', section);
    return api.post<FileImportResult>(`${BASE}/import-file/`, fd);
  },
  exportUrl: (id: number | string) => `${BASE}/tests/${id}/export/`,
  validatePackage: (payload: unknown, template = false) =>
    api.post<{ valid: boolean; errors: unknown[]; warnings: unknown[]; summary: Record<string, unknown> }>(
      `${BASE}/package/validate/${template ? '?template=1' : ''}`,
      payload,
    ),
  importPackage: (payload: unknown, template = false) =>
    api.post<StudioDetail>(`${BASE}/package/import/${template ? '?template=1' : ''}`, payload),
  exportPackage: (id: number | string, template = false) =>
    api.get<Record<string, unknown>>(`${BASE}/tests/${id}/package/${template ? '?template=1' : ''}`),
  checkReadiness: (id: number | string) =>
    api.get<{ ready: boolean; issues: StudioIssue[] }>(`${BASE}/tests/${id}/readiness/`),
  validate: (blocks: StudioBlock[]) =>
    api.post<{ issues: StudioIssue[] }>(`${BASE}/validate/`, { blocks: clean(blocks) }),
  create: (payload: TestPayload) =>
    api.post<StudioDetail>(`${BASE}/tests/`, { ...payload, blocks: clean(payload.blocks) }),
  update: (id: number | string, payload: TestPayload) =>
    api<StudioDetail>(`${BASE}/tests/${id}/`, {
      method: 'PUT',
      body: JSON.stringify({ ...payload, blocks: clean(payload.blocks) }),
    }),
  publish: (id: number | string) => api.post<StudioDetail>(`${BASE}/tests/${id}/publish/`),
  assign: (
    id: number | string,
    dataOrGroupId:
      | number
      | {
          group_id?: number | null;
          student_id?: number | null;
          due_at: string;
          time_limit_minutes?: number;
          max_attempts?: number;
          idempotency_key?: string;
        },
    dueAt?: string,
  ) => {
    const payload =
      typeof dataOrGroupId === 'number'
        ? { group_id: dataOrGroupId, due_at: dueAt ?? '' }
        : dataOrGroupId;
    return api.post<StudioLinks & { assignment: StudioAssignment }>(`${BASE}/tests/${id}/assign/`, payload);
  },
  analysis: (id: number | string, groupId?: number | null) =>
    api.get<ItemAnalysis>(`${BASE}/tests/${id}/analysis/${groupId ? `?group=${groupId}` : ''}`),
  uploadMedia: (file: File, kind: 'audio' | 'image') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('kind', kind);
    return api.post<{ path: string; url: string }>(`${BASE}/media/`, fd);
  },
};

/* ------------------------------------------------------------- helpers */

let keySeq = 0;
export const newKey = () => `b${Date.now().toString(36)}${(keySeq++).toString(36)}`;

export const withKeys = (blocks: StudioBlock[]): StudioBlock[] =>
  blocks.map((b) => ({ ...b, key: b.key || newKey() }));

export const GAP_RE = /\[(\d{1,3})(?:\s*:\s*([^\]]*))?\]/g;

/** One question per [n:answer] marker, in text order. */
export function gapQuestions(gapText: string): StudioQuestion[] {
  const out: StudioQuestion[] = [];
  for (const m of gapText.matchAll(GAP_RE)) {
    out.push({ number: Number(m[1]), text: '', options: [], answer: m[2] ?? '' });
  }
  return out;
}

/** Rewrite the answer of gap `n` inside the gap text (answer key matrix edits). */
export function setGapAnswer(gapText: string, n: number, answer: string): string {
  // Not trimmed while typing (multi-word answers); the server trims on save.
  const safe = answer.replace(/[[\]\n]/g, '');
  return gapText.replace(GAP_RE, (whole, num: string) =>
    Number(num) === n ? (safe.trim() ? `[${num}:${safe}]` : `[${num}]`) : whole,
  );
}

/**
 * What the exam screen shows for gap `n` (mirrors studio_parser.gap_sentence):
 * the line holding it, split into [before, after] around its input; other gaps
 * in that line appear as "(m) …".
 */
export function gapSentence(gapText: string, n: number): [string, string] {
  for (const line of gapText.split('\n')) {
    const nums = [...line.matchAll(GAP_RE)].map((m) => Number(m[1]));
    if (!nums.includes(n)) continue;
    const pieces = line.length > 200 ? line.trim().split(/(?<=[.!?])\s+/) : [line.trim()];
    const piece = pieces.find((p) => [...p.matchAll(GAP_RE)].some((m) => Number(m[1]) === n)) ?? line;
    const marker = '\u0000';
    const text = piece.replace(GAP_RE, (_w, num: string) => (Number(num) === n ? marker : `(${num}) …`));
    const [before, after = ''] = text.split(marker);
    return [before, after];
  }
  return ['', ''];
}

/** Gap-text lines without gaps (headings, labels): shown as the text. */
export function gapContext(gapText: string): string {
  return gapText
    .split('\n')
    .filter((line) => line.trim() && !new RegExp(GAP_RE.source).test(line))
    .join('\n')
    .trim();
}

export function nextNumber(blocks: StudioBlock[]): number {
  let max = 0;
  for (const b of blocks) for (const q of b.questions) max = Math.max(max, q.number);
  return max + 1;
}

export function emptyBlock(type: BlockType, start: number, section: SectionCode = 'GENERAL'): StudioBlock {
  const q = (n: number): StudioQuestion => ({
    number: n,
    text: '',
    options: type === 'mcq' ? ['', '', ''] : [],
    answer: '',
  });
  return {
    key: newKey(),
    type,
    section,
    title: '',
    instructions: '',
    passage: '',
    gap_text: type === 'gap' ? `[${start}:]` : '',
    options: type === 'matching' ? ['', '', ''] : type === 'tfng' ? [...TF_LABELS] : [],
    questions: type === 'gap' ? [{ number: start, text: '', options: [], answer: '' }] : [q(start)],
  };
}

/** A blank multiple-choice block of ``count`` questions (4 empty options each) —
 *  the "10/20/30/40 savollik test" starter. Publish validation flags anything
 *  left empty, so nothing incomplete can be published. */
export function blankMcqBlock(count: number, start: number, section: SectionCode = 'GENERAL'): StudioBlock {
  const b = emptyBlock('mcq', start, section);
  b.questions = Array.from({ length: count }, (_, i) => ({
    number: start + i,
    text: '',
    options: ['', '', '', ''],
    answer: '',
  }));
  return b;
}

/** Change a block's type keeping what still fits. */
export function convertBlock(b: StudioBlock, type: BlockType): StudioBlock {
  if (b.type === type) return b;
  if (type === 'gap') {
    const text = b.questions.map((q) => `${q.text} [${q.number}:${q.answer}]`).join('\n');
    return { ...b, type, gap_text: text, options: [], questions: gapQuestions(text) };
  }
  const questions = (b.type === 'gap' ? gapQuestions(b.gap_text) : b.questions).map((q) => ({
    ...q,
    options: type === 'mcq' ? (q.options.length ? q.options : ['', '', '']) : [],
    answer: type === 'short' ? q.answer : '',
  }));
  return {
    ...b,
    type,
    gap_text: '',
    options: type === 'tfng' ? [...TF_LABELS] : type === 'matching' ? (b.options.length ? b.options : ['', '', '']) : [],
    questions,
  };
}

/** Questions as the student sees them, in number order (gap blocks derived). */
export function blockQuestions(b: StudioBlock): StudioQuestion[] {
  return b.type === 'gap' ? gapQuestions(b.gap_text) : b.questions;
}

export function answerChoices(b: StudioBlock, q: StudioQuestion): string[] | null {
  if (b.type === 'mcq') return q.options.map((_, i) => LETTERS[i]);
  if (b.type === 'matching') return b.options.map((_, i) => LETTERS[i]);
  if (b.type === 'tfng') return b.options.length ? b.options : TF_LABELS;
  return null;
}
