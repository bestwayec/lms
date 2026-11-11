/**
 * Radar / spider-chart label helpers (pure, unit-tested in tests/radarLabel.test.ts).
 *
 * Long axis names such as "Masalalar (36-45)" or "Davlat nazariyasi" used to
 * overflow the SVG viewBox on 360–420px phones and overlap the spokes. We wrap
 * them into at most two balanced lines at a word boundary.
 */
export function splitRadarLabel(name: string, maxLine = 12): string[] {
  const clean = (name || '').trim().replace(/\s+/g, ' ');
  if (clean.length <= maxLine || !clean.includes(' ')) return [clean];
  const words = clean.split(' ');
  let best: [string, string] = [clean, ''];
  let bestScore = Number.POSITIVE_INFINITY;
  for (let i = 1; i < words.length; i += 1) {
    const a = words.slice(0, i).join(' ');
    const b = words.slice(i).join(' ');
    const score = Math.max(a.length, b.length);
    if (score < bestScore) {
      bestScore = score;
      best = [a, b];
    }
  }
  return best[1] ? best : [clean];
}
