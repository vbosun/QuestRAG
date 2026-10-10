// Shared bridge for the two local demo forms. Only the authorized parent may
// supply values; polling must never undo a user's edits in the business page.
const form = document.querySelector('#applicationForm');
const agentStatus = document.querySelector('#agentStatus');
const allowedParents = new Set([location.origin, 'http://localhost:5173', 'http://127.0.0.1:5173']);
const dirtyFields = new Set();
let parentOrigin = null;
let appliedCount = 0;
let submitted = false;
let activeTask = null;
let lastSequence = 0;
let taskFinished = false;
let agentRunning = false;
let highlighted = null;
let savedHighlight = null;
let pageId = null;
let snapshotSequence = 0;
const fieldRevisions = {};
const retiredTasks = new Set();
const conflicts = new Set();
let requestedFields = {};
let expectedRevisions = {};

function clearHighlight() {
  if (highlighted) Object.assign(highlighted.style, savedHighlight);
  highlighted = null;
  savedHighlight = null;
}

function highlight(input, phase) {
  clearHighlight();
  if (!input || (dirtyFields.has(input.id) && !canApply(input))) return;
  highlighted = input;
  savedHighlight = {outline: input.style.outline, outlineOffset: input.style.outlineOffset, boxShadow: input.style.boxShadow};
  const color = phase === 'failed' ? '#c23b3b' : '#0e9f94';
  Object.assign(input.style, {outline: `2px solid ${color}`, outlineOffset: '3px', boxShadow: `0 0 0 5px ${color}18`});
  // Keep a user's current editing position; highlighting never steals focus.
  if (!form.contains(document.activeElement)) input.scrollIntoView({block: 'nearest', inline: 'nearest'});
}

function canApply(input) {
  if (Object.hasOwn(requestedFields, input.id)) {
    const matches = (fieldRevisions[input.id] || 0) === (expectedRevisions[input.id] || 0);
    if (!matches) conflicts.add(input.id);
    return matches;
  }
  return !dirtyFields.has(input.id);
}

function applyFields(fields, allowEmpty = false, progress = false) {
  appliedCount = 0;
  for (const [key, value] of Object.entries(fields || {})) {
    const input = form.elements.namedItem(key);
    if (!input || input.type === 'file' || value == null || (!allowEmpty && value === '')) continue;
    if (progress ? canApply(input) : !dirtyFields.has(input.id)) input.value = String(value);
    if (input.value) appliedCount += 1;
  }
}

for (const input of form.querySelectorAll('input, select')) {
  input.required = true;
}
const phone = form.elements.namedItem('phone');
phone.pattern = '1[3-9][0-9]{9}';
phone.title = '请输入 11 位手机号码';

function missingLabels() {
  return [...form.querySelectorAll('input, select')]
    .filter(input => input.required && !input.value)
    .map(input => input.closest('label').textContent.replace('*', '').trim());
}

function acknowledge() {
  if (!parentOrigin) return;
  window.parent.postMessage({
    type: 'agent-form-applied', applied_count: appliedCount,
    missing_required_labels: missingLabels(),
    page_id: pageId, sequence: ++snapshotSequence,
    fields: Object.fromEntries([...form.querySelectorAll('input, select, textarea')]
      .filter(input => !['file', 'password', 'hidden'].includes(input.type))
      .map(input => [input.name || input.id, input.value])),
    field_revisions: {...fieldRevisions}, task_id: activeTask,
    conflicts: [...conflicts], submitted,
  }, parentOrigin);
}

for (const eventType of ['input', 'change']) {
  form.addEventListener(eventType, event => {
    if (event.target.id) {
      dirtyFields.add(event.target.id);
      if (!['file', 'password', 'hidden'].includes(event.target.type))
        fieldRevisions[event.target.id] = (fieldRevisions[event.target.id] || 0) + 1;
    }
    if (event.target === highlighted) clearHighlight();
    acknowledge();
  });
}

window.addEventListener('message', event => {
  if (!allowedParents.has(event.origin) || event.source !== window.parent) return;
  if (event.data?.type === 'agent-form-snapshot-request') {
    parentOrigin = event.origin;
    pageId = event.data.page_id;
    acknowledge();
    return;
  }
  if (event.data?.type === 'agent-form-restore' && !activeTask) {
    parentOrigin = event.origin;
    applyFields(event.data.fields, true);
    for (const key of Object.keys(event.data.fields || {})) dirtyFields.add(key);
    acknowledge();
    return;
  }
  if (submitted) return;
  if (event.data?.type === 'agent-form-progress') {
    const data = event.data;
    if (data.page_id && data.page_id !== pageId) return;
    if (retiredTasks.has(data.task_id)) return;
    if (activeTask && data.task_id !== activeTask) {
      if (!data.command_id || data.page_id !== pageId) return;
      retiredTasks.add(activeTask);
      lastSequence = 0;
      taskFinished = false;
      clearHighlight();
      conflicts.clear();
    }
    requestedFields = data.command_id ? data.requested_fields || {} : {};
    expectedRevisions = data.field_revisions || {};
    if (data.task_id) activeTask = data.task_id;
    if (taskFinished && ['queued', 'running'].includes(data.status)) return;
    parentOrigin = event.origin;
    agentRunning = ['idle', 'queued', 'running'].includes(data.status);
    form.querySelector('button[type="submit"]').disabled = agentRunning;
    const snapshotSequence = Math.max(0, ...(data.operations || []).map(operation => operation.sequence || 0));
    const visibleFields = data.command_id ? Object.fromEntries(Object.entries(data.fields || {}).filter(([key]) => Object.hasOwn(requestedFields, key))) : data.fields;
    if (snapshotSequence >= lastSequence) applyFields(visibleFields, true, true);
    for (const operation of data.operations || []) {
      if (!Number.isInteger(operation.sequence) || operation.sequence <= lastSequence) continue;
      lastSequence = operation.sequence;
      const input = form.elements.namedItem(operation.field_key);
      if (data.command_id && !Object.hasOwn(requestedFields, operation.field_key)) continue;
      if (!input || !['started', 'applied', 'failed', 'cancelled'].includes(operation.phase)) continue;
      if (operation.phase === 'applied') applyFields({[operation.field_key]: operation.value}, true, true);
      if (operation.phase === 'cancelled') clearHighlight();
      else highlight(input, operation.phase);
      agentStatus.textContent = operation.phase === 'started' ? `AI 正在操作：${operation.label}`
        : operation.phase === 'failed' ? `自动填写未成功：${operation.label}，请核对。`
        : dirtyFields.has(input.id) ? `已保留您修改的${operation.label}。` : `已同步：${operation.label}`;
    }
    if (!agentRunning) {
      taskFinished = true;
      clearHighlight();
      agentStatus.textContent = data.status === 'completed' ? '自动填写已结束，请核对信息、补充材料后自行提交。'
        : '自动填写已停止，您可以继续核对和手动填写。';
    }
    appliedCount = [...form.querySelectorAll('input, select')].filter(input => input.type !== 'file' && input.value).length;
    acknowledge();
    return;
  }
  if (event.data?.type !== 'agent-form-state') return;
  parentOrigin = event.origin;
  applyFields(event.data.fields, event.data.allow_empty === true);
  if (!activeTask && !agentRunning) {
    agentStatus.textContent = appliedCount
      ? `已带入 ${appliedCount} 项已有信息，请核对并补充必填项。`
      : '请填写必填信息并上传证明材料。';
  }
  acknowledge();
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (agentRunning) return;
  if (!form.reportValidity()) return;
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  agentStatus.textContent = '正在提交到模拟业务系统…';
  try {
    const business = location.pathname.startsWith('/unemployment-registration/')
      ? 'unemployment-registration' : 'employment-registration';
    const response = await fetch(`/api/${business}/submit`, {method: 'POST', body: new FormData(form)});
    const result = await response.json();
    if (!response.ok) throw new Error('提交失败，请核对信息后重试。');
    submitted = true;
    acknowledge();
    agentStatus.textContent = `${result.message} 申请编号：${result.application_no}`;
    if (parentOrigin) window.parent.postMessage({type: 'mock-business-submitted', message: agentStatus.textContent}, parentOrigin);
  } catch (error) {
    agentStatus.textContent = error instanceof Error ? error.message : '提交失败，请稍后重试。';
    button.disabled = false;
  }
});
