/** Insert a symbol at the caret, replacing any selected text. */
export function insertAtSelection(value: string, symbol: string, start: number | null, end: number | null) {
  const from = Math.max(0, Math.min(start ?? value.length, value.length));
  const to = Math.max(from, Math.min(end ?? from, value.length));
  return { value: value.slice(0, from) + symbol + value.slice(to), caret: from + symbol.length };
}
