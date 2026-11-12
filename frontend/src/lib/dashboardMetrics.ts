/** Only objective counts supplied by the subject-scoped API become scores. */
export function measuredParts<T extends { total?: number; correct?: number }>(parts: T[]): Array<T & { percentage: number }> {
  return parts.filter((p) => Number.isFinite(p.total) && p.total! > 0 && Number.isFinite(p.correct) && p.correct! >= 0 && p.correct! <= p.total!)
    .map((p) => ({ ...p, percentage: Math.round(p.correct! / p.total! * 100) }));
}
