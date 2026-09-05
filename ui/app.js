const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {config:null,runs:[],selected:null,detail:null,tab:'results',nav:'overview',busy:false,prd:null,legacyRequirements:'',navigationOrigins:[],open:new Set()};
const terminal = status => !['queued','running'].includes(status);
const pill = status => `<span class="pill ${esc(status)}">${esc(status.replaceAll('_',' '))}</span>`;
const time = value => new Date(value).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
async function api(path, options={}) {
  const response=await fetch(`/api${path}`,{...options,headers:{'Content-Type':'application/json',...options.headers}});
  let body; try {body=await response.json();} catch {throw new Error('The local server returned an unreadable response.');}
  if(!response.ok) throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail));
  return body;
}
function toast(message) { $('toast').textContent=message;$('toast').classList.remove('hidden');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.add('hidden'),5000); }
function showError(id,message) {$(id).textContent=message;$(id).classList.toggle('hidden',!message);}
function openRun(demo=false, request=null) {
  if(!state.config) return toast('Waiting for local configuration.');
  $('target-url').value=request?.url || (demo?state.config.demo_url:'https://www.saucedemo.com/inventory.html');
  $('run-mode').value=request?.mode || (demo || !state.config.openai_configured?'baseline':'openai');
  $('run-scope').value=request?.scope || '';state.legacyRequirements='';
  state.prd=request?.prd_content?{name:request.prd_name,content:request.prd_content}:request?.requirements?{name:'previous-requirements.md',content:request.requirements}:null;$('prd-file').value='';renderPrd();
  $('max-pages').value=request?.max_pages || 5;$('allow-interactions').checked=request?.allow_interactions || false;
  $('resource-policy').value=request?.resource_policy || 'compatible';
  state.navigationOrigins=request?.navigation_origins||[];$('max-flows').value=request?.max_flows||6;
  $('advanced-options').open=false;
  showError('form-error','');$('run-dialog').showModal();
}
function renderRuns() {
  const query=$('run-search').value.toLowerCase();
  const filtered=state.runs.filter(r=>r.request.url.toLowerCase().includes(query)&&(state.nav!=='reports'||r.status==='completed'));
  const runs=state.nav==='overview'&&!query?filtered.slice(0,6):filtered;
  $('view-all-runs').classList.toggle('hidden',state.nav!=='overview');
  $('run-count').textContent=state.runs.length;$('recent-count').textContent=runs.length;
  $('empty-runs').classList.toggle('hidden',runs.length>0);
  $('run-list').innerHTML=runs.map(r=>{
    const host=new URL(r.request.url).host,s=r.summary;
    return `<tr><td><div class="run-target"><span class="target-icon" aria-hidden="true">${esc(host.slice(0,1).toUpperCase())}</span><button class="run-link" data-run="${r.id}"><strong>${esc(host)}</strong><small>${r.id.slice(0,8)} · ${r.request.mode==='openai'?'OpenAI':'Baseline'}</small></button></div></td><td>${pill(r.status)}</td><td><span class="result-count">${s.total!==undefined?`${s.passed} / ${s.total} passed`:'—'}</span></td><td class="muted">${time(r.created)}</td><td><button class="text-button" data-run="${r.id}" aria-label="Open run ${r.id.slice(0,8)}">↗</button></td></tr>`;
  }).join('');
  const complete=state.runs.filter(r=>r.status==='completed');
  const totals=complete.reduce((a,r)=>({total:a.total+(r.summary.total||0),passed:a.passed+(r.summary.passed||0),healed:a.healed+(r.summary.healed||0),attention:a.attention+(r.summary.failed||0)+(r.summary.blocked||0)}),{total:0,passed:0,healed:0,attention:0});
  $('metric-total').textContent=state.runs.length;$('metric-rate').textContent=totals.total?`${Math.round(totals.passed/totals.total*100)}%`:'—';
  $('metric-rate-caption').textContent=totals.total?`${totals.passed} of ${totals.total} scenarios passed`:'No completed scenarios yet';
  $('metric-heals').textContent=totals.healed;$('metric-attention').textContent=totals.attention;
}
function artifactUrl(name) {return `/api/runs/${state.selected}/artifacts/${encodeURIComponent(name)}`;}
function diagnosticHTML(r) {
  return r.diagnostics?.length?`<details class="result-item"><summary class="result-summary"><span class="pill needs_review">Browser warnings (${r.diagnostics.length}) · ${esc(r.name)}</span></summary><pre class="code">${esc(JSON.stringify(r.diagnostics,null,2))}</pre></details>`:'';
}
function resultHTML(r) {
  const image=r.healed_attempt?.screenshot||r.screenshot;
  return `<details class="result-item" data-flow="${esc(r.flow_id)}" ${state.open.has(r.flow_id)?'open':''}><summary class="result-summary"><span class="result-name">${esc(r.name)}</span><span class="result-meta">${pill(r.status)}<span class="muted">${(r.duration_ms/1000).toFixed(1)}s</span></span></summary><p>${esc(r.classification?.rationale || 'Awaiting classification')}</p><p>${esc(r.risk)} risk · ${esc(r.oracle)} expectation · ${esc(r.classification?.label||'pending')} ${r.classification?.confidence?`(${Math.round(r.classification.confidence*100)}% heuristic confidence)`:''}</p>${r.error?`<pre class="code">${esc(r.error)}</pre>`:''}${r.retry?`<p>Unchanged rerun: ${esc(r.retry.status)}. Original outcome retained.</p>`:''}${image?`<a class="evidence-link" href="${artifactUrl(image)}" target="_blank" rel="noopener">Open browser evidence ↗</a><img class="evidence-img" loading="lazy" src="${artifactUrl(image)}" alt="Browser evidence for ${esc(r.name)}">`:''}</details>`;
}
function renderDetail() {
  const r=state.detail;if(!r)return;
  $('run-detail').classList.remove('hidden');$('detail-id').textContent=`RUN ${r.id.slice(0,8).toUpperCase()} · ${r.status.toUpperCase()}`;
  $('detail-title').textContent=new URL(r.request.url).host;
  $('detail-subtitle').textContent=`${r.request.url} · ${r.request.mode==='openai'?'OpenAI planning':'Deterministic baseline'} · ${time(r.created)}`;
  $('download-run').href=`/api/runs/${r.id}/export`;$('cancel-run').classList.toggle('hidden',terminal(r.status));$('rerun').classList.toggle('hidden',!terminal(r.status));
  const stages=[['recon','Explore'],['plan','Planner'],['coverage','Coverage'],['generate','Generator'],['validate','Validate'],['execute','Execute'],['triage','Classifier'],['heal','Healer'],['report','Quality report']];
  const visited=new Set(r.events.map(e=>e.stage));
  $('pipeline').innerHTML=stages.map(([key,label],i)=>`<div class="pipeline-step ${r.stage===key?'current':visited.has(key)?'done':''}">${visited.has(key)&&r.stage!==key?'✓':`0${i+1}`} ${label}</div>`).join('');
  let runError=r.summary.error||'';
  if(r.summary.diagnostic)runError+=` ${r.summary.diagnostic.remedy}`;
  if(runError.includes('WinError 5') && state.config?.runtime?.ready && new Date(r.updated)<new Date(state.config.runtime.checked_at))runError+=' This is a historical failure. The current server has passed its browser readiness check; use Run again to retry.';
  showError('run-error',runError);
  let content='';
  if(state.tab==='results') {
    const s=r.summary,u=s.usage;
    content=`<div class="summary-line"><span><strong>${r.results.length}</strong> recorded scenarios</span>${s.total!==undefined?`<span><strong>${s.pass_rate}%</strong> pass rate</span><span><strong>${s.duration_seconds}s</strong> duration</span>`:''}${u?`<span><strong>${u.calls}</strong> OpenAI calls</span><span><strong>${u.input_tokens+u.output_tokens}</strong> tokens</span><span>Cost: <strong>${u.estimated_cost_usd===null?'not configured':`$${u.estimated_cost_usd.toFixed(4)}`}</strong></span>`:''}</div>`;
    if(r.evolution?.previous_run)content+=`<div class="gap-item">${r.evolution.reused.length} reused scenarios · ${r.evolution.added.length} additions · ${(r.evolution.outcomes||[]).filter(c=>c.change==='regression').length} regressions. See Changes & repairs.</div>`;
    content+=r.results.length?r.results.map(r=>resultHTML(r)+diagnosticHTML(r)).join(''):`<div class="detail-empty">${terminal(r.status)?'No execution results. Inspect the decision log and partial artifacts.':'Preparing browser evidence. Results appear as each scenario finishes.'}</div>`;
  } else if(state.tab==='plan') {
    content=r.plan?`<p class="muted">${esc(r.plan.summary)}</p>${r.plan.flows.map(f=>`<details class="result-item"><summary class="result-summary"><span class="result-name">${esc(f.name)}</span><span class="pill">${esc(f.category)}</span></summary><p>${esc(f.risk)} risk · ${esc(f.oracle)} oracle · Requirements: ${esc(f.requirement_ids.join(', ')||'none linked')}</p><ol class="flow-steps">${f.steps.map(s=>`<li><strong>${esc(s.action)}</strong> — ${esc(s.intent)}<pre class="code">${esc(s.target)}${s.value?` → ${esc(s.value)}`:''}</pre></li>`).join('')}</ol></details>`).join('')}`:'<div class="detail-empty">The planner has not produced a plan yet.</div>';
  } else if(state.tab==='activity') {
    content=r.events.map(e=>`<div class="log-row"><span class="log-time">${new Date(e.at).toLocaleTimeString()}</span><span class="log-stage">${esc(e.stage)}</span><span class="log-message">${esc(e.message)}</span></div>`).join('');
  } else if(state.tab==='coverage') {
    content=`<p class="muted">Passing tests do not prove full coverage. These gaps and requirement links describe the bounded scope of this run.</p>${r.gaps.map(g=>`<div class="gap-item">${esc(g)}</div>`).join('')}`;
    if(r.traceability.length) content+=`<h3>Requirements traceability</h3>${r.traceability.map(t=>`<div class="result-item"><strong>${esc(t.id)} — ${esc(t.text)}</strong><p>Planned: ${esc(t.flows.join(', ')||'none')} · Passing: ${esc(t.passing_flows.join(', ')||'none')}</p></div>`).join('')}`;
    if(r.heals.length) content+=`<h3>Repair audit</h3>${r.heals.map(h=>`<div class="result-item"><strong>${esc(h.flow_id)} · ${h.verified?'Verified':'Unverified'}</strong><p>${esc(h.rationale)}</p><pre class="code">${esc(h.old_selector)} → ${esc(h.new_selector||'no replacement')}</pre></div>`).join('')}`;
  } else if(state.tab==='defects') {content=renderDefects(r);
  } else if(state.tab==='evolution') {content=renderEvolution(r);
  } else {content=`<div class="artifact-grid">${r.artifacts.map(name=>`<a href="${artifactUrl(name)}" ${name.endsWith('.png')?'target="_blank" rel="noopener"':'download'}>↓ ${esc(name)}</a>`).join('')}</div>`;}
  $('detail-content').innerHTML=content;
  $('detail-content').querySelectorAll('details[data-flow]').forEach(d=>d.addEventListener('toggle',()=>{if(d.open)state.open.add(d.dataset.flow);else state.open.delete(d.dataset.flow);}));
}
async function selectRun(id,scroll=true) {
  state.selected=id;state.open.clear();state.detail=await api(`/runs/${id}`);renderDetail();
  if(scroll)$('run-detail').scrollIntoView({behavior:'smooth',block:'start'});
}
function renderConfig() {
  const c=state.config;
  $('provider-status').textContent=c.openai_configured?`● OpenAI configured · ${c.model}`:'○ OpenAI key needed · Baseline is available';
  if(!c.runtime?.ready)$('provider-status').textContent='Browser not ready - inspect Configuration before starting a run.';
  $('settings-content').innerHTML=`<div class="setting-row"><strong>OpenAI Responses API ${c.openai_configured?'· configured':'· needs a key'}</strong><p>Add OPENAI_API_KEY to .env, then restart the server. Keys stay on the backend.</p><code>OPENAI_MODEL=${esc(c.model)}</code></div><div class="setting-row"><strong>Allowed target origins</strong><p>${c.allow_all_origins?'Any HTTP(S) target is enabled.':'Only the configured target origins are enabled.'} Compatible loading supports external assets; navigation stays within the selected site and explicitly added origins.</p><pre class="code">${c.allow_all_origins?'QA_ALLOWED_ORIGINS=* - All target origins':esc(c.allowed_origins.join('\n'))}</pre></div><div class="setting-row"><strong>Authenticated sessions ${c.auth_configured?'· configured':'· not configured'}</strong><p>${esc(c.auth_origin||'Configure TARGET_AUTH_ORIGIN and a local login profile or storage-state file in .env.')}</p><p>Credentials and storage state are never sent to the planner. Run artifacts can contain application content; protect your data directory.</p></div><div class="setting-row"><strong>Execution limits</strong><p>One active run · 12 pages maximum · 12 scenarios maximum · 10-minute deadline · 5 OpenAI calls maximum (each may retry once).</p></div><div class="setting-row"><strong>Local operating boundary</strong><p>This is a single-user loopback application. SSO, distributed workers and remote hosting require the deployment work described in the implementation plan.</p></div>`;
  $('settings-content').insertAdjacentHTML('afterbegin', `<div class="setting-row"><strong>Runtime readiness - ${c.runtime?.ready?'ready':'action required'}</strong><p>${esc((c.runtime?.checks||[]).join(' / '))}</p>${(c.runtime?.errors||[]).map(e=>`<p>${esc(e.code)} at ${esc(e.stage)}: ${esc(e.message)}</p><p>${esc(e.remedy)}</p>`).join('')}<p>Checked: ${esc(c.runtime?.checked_at||'not yet checked')}. Startup verifies write access and a real browser launch.</p></div>`);
}
async function refresh() {
  if(state.busy)return;state.busy=true;
  try {
    state.runs=await api('/runs');renderRuns();
    if(state.selected && !document.querySelector('#detail-content :focus') && !window.getSelection()?.toString()) {
      const latest=await api(`/runs/${state.selected}`);
      if(!state.detail||latest.updated!==state.detail.updated||latest.events.length!==state.detail.events.length){state.detail=latest;renderDetail();}
    }
    $('connection-label').textContent='Connected';$('connection-dot').classList.remove('offline');
  } catch(e) {$('connection-label').textContent='Connection lost · retrying';$('connection-dot').classList.add('offline');}
  finally{state.busy=false;}
}
$('new-run').onclick=()=>openRun();$('empty-start').onclick=()=>openRun();$('try-demo').onclick=()=>openRun(true);
$('view-all-runs').onclick=()=>document.querySelector('[data-nav="runs"]').click();
$('run-form').addEventListener('invalid',e=>{if(e.target.closest('.advanced-options'))$('advanced-options').open=true;},true);
$('close-dialog').onclick=()=>$('run-dialog').close();$('run-search').oninput=renderRuns;
$('run-list').onclick=e=>{const b=e.target.closest('[data-run]');if(b)selectRun(b.dataset.run).catch(e=>toast(e.message));};
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{state.tab=b.dataset.tab;document.querySelectorAll('[data-tab]').forEach(t=>{t.classList.toggle('active',t===b);t.setAttribute('aria-selected',t===b);});renderDetail();});
document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>{
  state.nav=b.dataset.nav;document.querySelectorAll('[data-nav]').forEach(t=>t.classList.toggle('active',t===b));
  document.querySelectorAll('[data-nav]').forEach(t=>{if(t===b)t.setAttribute('aria-current','page');else t.removeAttribute('aria-current');});
  $('page-title').textContent={overview:'Quality, at a glance.',runs:'Test runs',reports:'Test Quality Reports',settings:'Configuration'}[state.nav];
  $('page-description').textContent={overview:'Track test runs, review outcomes, and find what needs attention.',runs:'Browse your run history and inspect the evidence.',reports:'Review completed runs and export their evidence.',settings:''}[state.nav];
  $('runs-heading').textContent={overview:'Recent runs',runs:'All runs',reports:'Completed runs',settings:'Recent runs'}[state.nav];
  $('runs-description').textContent=state.nav==='overview'?'The latest six runs. Select a target to inspect its results.':'Select a target to view results, plans, and browser evidence.';
  document.querySelector('.metrics').classList.toggle('hidden',state.nav!=='overview');
  $('breadcrumb').textContent={overview:'Overview',runs:'Test runs',reports:'Test Quality Reports',settings:'Configuration'}[state.nav];
  $('overview-page').classList.toggle('hidden',state.nav==='settings');$('settings-page').classList.toggle('hidden',state.nav!=='settings');renderRuns();
});
$('run-form').onsubmit=async e=>{
  e.preventDefault();$('launch-run').disabled=true;showError('form-error','');
  try{
    const run=await api('/runs',{method:'POST',body:JSON.stringify({url:$('target-url').value.trim(),mode:$('run-mode').value,scope:$('run-scope').value,requirements:state.legacyRequirements,prd_name:state.prd?.name||'',prd_content:state.prd?.content||'',max_pages:Number($('max-pages').value),max_flows:Number($('max-flows').value),allow_interactions:$('allow-interactions').checked,resource_policy:$('resource-policy').value,navigation_origins:state.navigationOrigins})});
    $('run-dialog').close();toast('Run started. Follow each decision below.');await refresh();await selectRun(run.id);
  }catch(error){showError('form-error',error.message);}finally{$('launch-run').disabled=false;}
};
$('cancel-run').onclick=async()=>{try{await api(`/runs/${state.selected}/cancel`,{method:'POST'});await refresh();toast('Run cancelled. Partial evidence retained.');}catch(e){toast(e.message);}};
$('rerun').onclick=()=>openRun(false,state.detail.request);
(async()=>{try{state.config=await api('/config');renderConfig();await refresh();const active=state.runs.find(r=>!terminal(r.status));if(active)await selectRun(active.id,false);}catch(e){toast(e.message);}setInterval(refresh,2000);})();

function renderPrd() {
  $('prd-status').textContent=state.prd?`${state.prd.name} · ${new TextEncoder().encode(state.prd.content).length.toLocaleString()} bytes`:'No PRD selected';
  $('clear-prd').classList.toggle('hidden',!state.prd);
}
$('prd-file').onchange=async()=>{
  const file=$('prd-file').files[0];state.prd=null;renderPrd();
  if(!file)return;
  $('launch-run').disabled=true;
  try{
    if(!/\.(md|markdown)$/i.test(file.name)||file.size>65536)throw new Error('Choose a Markdown document up to 64 KiB.');
    const content=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
    if(!content.trim()||content.includes('\0'))throw new Error('The PRD must contain readable UTF-8 Markdown.');
    state.prd={name:file.name,content};renderPrd();showError('form-error','');
  }catch(e){$('prd-file').value='';showError('form-error',e.message);}
  finally{$('launch-run').disabled=false;}
};
$('clear-prd').onclick=()=>{state.prd=null;$('prd-file').value='';renderPrd();};
function renderDefects(r) {
  const rows=r.defects||[];
  if(!rows.length)return '<div class="detail-empty">The Defect Classifier report appears after execution. Older runs retain classifications in Results.</div>';
  return `<p class="muted">Evidence-based triage distinguishes verified script repairs, suspected application defects, intermittent failures, and unresolved issues. Confidence is heuristic; suspected bugs need review.</p><a class="secondary" href="${artifactUrl('report.html')}" download>Download Test Quality Report</a>`+rows.map(d=>`<details class="result-item"><summary class="result-summary"><span class="result-name">${esc(d.name)}</span>${pill(d.classification.label||'needs_review')}</summary><p><strong>${esc(d.classification.issue_type)}</strong> · ${esc(d.risk)} risk · ${Math.round((d.classification.confidence||0)*100)}% heuristic confidence</p><p>${esc(d.classification.rationale)}</p><p><strong>Next action:</strong> ${esc(d.classification.next_action)}</p><p>PRD links: ${esc(d.requirement_ids.join(', ')||'No requirement linked')} · Oracle: ${esc(d.oracle)}</p><h3>Expected and actual</h3><pre class="code">${esc(d.expected?JSON.stringify(d.expected,null,2):'All configured assertions')}\n${esc(d.actual)}</pre><h3>Reproduction</h3><ol>${d.reproduction.map(s=>`<li>${esc(s.action)} · ${esc(s.intent)}<pre class="code">${esc(s.target)} ${esc(s.value)}</pre></li>`).join('')}</ol><h3>Attempts & evidence</h3>${d.attempts.map(a=>`<p>${esc(a.attempt)}: ${esc(a.status)} ${a.screenshot?`<a class="evidence-link" target="_blank" rel="noopener" href="${artifactUrl(a.screenshot)}">Screenshot ↗</a>`:''}</p>`).join('')}<h3>Healer decisions</h3>${d.repairs.length?d.repairs.map(h=>`<p>${esc(h.rationale)} · ${h.verified?'Verified':'Not verified'}</p><pre class="code">${esc(h.old_selector)} → ${esc(h.new_selector||'No safe replacement')}</pre>`).join(''):'<p>No locator repair applied.</p>'}</details>`).join('');
}
function renderEvolution(r) {
  const e=r.evolution;
  if(!e?.suite_key)return '<div class="detail-empty">Suite comparison becomes available during planning. Older runs can seed a new suite.</div>';
  return `<p class="muted">${e.previous_run?`Compared with run ${esc(e.previous_run.slice(0,8))}`:'First matching run: establishing a reusable suite.'} · ${e.reused.length} retained · ${e.added.length} new scenarios</p><h3>Scenario outcomes</h3>${(e.outcomes||[]).map(c=>`<div class="result-item"><strong>${esc(c.name)}</strong><p>${esc(c.change.replaceAll('_',' '))} · ${esc(c.previous||'Not previously tested')} → ${esc(c.current)}</p></div>`).join('')||'<p>Execution is in progress.</p>'}<h3>Observed UI changes</h3><p class="muted">Text and locator differences within the crawl scope; not pixel comparison or proof of a defect.</p>${e.ui_changes.map(c=>`<details class="result-item"><summary class="result-summary"><span class="result-name">${esc(c.kind.replaceAll('_',' '))} · ${esc(c.url)}</span></summary><pre class="code">${esc(JSON.stringify(c,null,2))}</pre></details>`).join('')||'<p>No differences recorded in the observed scope.</p>'}${e.deferred.length?`<h3>Deferred by scenario budget</h3><p>${esc(e.deferred.join(', '))}</p>`:''}`;
}
