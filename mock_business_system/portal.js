const root = document.querySelector('#app');
const detailDialog = document.querySelector('#detail');
const labels = {PENDING: '待审批', APPROVED: '已通过', REJECTED: '已驳回'};
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const timeLabel = value => value ? new Date(value).toLocaleString('zh-CN', {hour12: false}) : '—';
const badge = status => `<span class="badge ${escapeHtml(status)}">${labels[status] || '未知状态'}</span>`;
let listPage = 1;
let listGeneration = 0;
let currentNumber = null;
const mode = location.pathname.endsWith('/admin') ? 'admin' : location.pathname.endsWith('/query') ? 'query' : 'home';
document.querySelector(`[data-nav="${mode}"]`).classList.add('active');

async function api(path, body) {
  const response = await fetch('/business/api' + path, {headers: {'Content-Type':'application/json', 'X-Business-Request':'1'}, ...(body !== undefined ? {method:'POST', body:JSON.stringify(body)} : {})});
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : '信息格式不正确，请检查后重试');
    error.status = response.status;
    throw error;
  }
  return data;
}

function home() {
  root.innerHTML = `<section class="hero"><span class="eyebrow">就业服务 · 在线办理</span><h1>办好就业事，安心迈出下一步</h1><p class="muted">在线提交登记申请，上传证明材料。提交后直接查看办理进度及审批意见。</p></section><section class="services"><article class="card service-card"><span class="service-icon">就</span><h2>就业登记</h2><p class="muted">适用于单位就业、灵活就业和自主创业。<br>请准备劳动合同、营业执照或灵活就业证明。</p><a class="button" href="/employment-registration/apply?new=1">办理就业登记 <span aria-hidden="true">→</span></a></article><article class="card service-card"><span class="service-icon">失</span><h2>失业登记</h2><p class="muted">登记当前失业情况及上次就业信息。<br>请准备解除或终止劳动关系证明。</p><a class="button" href="/unemployment-registration/apply?new=1">办理失业登记 <span aria-hidden="true">→</span></a></article></section><section class="card home-bottom"><div><h3 style="margin-bottom:6px">已经提交申请？</h3><span class="muted">在本次浏览会话中重新打开对应业务，即可查看办理进度。</span></div><div class="row"><a class="button secondary" href="/employment-registration/apply">就业进度</a><a class="button secondary" href="/unemployment-registration/apply">失业进度</a><a href="/business/query">历史回执查询</a></div></section>`;
}

function login(message = '') {
  listGeneration++;
  detailDialog.close();
  root.innerHTML = `<section class="narrow card"><span class="eyebrow">审批工作台</span><h1>审批人员登录</h1><p class="muted">查看待办申请，核对材料并作出审批决定。</p><form id="loginForm"><label>审批账号<input name="username" required maxlength="80" autocomplete="username" autofocus></label><label>密码<input type="password" name="password" required maxlength="200" autocomplete="current-password"></label><p class="error" role="alert">${escapeHtml(message)}</p><button type="submit">登录工作台 →</button></form><div class="login-sub">使用独立业务系统的审批账号登录。</div></section>`;
  document.querySelector('#loginForm').onsubmit = async event => {
    event.preventDefault();
    const form = event.target, button = form.querySelector('button');
    button.disabled = true;
    try { const user = await api('/login', Object.fromEntries(new FormData(form))); await workspace(user); }
    catch (error) { form.querySelector('.error').textContent = error.message; }
    finally { button.disabled = false; }
  };
}

async function workspace(user) {
  root.innerHTML = `<div class="page-heading"><div><span class="eyebrow">业务办理</span><h1>审批工作台</h1><p class="muted">核对申请信息与证明材料，处理待办事项。</p></div><div class="account"><span>${escapeHtml(user.name)}</span><button id="changePassword" class="secondary">修改密码</button><button id="logout" class="secondary">退出</button></div></div><section class="stats"><div class="card stat"><span>待审批</span><strong id="countPENDING">—</strong></div><div class="card stat"><span>已通过</span><strong id="countAPPROVED">—</strong></div><div class="card stat"><span>已驳回</span><strong id="countREJECTED">—</strong></div></section><section class="card table-card"><form class="filters" id="filters"><label>审批状态<select name="status" aria-label="审批状态"><option value="PENDING">待审批</option><option value="APPROVED">已通过</option><option value="REJECTED">已驳回</option><option value="">全部状态</option></select></label><label>业务类型<select name="business" aria-label="业务类型"><option value="">全部业务</option><option value="employment-registration">就业登记</option><option value="unemployment-registration">失业登记</option></select></label><label class="search">申请搜索<input name="q" maxlength="100" placeholder="输入申请人姓名或申请编号"></label><button type="submit">查询</button><button type="button" class="secondary" id="refresh">刷新</button></form><p id="listError" class="error" role="alert" style="padding:0 24px"></p><div class="table-wrap"><table><thead><tr><th>申请人 / 编号</th><th>业务类型</th><th>提交时间</th><th>状态</th><th>操作</th></tr></thead><tbody id="rows"></tbody></table></div><div class="pager"><span id="total"></span><div class="row"><button id="prev" class="secondary">上一页</button><span id="pageLabel"></span><button id="next" class="secondary">下一页</button></div></div></section>`;
  document.querySelector('#logout').onclick = async () => { try { await api('/logout', {}); login(); } catch (error) { document.querySelector('#listError').textContent = error.message; } };
  document.querySelector('#changePassword').onclick = () => document.querySelector('#passwordDialog').showModal();
  document.querySelector('#filters').onsubmit = event => {event.preventDefault(); listPage = 1; loadList();};
  document.querySelector('#refresh').onclick = () => loadList();
  document.querySelector('#prev').onclick = () => {listPage--; loadList();};
  document.querySelector('#next').onclick = () => {listPage++; loadList();};
  await loadList();
}

async function loadList() {
  const generation = ++listGeneration;
  const params = new URLSearchParams(new FormData(document.querySelector('#filters')));
  params.set('page', listPage);
  document.querySelector('#listError').textContent = '';
  document.querySelector('#rows').innerHTML = '<tr><td colspan="5" class="empty">正在读取申请…</td></tr>';
  try {
    const data = await api('/applications?' + params);
    if (generation !== listGeneration) return;
    for (const status of Object.keys(labels)) document.querySelector('#count' + status).textContent = data.counts[status] || 0;
    document.querySelector('#rows').innerHTML = data.items.length ? data.items.map(item => `<tr><td><strong>${escapeHtml(item.applicant)}</strong><small>${escapeHtml(item.number)}</small></td><td>${escapeHtml(item.business_name)}</td><td>${timeLabel(item.created_at)}</td><td>${badge(item.status)}</td><td><button class="link-button" data-detail="${escapeHtml(item.number)}">${item.status === 'PENDING' ? '查看并审批' : '查看详情'} →</button></td></tr>`).join('') : '<tr><td colspan="5" class="empty">暂无符合条件的申请</td></tr>';
    document.querySelector('#total').textContent = `共 ${data.total} 份申请`;
    document.querySelector('#pageLabel').textContent = `第 ${listPage} 页`;
    document.querySelector('#prev').disabled = listPage <= 1;
    document.querySelector('#next').disabled = listPage * 20 >= data.total;
    document.querySelectorAll('[data-detail]').forEach(button => button.onclick = () => showDetail(button.dataset.detail));
  } catch (error) {
    if (generation !== listGeneration) return;
    if (error.status === 401) return login('登录已过期，请重新登录');
    document.querySelector('#listError').textContent = error.message;
    document.querySelector('#rows').innerHTML = '<tr><td colspan="5" class="empty">读取失败，请点击刷新重试</td></tr>';
  }
}

async function showDetail(number) {
  currentNumber = number;
  document.querySelector('#detailBody').innerHTML = '<div class="dialog-head"><h2 id="detailTitle">申请详情</h2><button class="icon secondary" data-close="detail" aria-label="关闭详情">×</button></div><p class="empty">正在读取…</p>';
  if (!detailDialog.open) detailDialog.showModal();
  try {
    const item = await api('/applications/' + encodeURIComponent(number));
    if (currentNumber !== number) return;
    renderDetail(item);
  } catch (error) {
    if (error.status === 401) return login('登录已过期，请重新登录');
    document.querySelector('#detailBody').innerHTML += `<p class="error" style="padding:24px">${escapeHtml(error.message)}</p>`;
  }
}

function renderDetail(item) {
  document.querySelector('#detailBody').innerHTML = `<div class="dialog-head"><div><h2 id="detailTitle">${escapeHtml(item.business_name)}申请</h2><small class="muted">${escapeHtml(item.number)}</small></div><button class="icon secondary" data-close="detail" aria-label="关闭详情">×</button></div><div class="dialog-content"><div>${badge(item.status)}</div><section><h3>申请信息</h3><dl class="details">${item.fields.map(field => `<div><dt>${escapeHtml(field.label)}</dt><dd>${escapeHtml(field.value)}</dd></div>`).join('')}</dl></section><section><h3>证明材料</h3><div class="material"><span>${escapeHtml(item.file_name)}<small class="muted"> · ${(item.file_size / 1024).toFixed(1)} KB</small></span><a href="/business/api/applications/${encodeURIComponent(item.number)}/material" download>下载查看 ↓</a></div></section><section><h3>办理记录</h3><div class="timeline"><div>申请已提交<small>${timeLabel(item.created_at)}</small></div>${item.reviewed_at ? `<div>${labels[item.status]} · ${escapeHtml(item.reviewer)}<small>${timeLabel(item.reviewed_at)}</small><div class="result-comment">${escapeHtml(item.comment || '核对通过')}</div></div>` : '<div class="muted">等待审批人员处理</div>'}</div></section>${item.status === 'PENDING' ? '<form id="decisionForm"><label>审批意见<textarea name="comment" rows="3" maxlength="1000" placeholder="请填写核对意见；驳回时必须说明原因"></textarea></label><p id="decisionError" class="error" role="alert"></p><div class="decision-actions"><button type="submit" class="danger" value="reject">驳回申请</button><button type="submit" value="approve">通过申请</button></div></form>' : '<div class="notice">此申请已处理，审批结果已可供申请人查询。</div>'}</div>`;
  const form = document.querySelector('#decisionForm');
  if (form) form.onsubmit = async event => {
    event.preventDefault();
    const action = event.submitter.value, comment = form.elements.comment.value.trim();
    if (action === 'reject' && !comment) {document.querySelector('#decisionError').textContent = '请填写驳回原因'; form.elements.comment.focus(); return;}
    if (!confirm(`确认${action === 'approve' ? '通过' : '驳回'} ${item.applicant} 的${item.business_name}申请？`)) return;
    form.querySelectorAll('button').forEach(button => button.disabled = true);
    try { const updated = await api(`/applications/${encodeURIComponent(item.number)}/decision`, {action, comment}); renderDetail(updated); await loadList(); }
    catch (error) { if (error.status === 401) return login('登录已过期，请重新登录'); document.querySelector('#decisionError').textContent = error.message; form.querySelectorAll('button').forEach(button => button.disabled = false); }
  };
}

function queryPage() {
  root.innerHTML = `<section class="narrow"><div class="card"><span class="eyebrow">办理进度</span><h1>查询申请结果</h1><p class="muted">请输入提交成功后回执中的申请编号与查询码。</p><form id="queryForm"><label>申请编号<input name="number" required maxlength="100" placeholder="MOCK-…" autocomplete="off"></label><label>查询码<input name="code" required maxlength="100" placeholder="填写回执上的查询码" autocomplete="off"></label><p class="error" role="alert"></p><button type="submit">查询结果</button></form></div><div id="queryResult"></div></section>`;
  const form = document.querySelector('#queryForm');
  // Receipt secrets travel in the fragment only and are removed immediately.
  const fragment = new URLSearchParams(location.hash.slice(1));
  form.elements.number.value = fragment.get('number') || '';
  form.elements.code.value = fragment.get('code') || '';
  if (location.hash) history.replaceState(null, '', location.pathname);
  form.onsubmit = async event => {
    event.preventDefault();
    form.querySelector('button').disabled = true;
    form.querySelector('.error').textContent = '';
    document.querySelector('#queryResult').innerHTML = '';
    try {
      const item = await api('/query', Object.fromEntries(new FormData(form)));
      document.querySelector('#queryResult').innerHTML = `<section class="card query-result"><div class="row"><h2>${escapeHtml(item.business_name)}</h2>${badge(item.status)}</div><p class="muted wide-text">${escapeHtml(item.number)}</p><div class="result-line"><span>提交时间</span><span>${timeLabel(item.created_at)}</span></div>${item.reviewed_at ? `<div class="result-line"><span>审批时间</span><span>${timeLabel(item.reviewed_at)}</span></div><h3 style="margin-top:24px">审批意见</h3><p class="result-comment">${escapeHtml(item.comment || '核对通过')}</p>` : '<p class="notice" style="margin-top:24px">申请已收到，等待审批人员核对信息和材料。</p>'}</section>`;
    } catch (error) {form.querySelector('.error').textContent = error.message;}
    finally {form.querySelector('button').disabled = false;}
  };
  if (form.elements.number.value && form.elements.code.value) form.requestSubmit();
}

document.addEventListener('click', event => {const button = event.target.closest('[data-close]'); if (button) document.getElementById(button.dataset.close).close();});
document.querySelector('#passwordForm').onsubmit = async event => {
  event.preventDefault();
  const form = event.target, button = form.querySelector('button');
  button.disabled = true;
  try {await api('/password', Object.fromEntries(new FormData(form))); document.querySelector('#passwordDialog').close(); form.reset(); login('密码已修改，请重新登录');}
  catch (error) {document.querySelector('#passwordError').textContent = error.message;}
  finally {button.disabled = false;}
};
if (mode === 'home') home();
else if (mode === 'query') queryPage();
else api('/me').then(workspace).catch(error => login(error.status === 401 ? '' : error.message));
