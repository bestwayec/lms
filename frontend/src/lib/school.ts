/**
 * School domain helpers (Teacher / Groups / Parent / Imports).
 *
 * The typed `School` client in lib/api.ts covers most of
 * apps/webapi/views_school.py. The helpers below fill the remaining gaps
 * via the generic api<T>() — group detail GET, parent overview for a given
 * user_id (platform admin), plus shared types, CSV sample templates and
 * per-row error normalisation. No other stream files are touched.
 */
import { api } from './api';

export interface GroupMember {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  has_pro?: boolean;
  pro_status_label?: string;
  tests_count?: number;
  essays_count?: number;
}

export interface GroupStudentResult {
  id: number;
  test: string;
  subject: string;
  calculated_at: string;
  grading_status: string;
  score: number | null;
  max_score: number | null;
  percentage: number | null;
}

export interface GroupStudentResults {
  student: { id: number; name: string };
  results: GroupStudentResult[];
}

export interface GroupMembershipHistoryItem {
  id: number;
  student_id: number;
  student_name: string;
  student_email: string;
  action: string;
  action_display: string;
  joined_at: string;
  removed_at: string | null;
  actor_id: number | null;
  actor_name: string;
  reason: string;
  created_at: string;
}

export interface SchoolGroup {
  id: number;
  name: string;
  description: string;
  invite_code?: string;
  invite_token?: string;
  group_code?: string;
  telegram_chat_id?: number | null;
  telegram_chat_title?: string;
  teacher: number;
  teacher_name: string;
  student_count: number;
  students: GroupMember[];
  created_at: string;
}

export type StudentGroup = SchoolGroup;

export interface RecentResult {
  student: string;
  test: string;
  percentage: number;
  is_passed: boolean;
  date: string;
}

export interface TodayLessonItem {
  session_id: number | null;
  group_id: number;
  group_name: string;
  lesson_date: string;
  start_time: string | null;
  end_time: string | null;
  status: 'draft' | 'finalized' | 'not_started';
  title: string;
  student_count: number;
  present_count: number;
  absent_count: number;
  late_count: number;
  excused_count: number;
  unmarked_count: number;
}

export interface HomeworkAssignmentItem {
  id: number;
  title: string;
  description: string;
  group_id: number;
  group_name: string;
  due_date: string;
  is_overdue: boolean;
  type: 'test' | 'essay' | 'custom';
  test_id?: number | null;
  test_title?: string | null;
  essay_topic_id?: number | null;
  essay_topic_title?: string | null;
  submissions_count: number;
  total_students: number;
  created_at: string;
}

export interface ReviewQueueItem {
  id: number;
  student_id: number;
  student_name: string;
  topic_title: string;
  submitted_at: string;
  word_count: number;
  total_score?: number | null;
}

export interface AttendanceTodaySummary {
  total_groups: number;
  today_sessions_count: number;
  finalized_count: number;
  draft_count: number;
  not_started_count: number;
}

export interface TeacherOverview {
  groups: SchoolGroup[];
  student_count: number;
  published_tests: number;
  active_topics: number;
  recent_results: RecentResult[];
  // Stage 3c Teacher Workspace 3.0 fields:
  today_lessons?: TodayLessonItem[];
  assignments?: HomeworkAssignmentItem[];
  upcoming_deadlines?: HomeworkAssignmentItem[];
  review_queue?: ReviewQueueItem[];
  review_queue_count?: number;
  attendance_today_summary?: AttendanceTodaySummary;
  essay_pending?: number;
  essay_graded?: number;
  essay_avg_score?: number;
}

export interface AnalyticsTotals {
  attempts: number;
  passed: number;
}

export interface AnalyticsData {
  labels: string[];
  attempts: number[];
  avg_percentage: number[];
  totals: AnalyticsTotals;
}

export interface ChildResult {
  test: string;
  percentage: number;
  is_passed: boolean;
  date: string;
}

export interface ParentChild {
  id: number;
  name: string;
  email: string;
  relationship: string;
  results: ChildResult[];
}

export interface ParentOverview {
  children: ParentChild[];
}

/** Per-row import error — services return {row, error} objects. */
export interface ImportRowError {
  row: number | string;
  message: string;
}

export interface StudentImportResult {
  created: number;
  skipped: number;
  errors: ImportRowError[];
}

export interface TestImportCourse {
  id: number;
  title: string;
}

export interface TestImportResult {
  success: boolean;
  test_id: number | null;
  questions_created: number;
  errors: ImportRowError[];
}

/** Leaderboard entry from /api/v1/school/essay-leaderboard/. */
export interface EssayBoardEntry {
  rank: number;
  name: string;
  student_id: number;
  best_score: number;
  converted_score: number;
  essay_count: number;
  avg_score: number;
}

export interface EssayBoard {
  podium: EssayBoardEntry[];
  rest: EssayBoardEntry[];
  total_essays: number;
  total_students: number;
}

/** GET /api/v1/school/groups/<id>/ — the typed client only has PATCH/DELETE. */
export function getGroupDetail(id: number | string): Promise<SchoolGroup> {
  return api<SchoolGroup>(`/api/v1/school/groups/${id}/`);
}

/** GET /api/v1/school/groups/<id>/members/<student_id>/results/ — scoped test results for a group student. */
export function getGroupStudentResults(
  groupId: number | string,
  studentId: number | string,
): Promise<GroupStudentResults> {
  return api<GroupStudentResults>(`/api/v1/school/groups/${groupId}/members/${studentId}/results/`);
}

/** GET /api/v1/school/groups/<id>/history/ — group membership change audit history. */
export function getGroupMembershipHistory(
  groupId: number | string,
): Promise<GroupMembershipHistoryItem[]> {
  return api<GroupMembershipHistoryItem[]>(`/api/v1/school/groups/${groupId}/history/`);
}

/** POST /api/v1/school/groups/<id>/broadcast-vedomost/ — sends Leaderboard & PDF Vedomost to linked Telegram group. */
export async function broadcastGroupVedomost(
  groupId: number,
): Promise<{ ok?: boolean; status?: string; message?: string; detail?: string }> {
  try {
    return await api.post(`/api/v1/school/groups/${groupId}/broadcast-vedomost/`);
  } catch (err: unknown) {
    if ((err as { status?: number })?.status === 404) {
      return await api.post(`/v1/school/groups/${groupId}/broadcast-vedomost/`);
    }
    throw err;
  }
}

/**
 * GET /api/v1/school/parent/ — optional user_id lets a platform admin
 * inspect another parent's overview (backend supports ?user_id= for admins).
 */
export function parentOverview(userId?: number | string): Promise<ParentOverview> {
  const qs = userId ? `?user_id=${encodeURIComponent(String(userId))}` : '';
  return api<ParentOverview>(`/api/v1/school/parent/${qs}`);
}

/** Normalise per-row errors: [{row, error}] objects or plain strings. */
export function normaliseRowErrors(input: unknown): ImportRowError[] {
  if (!Array.isArray(input)) return [];
  return input.map((e, i) => {
    if (typeof e === 'object' && e !== null) {
      const r = e as Record<string, unknown>;
      return {
        row: (r.row as number | string) ?? i + 1,
        message: String(r.error ?? r.message ?? JSON.stringify(e)),
      };
    }
    return { row: i + 1, message: String(e) };
  });
}

export function errMessage(e: unknown): string {
  return e instanceof Error ? e.message : 'Failed.';
}

export function num(v: unknown, fallback = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? (n as number) : fallback;
}

/** Trigger a client-side download (used for sample CSV templates). */
export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

/** Mirrors templates/web/csv_import.html downloadTemplate(). */
export const STUDENT_CSV_SAMPLE =
  'email,first_name,last_name,phone\n' +
  'ali@example.com,Ali,Valiyev,+998901234567\n' +
  'vali@example.com,Vali,Hasanov,+998907654321\n';

/** Mirrors templates/web/bulk_test_import.html downloadTemplate(). */
export const TEST_CSV_SAMPLE =
  'question,choice_a,choice_b,choice_c,choice_d,correct,points,explanation\n' +
  '"2+2=?",A.3,B.4,C.5,D.6,B,1,"Oddiy qo\'shish"\n' +
  '"3+5=?",A.6,B.7,C.8,D.9,C,1,""\n' +
  '"Poytaxt Toshkentmi?",A.Ha,B.Yo\'q,,,A,1,""\n';

/** Client-side mirror of the backend _csv_guard (5 MB, .csv). */
export function guardCsv(file: File | null): string | null {
  if (!file) return 'CSV faylni tanlang.';
  if (!file.name.toLowerCase().endsWith('.csv')) return 'Faqat CSV fayllar qabul qilinadi.';
  if (file.size > 5 * 1024 * 1024) return 'CSV fayl hajmi 5 MB dan oshmasligi kerak.';
  return null;
}

export interface StudentHomeworkItem {
  id: number;
  title: string;
  description: string;
  content_type: 'test' | 'essay' | 'vocabulary' | 'lesson' | 'custom';
  group_id: number | null;
  group_name: string;
  teacher_name: string;
  due_date: string;
  time_limit: number;
  max_attempts: number;
  status:
    | 'not_started'
    | 'in_progress'
    | 'submitted'
    | 'awaiting_review'
    | 'graded'
    | 'overdue'
    | 'cancelled'
    | 'grading_failed';
  status_label: string;
  is_completed: boolean;
  /** Server decides: current recipient, window open, attempts left. */
  can_start?: boolean;
  is_current_recipient?: boolean;
  is_late?: boolean;
  attempts_used?: number;
  deadline_at?: string | null;
  attempt_id?: number | null;
  score: number | null;
  max_score: number | null;
  percentage: number | null;
  score_display: string;
  action_url: string;
  action_id: number | null;
  submission_id: number | null;
  created_at: string;
}

export interface HomeworkCatalogResponse {
  tests: {
    id: number;
    title: string;
    subject: string;
    time_limit: number;
    questions_count: number;
    is_official: boolean;
  }[];
  essays: {
    id: number;
    title: string;
    task_type: string;
    min_words: number;
    max_words: number;
  }[];
  vocabulary: {
    id: number;
    title: string;
    words_count: number;
  }[];
  lessons: {
    id: number;
    title: string;
    course_title: string;
  }[];
}

export const HomeworkAPI = {
  getStudentHomeworks: (status?: string) => {
    const qs = status ? `?status=${encodeURIComponent(status)}` : '';
    return api<{ results: StudentHomeworkItem[]; count: number }>(`/api/v1/school/student/homeworks/${qs}`);
  },
  getStudentHomeworkDetail: (id: number) =>
    api<StudentHomeworkItem>(`/api/v1/school/student/homeworks/${id}/`),
  startStudentHomework: (id: number) =>
    api<{
      ok: boolean;
      homework_id: number;
      submission_id: number;
      status: string;
      attempt_id?: number | null;
      started_at: string;
      time_limit: number;
    }>(`/api/v1/school/student/homeworks/${id}/start/`, {
      method: 'POST',
    }),
  saveStudentHomework: (id: number, answers: unknown) =>
    api<{ ok: boolean; saved_at: string }>(`/api/v1/school/student/homeworks/${id}/save/`, {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),
  submitStudentHomework: (id: number, answers?: unknown) =>
    api<{
      ok: boolean;
      status: string;
      is_completed: boolean;
      score: number | null;
      percentage: number | null;
      score_display: string;
      completed_at: string;
    }>(`/api/v1/school/student/homeworks/${id}/submit/`, {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),
  getStudentHomeworkResult: (id: number) =>
    api<{
      homework_id: number;
      title: string;
      status: string;
      status_label: string;
      score: number | null;
      max_score: number | null;
      percentage: number | null;
      score_display: string;
      feedback: string;
      completed_at: string;
    }>(`/api/v1/school/student/homeworks/${id}/result/`),
  getTeacherCatalog: (contentType?: string) => {
    const qs = contentType ? `?content_type=${encodeURIComponent(contentType)}` : '';
    return api<HomeworkCatalogResponse>(`/api/v1/school/teacher/homework-catalog/${qs}`);
  },
};
