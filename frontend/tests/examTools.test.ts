import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { examToolPolicy, hasAnyExamTool } from '../src/lib/examTools.ts';

describe('exam tool policy (owner screenshots: chemistry tools in an Ona tili exam)', () => {
  it('Ona tili / Adabiyot exams show no chemistry tools and no calculator', () => {
    assert.equal(hasAnyExamTool(examToolPolicy('uzbek', 'general')), false);
    assert.equal(hasAnyExamTool(examToolPolicy('uzbek', 'national_cert')), false);
  });
  it('IELTS / CEFR / English show none', () => {
    for (const [s, e] of [['english', 'ielts_academic'], ['english', 'cefr_multilevel'], ['english', 'general']]) {
      assert.equal(hasAnyExamTool(examToolPolicy(s, e)), false);
    }
  });
  it('chemistry gets periodic table, solubility table and calculator', () => {
    assert.deepEqual(examToolPolicy('chemistry', 'general'), { periodicTable: true, solubilityTable: true, calculator: true });
  });
  it('unknown or missing subject is safe (no tools)', () => {
    assert.equal(hasAnyExamTool(examToolPolicy(undefined)), false);
    assert.equal(hasAnyExamTool(examToolPolicy('law')), false);
    assert.equal(hasAnyExamTool(examToolPolicy('biology')), false);
  });
});
