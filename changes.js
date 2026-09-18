(function () {
  'use strict';
  let resourceScope=null;
  const panel=document.createElement('div');panel.id='changes';panel.className='panel hidden';document.querySelector('.content').appendChild(panel);
  panel.innerHTML='<div class="history-heading"><div><span class="eyebrow">CONFIGURATION & ACTIONS</span><h2>What changed recently?</h2><p class="muted">Compare observed configuration changes and dashboard actions.</p></div></div><div class="tools"><label>Period<select id="changeDays"><option value="1">Last 24 hours</option><option value="2">Last 48 hours</option><option value="7" selected>Last 7 days</option><option value="30">Last 30 days</option><option value="custom">Custom date & time</option></select></label><label class="change-custom hidden">From<input id="changeFrom" type="datetime-local"></label><label class="change-custom hidden">To<input id="changeTo" type="datetime-local"></label><label>Source<select id="changeSource"><option value="all">All changes</option><option value="observed">Observed configuration</option><option value="dashboard">Dashboard actions</option></select></label><label>Search<input id="changeSearch" placeholder="Resource name or dashboard user"></label><button id="changeRefresh">Apply filters</button></div><p id="changeStatus" role="status"></p><div id="changeResults"></div>';
  let request=0, rows=[];
  const issues=document.createElement('div');issues.id='changeIssues';$('#changeStatus').after(issues);
  function showIssues(errors){
    if(!errors.length){issues.replaceChildren();return;}
    const full=errors.filter(e=>e.includes('History storage budget reached'));
    const other=[...new Set(errors.filter(e=>!e.includes('History storage budget reached')))];
    let html='';
    if(full.length){const affected=[...new Set(full.map(e=>e.split(': logs:')[0]))];html='<div class="change-warning" role="status"><strong>History storage budget reached</strong><p>New history records cannot be saved. Existing records remain available. Increase history.maxBytes after checking available PVC space.</p><details><summary>Show affected collectors ('+affected.length+')</summary><ul>'+affected.map(e=>'<li>'+esc(e)+'</li>').join('')+'</ul></details></div>';}
    if(other.length)html+='<details class="change-warning"><summary>'+other.length+' other collection issue(s)</summary><ul>'+other.map(e=>'<li>'+esc(e)+'</li>').join('')+'</ul></details>';
    issues.innerHTML=html;
  }
  function format(value){return value==null?'Not available':JSON.stringify(value,null,2);}
  function differences(before,after,path=''){
    if(JSON.stringify(before)===JSON.stringify(after))return [];
    if(before&&after&&typeof before==='object'&&typeof after==='object')return [...new Set([...Object.keys(before),...Object.keys(after)])].flatMap(key=>differences(before[key],after[key],path?path+'.'+key:key));
    return [{path:path||'Resource',before,after}];
  }
  function highlight(){
    $('#changeResults').querySelectorAll('details.insight').forEach((card,index)=>{
      const source=$('#changeSource').value;
      const records=rows.filter(r=>(source==='all'||r.source===source)&&(!resourceScope||resourceScope.has(String(r.resource).toLowerCase())));
      const row=records[index];
      const label=document.createElement('p');label.className='muted';label.textContent='Namespace: '+(row.namespace||ns());card.querySelector('summary').append(label);
      const delta=differences(row.before,row.after);
      const box=document.createElement('div');box.className='change-field-summary';
      box.innerHTML='<h3>Changed fields</h3>'+ (delta.length?'<table><thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead><tbody>'+delta.map(d=>'<tr><td>'+esc(d.path)+'</td><td style="background:#422b31"><pre>'+esc(format(d.before))+'</pre></td><td style="background:#173e38"><pre>'+esc(format(d.after))+'</pre></td></tr>').join('')+'</tbody></table>':'<p>No configuration difference recorded for this action.</p>');
      card.insertBefore(box,card.querySelector('.change-diff'));
      const badge=document.createElement('span');badge.style.color='#ffd27a';badge.textContent=' · '+delta.length+' changed field(s)';card.querySelector('summary').append(badge);
    });
  }
  new MutationObserver(()=>{if($('#changeResults details.insight')&&!$('#changeResults .change-field-summary'))highlight()}).observe($('#changeResults'),{childList:true});
  function render(){const source=$('#changeSource').value;const filtered=rows.filter(r=>(source==='all'||r.source===source)&&(!resourceScope||resourceScope.has(String(r.resource).toLowerCase())));
    $('#changeResults').innerHTML=filtered.length?filtered.map(r=>'<details class="insight"><summary><strong>'+esc(r.resource)+'</strong> · '+esc(r.action)+' · '+esc(r.status)+(r.occurrenceCount>1?' · '+esc(r.occurrenceCount)+' observations':'')+'<br><small>'+esc(r.source==='observed'?'Latest observed at ':'Performed/attempted at ')+esc(new Date(r.ts*1000).toLocaleString())+' · '+esc(r.source==='observed'?'Actor unknown (snapshot comparison)':r.actor==='local'?'Local mode (no authenticated user)':r.actor)+'</small></summary>'+(r.occurrenceCount>1?'<p class="muted">Consolidated '+esc(r.occurrenceCount)+' observations for this resource from '+esc(new Date(r.firstTs*1000).toLocaleString())+' to '+esc(new Date(r.ts*1000).toLocaleString())+'. The difference below is the latest observation.</p>':'')+(r.previousObserved?'<p class="muted">Previous observation: '+esc(new Date(r.previousObserved*1000).toLocaleString())+'. Intermediate changes may not have been captured.</p>':'')+'<div class="change-diff"><section><h3>Before</h3><pre>'+esc(format(r.before))+'</pre></section><section><h3>After</h3><pre>'+esc(format(r.after))+'</pre></section></div></details>').join(''):'<div class="history-empty"><h3>No changes in this selection</h3><p>The first successful collection establishes a baseline. Subsequent cycles show differences. This view does not reconstruct changes from before collection began.</p></div>';
  }
  function rangeQuery(query){const period=$('#changeDays').value;if(period!=='custom'){query.set('days',period);return}const from=$('#changeFrom').value,to=$('#changeTo').value;if(!from||!to)throw Error('Select both From and To date/time.');const start=new Date(from).getTime()/1000,end=new Date(to).getTime()/1000;if(!Number.isFinite(start)||!Number.isFinite(end)||start>=end)throw Error('From must be earlier than To.');query.set('days','30');query.set('start',start);query.set('end',end)}
  async function load(){const id=++request,namespace=ns();rows=[];showIssues([]);$('#changeResults').textContent='';$('#changeStatus').textContent='Loading changes…';try{const query=new URLSearchParams({namespace,kind:'changes',search:$('#changeSearch').value});rangeQuery(query);if(resourceScope)resourceScope.forEach(resource=>query.append('resource',resource));const data=await api('/api/history?'+query);if(id!==request||namespace!==ns())return;rows=data.items;const range=new Date(data.rangeStart*1000).toLocaleString()+' – '+new Date(data.rangeEnd*1000).toLocaleString();$('#changeStatus').textContent=(data.baselineExists?'Configuration baseline available':'Waiting for configuration baseline')+' · Showing '+range+' · '+data.retentionDays+' day retention'+(data.truncated?' · Results limited: narrow your search.':'');showIssues(data.errors||[]);render();}catch(e){if(id===request)$('#changeStatus').textContent=e.message}}
  window.openApplicationChanges=(resources)=>{resourceScope=resources?new Set(resources.map(r=>r.toLowerCase())):null;document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('hidden',p!==panel));document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab==='applications'));panel.querySelector('h2').textContent=(resources?'Application changes in ':'Changes in ')+ns();load()};
  const back=document.createElement('button');back.textContent='← Back to Applications';back.onclick=()=>document.querySelector('[data-tab="applications"]').click();panel.prepend(back);
  $('#changeRefresh').onclick=load;$('#changeDays').onchange=()=>{const custom=$('#changeDays').value==='custom';document.querySelectorAll('.change-custom').forEach(x=>x.classList.toggle('hidden',!custom));if(!custom)load()};$('#changeSource').onchange=render;$('#changeSearch').onchange=load;
  $('#namespace').addEventListener('change',()=>{if(!panel.classList.contains('hidden'))window.openApplicationChanges(null)});
  document.addEventListener('click',e=>{if(e.target.closest('[data-ns]')&&!panel.classList.contains('hidden'))window.openApplicationChanges(null)});
  document.addEventListener('dashboard-resource-change',()=>{if(!panel.classList.contains('hidden'))load()});
}());
