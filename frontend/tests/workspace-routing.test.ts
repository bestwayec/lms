import test from 'node:test';
import assert from 'node:assert/strict';
import {
  getAvailableWorkspaces,
  getDefaultWorkspace,
  resolveRouteTitle,
  shouldShowSubjectSwitcher,
} from '../src/lib/routeTitle.ts';

test('resolveRouteTitle assigns distinct titles to /panel, /groups, /tests/create and never falls back to Login', () => {
  const panelTitle = resolveRouteTitle('/panel');
  const groupsTitle = resolveRouteTitle('/groups');
  const builderTitle = resolveRouteTitle('/tests/create');
  assert.ok(!panelTitle.includes('Tizimga kirish'));
  assert.ok(panelTitle.includes('Admin'));
  assert.ok(groupsTitle.includes('Guruhlar'));
  assert.ok(builderTitle.includes('Test'));
});

test('global admin workspace excludes student subject switcher by default', () => {
  const admin = { role: 'admin', is_platform_admin: true };
  assert.equal(getDefaultWorkspace(admin, '/panel'), 'admin');
  assert.equal(shouldShowSubjectSwitcher('admin', '/panel'), false);
  assert.deepEqual(getAvailableWorkspaces(admin), ['admin', 'teacher', 'student']);

  const student = { role: 'student' };
  assert.equal(getDefaultWorkspace(student, '/dashboard'), 'student');
  assert.equal(shouldShowSubjectSwitcher('student', '/dashboard'), true);
  assert.deepEqual(getAvailableWorkspaces(student), ['student']);

  const englishTitle = resolveRouteTitle('/english');
  assert.ok(englishTitle.includes('English Center'));
  assert.equal(shouldShowSubjectSwitcher('admin', '/english'), false);
  assert.equal(shouldShowSubjectSwitcher('student', '/english'), true);
});
