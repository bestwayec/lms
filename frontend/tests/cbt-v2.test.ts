import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { splitRadarLabel } from '../src/lib/radarLabel.ts';
import { cleanChoiceText, parseSmartTestText } from '../src/lib/testParser.ts';

describe('Dashboard Radar Label Wrapping (v2.0.0 mobile fix)', () => {
  it('keeps short single-word axis labels on one line', () => {
    assert.deepEqual(splitRadarLabel('Organik'), ['Organik']);
    assert.deepEqual(splitRadarLabel('Reading'), ['Reading']);
  });

  it('wraps long multi-word subject axes into two balanced lines so 360px SVG viewBox never clips', () => {
    const chem = splitRadarLabel('Masalalar (36-45)');
    assert.equal(chem.length, 2);
    assert.deepEqual(chem, ['Masalalar', '(36-45)']);

    const law = splitRadarLabel('Davlat nazariyasi');
    assert.equal(law.length, 2);
    assert.deepEqual(law, ['Davlat', 'nazariyasi']);

    const uz = splitRadarLabel('Imlo va uslub');
    assert.equal(uz.length, 2);
    assert.ok(uz[0].length <= 8 && uz[1].length <= 8);
  });
});

describe('Teacher Smart Paste Parser (v2.0.0 builder)', () => {
  it('parses A)/B)/C)/D) choices, *A) marker, and Javob: B line across subjects', () => {
    const raw = `
1. Suvning molyar massasi necha g/mol?
A) 16
*B) 18
C) 20
D) 22

2. NaOH qanday modda?
A) Kislota   B) Ishqor   C) Tuz   D) Oksid
Javob: B
`;
    const res = parseSmartTestText(raw, 'chemistry');
    assert.equal(res.questions.length, 2);
    assert.equal(res.questions[0].correctAnswer, 'B');
    assert.equal(res.questions[0].choices.length, 4);
    assert.equal(res.questions[1].correctAnswer, 'B');
    assert.equal(res.unansweredCount, 0);
  });

  it('strips duplicate option prefixes via cleanChoiceText', () => {
    assert.equal(cleanChoiceText('A) A) Toshkent', 'A'), 'Toshkent');
    assert.equal(cleanChoiceText('(B) Samarqand', 'B'), 'Samarqand');
  });
});
