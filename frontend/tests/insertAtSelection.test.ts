import assert from 'node:assert/strict';
import { test } from 'node:test';
import { insertAtSelection } from '../src/lib/insertAtSelection.ts';

test('scientific symbols insert at the caret and replace selections', () => {
  assert.deepEqual(insertAtSelection('H2O', '₂', 1, 2), { value: 'H₂O', caret: 2 });
  assert.deepEqual(insertAtSelection('CO', '₂', 1, 1), { value: 'C₂O', caret: 2 });
  assert.deepEqual(insertAtSelection('25', '°C', null, null), { value: '25°C', caret: 4 });
});
