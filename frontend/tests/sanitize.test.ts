import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { escapeHtml, sanitizeHtml, sanitizeSvg } from '../src/lib/sanitize.ts';

describe('Frontend XSS Sanitization (GRANDEC Security Hardening)', () => {
  it('escapes HTML special characters while preserving Uzbek apostrophes and text', () => {
    const raw = `<script>alert("xss")</script> O'tkirbek & G'ulomov`;
    const escaped = escapeHtml(raw);
    assert.equal(escaped.includes('<script>'), false);
    assert.equal(escaped.includes('&lt;script&gt;'), true);
    assert.equal(escaped.includes('O&#39;tkirbek &amp; G&#39;ulomov'), true);
  });

  it('strips executable script tags, iframes, event handlers, and javascript: URIs', () => {
    const dirty =
      '<mark class="essay-strong-highlight">Good point</mark>' +
      '<script>fetch("https://evil.test")</script>' +
      '<iframe src="javascript:alert(1)"></iframe>' +
      '<span onmouseover="alert(1)" onclick=\'steal()\'>Safe text</span>';
    const clean = sanitizeHtml(dirty);
    assert.equal(clean.includes('<mark class="essay-strong-highlight">Good point</mark>'), true);
    assert.equal(clean.includes('<script'), false);
    assert.equal(clean.includes('<iframe'), false);
    assert.equal(clean.includes('onmouseover'), false);
    assert.equal(clean.includes('onclick'), false);
    assert.equal(clean.includes('javascript:'), false);
    assert.equal(clean.includes('Safe text'), true);
  });

  it('sanitizes SVG content before rendering in QR modal', () => {
    const svg = '<svg viewBox="0 0 100 100" onload="alert(1)"><path d="M0 0"/><script>evil()</script></svg>';
    const clean = sanitizeSvg(svg);
    assert.equal(clean.includes('<svg'), true);
    assert.equal(clean.includes('<path d="M0 0"/>'), true);
    assert.equal(clean.includes('onload'), false);
    assert.equal(clean.includes('<script'), false);
  });
});
