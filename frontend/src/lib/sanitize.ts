/**
 * Frontend XSS Sanitization & HTML Escaping Utilities (GRANDEC Security Hardening).
 *
 * Prevents Stored and Reflected DOM XSS whenever user-supplied or API-returned
 * strings are rendered into HTML/SVG containers.
 */

const SCRIPT_BLOCK_RE = /<\s*script\b[^>]*>[\s\S]*?<\s*\/\s*script\s*>/gi;
const DANGEROUS_TAG_RE =
  /<\s*\/?\s*(?:script|iframe|object|embed|applet|meta|link|style|form|base|foreignobject)\b[^>]*>/gi;
const EVENT_HANDLER_ATTR_RE = /\bon[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi;
const JS_URI_RE = /(?:javascript|vbscript|data\s*:\s*text\/html)\s*:/gi;

/**
 * Escapes HTML special characters so untrusted plain text can be safely
 * interpolated before adding trusted `<mark>` highlights.
 */
export function escapeHtml(raw: string | null | undefined): string {
  if (!raw) return '';
  return String(raw)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Strips executable XSS vectors (`<script>`, `<iframe>`, `on*=`, `javascript:`)
 * from HTML strings while preserving safe formatting tags like `<mark>`, `<b>`, `<span>`.
 */
export function sanitizeHtml(dirty: string | null | undefined): string {
  if (!dirty) return '';
  return String(dirty)
    .replace(SCRIPT_BLOCK_RE, '')
    .replace(DANGEROUS_TAG_RE, '')
    .replace(EVENT_HANDLER_ATTR_RE, '')
    .replace(JS_URI_RE, '');
}

/**
 * Sanitizes SVG markup before rendering via `dangerouslySetInnerHTML`.
 */
export function sanitizeSvg(svg: string | null | undefined): string {
  if (!svg) return '';
  return sanitizeHtml(svg);
}
