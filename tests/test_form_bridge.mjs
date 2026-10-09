import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source = readFileSync(new URL('../mock_business_system/form_bridge.js', import.meta.url), 'utf8');

function fixture(origin = 'http://127.0.0.1:8020') {
  const inputs = ['full_name', 'phone', 'occupation', 'proof'].map(id => ({
    id, type: id === 'proof' ? 'file' : 'text', value: '', required: false,
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
  };
  vm.runInNewContext(source, {
    document: {querySelector: selector => selector === '#applicationForm' ? form : status},
    window: {parent, addEventListener: (type, handler) => {windowEvents[type] = handler;}},
    location: {pathname: '/employment-registration/apply', origin},
    FormData: class {},
    fetch: async () => {requests++; return {ok: true, json: async () => ({message: 'received', application_no: 'demo'})};},
  });
  const supply = (fields, origin = 'http://127.0.0.1:5173', source = parent) => windowEvents.message({origin, source, data: {type: 'agent-form-state', fields}});
  return {inputs, formEvents, supply, messages, parent, status, requests: () => requests};
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
