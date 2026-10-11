// Helpers used by the native business forms, including standalone applicants.
(() => {
  const form = document.querySelector('#applicationForm');
  const caseId = new URLSearchParams(location.search).get('case_id') || '';
  const id = [...crypto.getRandomValues(new Uint8Array(24))].map(n => n.toString(16).padStart(2, '0')).join('');
  let submissionId = id;
  let linkToken = '';
  // Reopening an embedded case retries the same submission instead of duplicating it.
  if (caseId) {
    try {const key = 'business-submission:' + location.pathname + ':' + caseId; submissionId = sessionStorage.getItem(key) || id; sessionStorage.setItem(key, submissionId);} catch { /* Idempotent within this page even when storage is disabled. */ }
  }
  if (window.parent === window) {
    form.elements.full_name.readOnly = false;
    const navigation = document.createElement('p');
    const home = document.createElement('a');
    home.href = '/business/'; home.textContent = '← 返回业务首页';
    navigation.append(home); document.querySelector('main').prepend(navigation);
  }
  for (const input of form.querySelectorAll('input[type="file"]')) {
    const hint = document.createElement('small');
    hint.textContent = '单份材料不超过5MB'; hint.style.cssText = 'font-weight:400;color:#698083';
    input.after(hint);
    input.addEventListener('change', () => input.setCustomValidity(input.files[0]?.size > 5 * 1024 * 1024 ? '材料不能超过5MB' : ''));
  }
  window.businessSubmission = {
    setLink(link) {
      if (link?.case_id !== caseId || !/^[a-zA-Z0-9_-]{43}$/.test(link.token || '')) return;
      linkToken = link.token;
      if (!current && Date.now() - lastLinkCheck > 10000) { lastLinkCheck = Date.now(); refresh(); }
    },
    prepare(body) {
      if (caseId && window.parent !== window && !linkToken) throw new Error('申请关联尚未就绪，请稍后重试或重新打开申请页面。');
      body.set('submission_id', submissionId); body.set('case_id', caseId); body.set('link_token', linkToken);
    },
    showReceipt(result) {
      credential = {number: result.application_no, code: result.query_code};
      try { sessionStorage.setItem(storageKey, JSON.stringify(credential)); } catch {}
      if (result.progress) render(result.progress);
      else refresh();
    },
  };
  const storageKey = 'business-progress:' + location.pathname + ':' + caseId;
  if (!caseId && new URLSearchParams(location.search).get('new') === '1') {
    try { sessionStorage.removeItem(storageKey); } catch {}
    history.replaceState(null, '', location.pathname);
  }
  let credential = null;
  let current = null;
  let timer = null;
  let busy = false;
  let lastLinkCheck = 0;
  let panel = null;
  try { credential = JSON.parse(sessionStorage.getItem(storageKey) || 'null'); } catch {}

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function timeText(value) {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', {hour12:false});
  }
  function schedule() {
    clearTimeout(timer);
    if (!current || current.status === 'PENDING') timer = setTimeout(refresh, 10000);
  }
  function render(data) {
    if (!['PENDING','APPROVED','REJECTED'].includes(data.status)) throw new Error('办理状态暂时无法确认');
    const first = !current;
    current = data;
    if (!panel) {
      panel = element('section', '', 'business-progress'); panel.id = 'applicationProgress';
      panel.setAttribute('aria-label', '办理进度');
      form.after(panel);
      form.hidden = true;
      form.querySelectorAll('input,select,textarea,button').forEach(input => input.disabled = true);
      document.querySelectorAll('main .steps, .card > p, .card > .notice').forEach(node => node.hidden = true);
      const heading = document.querySelector('header h1');
      if (heading) heading.textContent = data.business_name + '办理进度';
    }
    panel.replaceChildren();
    const done = data.status !== 'PENDING';
    const rejected = data.status === 'REJECTED';
    const title = element('div', '', 'progress-heading');
    title.append(element('h2','办理进度'), element('span', done ? (rejected ? '已驳回' : '审批通过') : '等待审批', 'progress-badge' + (rejected ? ' rejected' : '')));
    const steps = element('ol', '', 'progress-steps');
    const labels = ['申请成功','等待审批', done ? (rejected ? '已驳回' : '审批通过') : '审批结果'];
    labels.forEach((label,index) => {
      const active = done ? index === 2 : index === 1;
      const complete = index === 0 || (done && index === 1);
      const item = element('li','', complete ? 'complete' : active ? (rejected ? 'active rejected' : 'active') : '');
      if (active) item.setAttribute('aria-current','step');
      item.append(element('span', complete || (done && active && !rejected) ? '✓' : rejected && active ? '!' : String(index + 1),'step-dot'),element('strong',label));
      const caption = index === 0 ? timeText(data.created_at) : index === 1 ? (done ? '审批已完成' : '申请已受理，请耐心等待') : (done ? timeText(data.reviewed_at) : '审批完成后更新');
      item.append(element('small',caption)); steps.append(item);
    });
    const note = element('p',done ? (rejected ? '请查看审批意见，按要求准备后重新申请。' : '本次申请已审批通过。') : '材料已随申请送达，关闭页面不会影响办理。','progress-note');
    panel.append(title,steps,note);
    if (done) panel.append(element('h3','审批意见'),element('p',data.comment || '暂无补充意见','review-comment'));
    if (data.materials?.length) {
      const materials = element('div','','progress-materials');
      materials.append(element('h3','已接收材料'));
      data.materials.forEach(item => materials.append(element('p',item.name + ' · ' + Math.max(1,Math.ceil(item.size_bytes / 1024)) + ' KB')));
      panel.append(materials);
    }
    const footer = element('div','','progress-footer');
    const live = element('span','刚刚更新','progress-live'); live.id = 'progressUpdate'; live.setAttribute('role','status');
    const refreshButton = element('button','刷新进度'); refreshButton.type = 'button'; refreshButton.onclick = refresh;
    footer.append(live,refreshButton); panel.append(footer);
    window.dispatchEvent(new Event('business-submitted'));
    if (first) panel.scrollIntoView({block:'nearest'});
    schedule();
  }
  async function refresh() {
    if (busy || (!credential && !linkToken)) return;
    if (document.hidden) { schedule(); return; }
    busy = true;
    const status = document.querySelector('#progressUpdate');
    if (status) status.textContent = '正在更新…';
    try {
      const url = credential ? '/business/api/query' : '/business/api/case-status';
      const body = credential || {case_id: caseId, token: linkToken};
      const response = await fetch(url, {method:'POST',headers:{'Content-Type':'application/json','X-Business-Request':'1'},body:JSON.stringify(body),signal:AbortSignal.timeout(5000)});
      if (response.status === 404 && !current && !credential) return;
      if (!response.ok) throw new Error('query failed');
      render(await response.json());
    } catch {
      const status = document.querySelector('#progressUpdate');
      if (status) status.textContent = '暂时无法更新，当前显示上次查询结果';
      schedule();
    } finally { busy = false; }
  }
  document.addEventListener('visibilitychange', () => {if (!document.hidden) refresh();});
  if (credential) refresh();
})();
