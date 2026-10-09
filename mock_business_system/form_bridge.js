// Shared bridge for the two local demo forms. Only the authorized parent may
// supply values; polling must never undo a user's edits in the business page.
const form = document.querySelector('#applicationForm');
const agentStatus = document.querySelector('#agentStatus');
const allowedParents = new Set([location.origin, 'http://localhost:5173', 'http://127.0.0.1:5173']);
const dirtyFields = new Set();
let parentOrigin = null;
let appliedCount = 0;
let submitted = false;

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
  }, parentOrigin);
}

for (const eventType of ['input', 'change']) {
  form.addEventListener(eventType, event => {
    if (event.target.id) dirtyFields.add(event.target.id);
    acknowledge();
  });
}

window.addEventListener('message', event => {
  if (!allowedParents.has(event.origin) || event.source !== window.parent) return;
  if (event.data?.type !== 'agent-form-state' || submitted) return;
  parentOrigin = event.origin;
  appliedCount = 0;
  for (const [key, value] of Object.entries(event.data.fields || {})) {
    const input = form.elements.namedItem(key);
    if (!input || input.type === 'file' || value == null || value === '') continue;
    if (!dirtyFields.has(input.id)) input.value = String(value);
    if (input.value) appliedCount += 1;
  }
  agentStatus.textContent = appliedCount
    ? `已带入 ${appliedCount} 项已有信息，请核对并补充必填项。`
    : '请填写必填信息并上传证明材料。';
  acknowledge();
});

form.addEventListener('submit', async event => {
  event.preventDefault();
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
    agentStatus.textContent = `${result.message} 申请编号：${result.application_no}`;
    if (parentOrigin) window.parent.postMessage({type: 'mock-business-submitted', message: agentStatus.textContent}, parentOrigin);
  } catch (error) {
    agentStatus.textContent = error instanceof Error ? error.message : '提交失败，请稍后重试。';
    button.disabled = false;
  }
});
