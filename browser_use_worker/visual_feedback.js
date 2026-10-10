(() => {
  if (window.__questAgentVisual) return;
  const state = window.__questAgentVisual = { enabled: true, events: [], sequence: 0 };
  let target;
  const host = document.createElement('div');
  host.dataset.questAgentOverlay = '';
  host.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647';
  const root = host.attachShadow({mode:'closed'});
  root.innerHTML = `<style>
    .box{position:fixed;border:3px solid #12b8ae;border-radius:8px;background:#12b8ae12;box-shadow:0 0 0 5px #12b8ae20;display:none}
  </style><div class="box"></div>`;
  const box = root.querySelector('.box');
  function mount(){ if(!host.isConnected && document.documentElement) document.documentElement.append(host); }
  function position(){
    if(!state.enabled || !target?.isConnected){box.style.display='none';state.cursor=null;return;}
    const r=target.getBoundingClientRect();
    box.style.cssText += `;display:block;left:${r.left-3}px;top:${r.top-3}px;width:${r.width}px;height:${r.height}px`;
    state.cursor={x:r.left+r.width*.6,y:r.top+r.height*.55};
  }
  function observe(event){
    if(!state.enabled) return;
    const el=event.composedPath().find(e=>e instanceof Element && e.matches('input,select,textarea,button,a,[role="button"]'));
    if(!el) return;
    mount(); target=el;
    const label=(el.labels?.[0] ? Array.from(el.labels[0].childNodes).filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join(' ') : el.getAttribute('aria-label') || el.name || el.id || el.innerText || '页面控件').replace(/\s+/g,' ').trim().slice(0,80);
    const field_key = el.name || el.id;
    state.events.push({sequence:++state.sequence,kind:event.type,label,field_key});state.events=state.events.slice(-30);
    if (field_key && typeof window.__questAgentTarget === 'function')
      window.__questAgentTarget({field_key,label}).catch(() => {});
    position();
  }
  for(const name of ['focusin','input','change','click']) document.addEventListener(name,observe,true);
  document.addEventListener('scroll',position,true);window.addEventListener('resize',position);
  state.setEnabled=(enabled)=>{state.enabled=enabled;position();};
  mount();
})();
