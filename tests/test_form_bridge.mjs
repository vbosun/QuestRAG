import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source = readFileSync(new URL('../mock_business_system/form_bridge.js', import.meta.url), 'utf8');

function fixture(origin = 'http://127.0.0.1:8020') {
  const inputs = ['full_name', 'phone', 'occupation', 'proof'].map(id => ({
    id, type: id === 'proof' ? 'file' : 'text', value: '', required: false,
    style: {outline: '', outlineOffset: '', boxShadow: ''}, scrollIntoView() {},
    closest: () => ({textContent: `${id} *`}),
  }));
  const formEvents = {};
  const windowEvents = {};
  const messages = [];
  const status = {textContent: ''};
  const button = {disabled: false};
  const parent = {postMessage: (payload, origin) => messages.push({payload, origin})};
  let requests = 0;
  const form = {
    querySelectorAll: () => inputs,
    querySelector: () => button,
    elements: {namedItem: name => inputs.find(input => input.id === name)},
    addEventListener: (type, handler) => {formEvents[type] = handler;},
    reportValidity: () => inputs.every(input => !input.required || input.value),
    contains: () => false,
  };
  vm.runInNewContext(source, {
    document: {querySelector: selector => selector === '#applicationForm' ? form : status},
    window: {parent, addEventListener: (type, handler) => {windowEvents[type] = handler;}},
    location: {pathname: '/employment-registration/apply', origin},
    FormData: class {},
    fetch: async () => {requests++; return {ok: true, json: async () => ({message: 'received', application_no: 'demo'})};},
  });
  const supply = (fields, origin = 'http://127.0.0.1:5173', source = parent) => windowEvents.message({origin, source, data: {type: 'agent-form-state', fields}});
  const progress = (data, origin = 'http://127.0.0.1:5173', source = parent) => windowEvents.message({origin, source, data: {type: 'agent-form-progress', task_id: 't', ...data}});
  const snapshot = (page_id = 'p') => windowEvents.message({origin: 'http://127.0.0.1:5173', source: parent, data: {type: 'agent-form-snapshot-request', page_id}});
  return {inputs, formEvents, supply, progress, snapshot, messages, parent, status, button, requests: () => requests};
}

test('prefill acknowledgement reports missing fields and never submits', () => {
  const f = fixture();
  f.supply({full_name: 'Demo', phone: '13800138000'});
  const ack = f.messages.at(-1);
  assert.equal(ack.origin, 'http://127.0.0.1:5173');
  assert.equal(ack.payload.applied_count, 2);
  assert.deepEqual(Array.from(ack.payload.missing_required_labels), ['occupation', 'proof']);
  assert.equal(f.requests(), 0);
});

test('repeated polling preserves user changes including deliberately cleared fields', () => {
  const f = fixture();
  f.supply({phone: '13800138000'});
  const phone = f.inputs.find(input => input.id === 'phone');
  phone.value = '13900139000';
  f.formEvents.input({target: phone});
  f.supply({phone: '13800138000'});
  assert.equal(phone.value, '13900139000');
  phone.value = '';
  f.formEvents.input({target: phone});
  f.supply({phone: '13800138000'});
  assert.equal(phone.value, '');
});

test('messages from an unrelated origin or window cannot supply fields', () => {
  const f = fixture();
  f.supply({phone: '13800138000'}, 'https://untrusted.example');
  f.supply({phone: '13800138000'}, 'http://127.0.0.1:5173', {});
  assert.equal(f.inputs.find(input => input.id === 'phone').value, '');
  assert.equal(f.messages.length, 0);
});

test('incomplete form does not call the mock submit endpoint', async () => {
  const f = fixture();
  await f.formEvents.submit({preventDefault() {}});
  assert.equal(f.requests(), 0);
});

test('same-origin deployed form accepts its parent and rejects unrelated origins', () => {
  const f = fixture('https://demo.example');
  f.supply({phone: '13800138000'}, 'https://untrusted.example');
  assert.equal(f.messages.length, 0);
  f.supply({phone: '13800138000'}, 'https://demo.example');
  assert.equal(f.messages.at(-1).origin, 'https://demo.example');
  assert.equal(f.inputs.find(input => input.id === 'phone').value, '13800138000');
});

test('targets highlight natively, only confirmed values are applied, and terminal status clears highlight', () => {
  const f = fixture();
  const phone = f.inputs.find(input => input.id === 'phone');
  f.progress({status: 'running', operations: [{sequence: 1, phase: 'started', field_key: 'phone', label: '联系电话', value: 'unconfirmed'}]});
  assert.equal(phone.value, '');
  assert.match(phone.style.outline, /#0e9f94/);
  assert.equal(f.button.disabled, true);
  f.progress({status: 'running', fields: {phone: '13800138000'}, operations: [{sequence: 2, phase: 'applied', field_key: 'phone', label: '联系电话', value: '13800138000'}]});
  assert.equal(phone.value, '13800138000');
  f.progress({status: 'completed'});
  assert.equal(phone.style.outline, '');
  assert.equal(f.button.disabled, false);
  assert.equal(f.requests(), 0);
});

test('takeover ignores late active status, old sequences, foreign tasks and untrusted windows', () => {
  const f = fixture();
  const phone = f.inputs.find(input => input.id === 'phone');
  f.progress({status: 'running', operations: [{sequence: 2, phase: 'applied', field_key: 'phone', label: '电话', value: 'confirmed'}]});
  f.progress({status: 'running', operations: [{sequence: 1, phase: 'applied', field_key: 'phone', label: '电话', value: 'old'}]});
  assert.equal(phone.value, 'confirmed');
  f.progress({status: 'running', task_id: 'foreign', fields: {phone: 'foreign'}});
  f.progress({status: 'running', fields: {phone: 'foreign'}}, 'https://untrusted.example');
  f.progress({status: 'running', fields: {phone: 'foreign'}}, 'http://127.0.0.1:5173', {});
  assert.equal(phone.value, 'confirmed');
  f.progress({status: 'cancelled'});
  f.progress({status: 'running', fields: {phone: 'late'}});
  assert.equal(phone.value, 'confirmed');
  assert.equal(f.button.disabled, false);
});

test('progress cannot overwrite manual edits or selected files and active agent cannot submit', async () => {
  const f = fixture();
  const phone = f.inputs.find(input => input.id === 'phone');
  phone.value = '';
  f.formEvents.input({target: phone});
  f.progress({status: 'running', fields: {phone: 'AI', proof: 'invalid'}, operations: [{sequence: 1, phase: 'applied', field_key: 'phone', label: '电话', value: 'AI'}]});
  assert.equal(phone.value, '');
  assert.equal(phone.style.outline, '');
  assert.equal(f.inputs.find(input => input.id === 'proof').value, '');
  for (const input of f.inputs) input.value = 'test';
  await f.formEvents.submit({preventDefault() {}});
  assert.equal(f.requests(), 0);
});

test('follow-up task replaces explicitly requested manual fields, protects later edits and retires old events', () => {
  const f = fixture();
  const phone = f.inputs.find(input => input.id === 'phone');
  const occupation = f.inputs.find(input => input.id === 'occupation');
  f.snapshot();
  phone.value = '13900139000';
  f.formEvents.input({target: phone});
  occupation.value = '人工职业';
  f.formEvents.input({target: occupation});
  f.progress({status: 'completed'});
  const next = {task_id: 't2', command_id: 'cmd2', page_id: 'p', status: 'running',
    requested_fields: {phone: '13800138000'}, field_revisions: {phone: 1},
    operations: [{sequence: 1, phase: 'started', field_key: 'phone', label: '电话'}]};
  f.progress(next);
  assert.match(phone.style.outline, /#0e9f94/);
  f.progress({...next, fields: {phone: '13800138000', occupation: '后台旧值'},
    operations: [{sequence: 2, phase: 'applied', field_key: 'phone', label: '电话', value: '13800138000'}]});
  assert.equal(phone.value, '13800138000');
  assert.equal(occupation.value, '人工职业');
  f.progress({...next, status: 'completed'});
  f.progress({status: 'running', fields: {phone: '旧任务'}});
  assert.equal(phone.value, '13800138000');
  const third = {...next, task_id: 't3', command_id: 'cmd3', operations: []};
  f.progress(third);
  phone.value = '';
  f.formEvents.input({target: phone});
  f.progress({...third, fields: {phone: '13800138000'}, operations: [{sequence: 1, phase: 'applied', field_key: 'phone', value: '13800138000'}]});
  assert.equal(phone.value, '');
  const ack = f.messages.at(-1).payload;
  assert.deepEqual(Array.from(ack.conflicts), ['phone']);
  assert.equal(ack.fields.phone, '');
  assert.equal(ack.field_revisions.phone, 2);
  assert.equal(ack.task_id, 't3');
  assert.equal(ack.fields.proof, undefined);
  assert.equal(f.requests(), 0);
});

test('a new explicit command can be discovered before the previous terminal poll, but wrong pages are ignored', () => {
  const f = fixture();
  f.snapshot();
  f.progress({status: 'running'});
  const next = {task_id: 'next', command_id: 'new', page_id: 'wrong', status: 'running', requested_fields: {phone: 'new'},
    field_revisions: {}, operations: [{sequence: 1, phase: 'applied', field_key: 'phone', value: 'new'}]};
  f.progress(next);
  assert.equal(f.inputs.find(i => i.id === 'phone').value, '');
  f.progress({...next, page_id: 'p'});
  assert.equal(f.inputs.find(i => i.id === 'phone').value, 'new');
});
