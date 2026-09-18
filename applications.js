/* Application view is optional: failures here must never prevent core dashboard startup. */
(function () {
  var currentApplication=null;
  function tab(name) {
    document.querySelectorAll('.tabs button').forEach(function (button) {
      button.classList.toggle('active', button.dataset.tab === name);
    });
    document.querySelectorAll('.panel').forEach(function (panel) {
      panel.classList.toggle('hidden', panel.id !== name);
    });
  }

  function ready(workload) {
    if (workload.kind === 'CronJob') return workload.spec.suspend ? 'Suspended' : 'Scheduled';
    if (workload.kind === 'Domain') return 'See mapped Pods';
    var status = workload.status || {}, spec = workload.spec || {};
    return (status.readyReplicas == null ? status.numberReady || 0 : status.readyReplicas) + '/' +
      (spec.replicas == null ? status.currentNumberScheduled || 0 : spec.replicas);
  }

  function phase(pod) { return (pod.status || {}).phase || 'Unknown'; }

  function rollout(workload) {
    var status = workload.status || {}, metadata = workload.metadata || {};
    var desired = (workload.spec || {}).replicas;
    if (desired == null) desired = status.desiredNumberScheduled == null ? 0 : status.desiredNumberScheduled;
    var updated = status.updatedReplicas == null ? status.updatedNumberScheduled : status.updatedReplicas;
    var available = status.availableReplicas == null ? status.numberAvailable : status.availableReplicas;
    var conditions = (status.conditions || []).map(function (condition) {
      return condition.type + ': ' + condition.status + (condition.reason ? ' (' + condition.reason + ')' : '');
    });
    return {
      desired: desired,
      updated: updated == null ? '—' : updated,
      available: available == null ? '—' : available,
      generation: metadata.generation || '—',
      observed: status.observedGeneration == null ? '—' : status.observedGeneration,
      revision: (metadata.annotations || {})['deployment.kubernetes.io/revision'] || '—',
      conditions: conditions.join(' · ') || 'No rollout conditions reported.'
    };
  }

  function appHealthy(workload) {
    if (workload.kind === 'CronJob') return true;
    if (workload.kind === 'Domain') return null;
    var status=workload.status||{}, spec=workload.spec||{}, desired=spec.replicas;
    if(desired==null)desired=status.desiredNumberScheduled||0;
    var available=status.availableReplicas==null?status.numberAvailable:status.availableReplicas;
    return Number(available||0)>=Number(desired||0);
  }

  function appRows(workloads, changed) {
    return workloads.map(function (workload) {
      var kind = String(workload.kind || '').toLowerCase();
      var resource=(workload.kind+'/'+workload.metadata.name).toLowerCase(), hasChanged=changed.has(resource), healthy=appHealthy(workload);
      var status=healthy==null?'Mapped Pods':healthy?'Healthy':'Needs attention';
      return '<tr class="'+(hasChanged?'application-changed':'')+'" data-app-kind="' + esc(kind) + '" data-app-name="' + esc(workload.metadata.name) + '">' +
        '<td>' + esc(workload.kind) + '</td><td><b>' + esc(workload.metadata.name) + '</b>'+(hasChanged?'<span class="recent-badge">Changed</span>':'')+'</td><td><span class="status-pill '+(healthy===false?'status-attention':healthy===true?'status-healthy':'')+'">'+esc(status)+'</span><small class="ready-count">'+esc(ready(workload))+'</small></td>' +
        '<td><button class="open-application" data-app-kind="' + esc(kind) + '" data-app-name="' + esc(workload.metadata.name) + '">View application</button></td></tr>';
    }).join('');
  }

  async function openApplication(kind, name) {
    currentApplication={kind:kind,name:name};
    var selectedNamespace=ns();
    var panel = $('#applications');
    panel.innerHTML = '<h2>Application map <small>' + esc(ns()) + '</small></h2><p class="muted">Loading live application relationships…</p>';
    try {
      var data = await api('/api/workload-context?namespace=' + encodeURIComponent(ns()) + '&kind=' + encodeURIComponent(kind) + '&name=' + encodeURIComponent(name));
      if(ns()!==selectedNamespace)return;
      var workload = data.workload || {}, replicaSets=data.replicaSets||[], pods = data.pods || [], services = data.services || [], hpas = data.hpas || [];
      var changeQuery=new URLSearchParams({namespace:selectedNamespace,kind:'changes',days:'1'});(data.relatedResources||[]).forEach(function(resource){changeQuery.append('resource',resource)});
      var recentChanges=await api('/api/history?'+changeQuery).catch(function(){return {items:[]}});
      var changed=new Set((recentChanges.items||[]).map(function(item){return String(item.resource).toLowerCase()}));
      function changedClass(resource){return changed.has(String(resource).toLowerCase())?' app-map-changed':''}
      var state = rollout(workload);
      var replicaSetNames=replicaSets.map(function(item){return esc(item.metadata.name)+' <small>'+esc(ready(item))+'</small>'}).join('<br>')||'No ReplicaSet layer';
      var podNames = pods.map(function (pod) { return esc(pod.metadata.name) + ' <small>' + esc(phase(pod)) + '</small>'; }).join('<br>') || 'No selector-matched Pods';
      var serviceNames = services.map(function (service) { return esc(service.name) + ' <small>' + esc(service.readyEndpoints) + '/' + esc(service.endpointCount) + ' endpoints</small>'; }).join('<br>') || 'No matching Service';
      var routeNames = services.reduce(function (all, service) { return all.concat(service.routes || []); }, []).map(function (route) { return esc((route.host || '*') + (route.path || '/')); }).join('<br>') || 'No Ingress route';
      var hpaNames = hpas.map(function (hpa) { var spec = hpa.spec || {}; return esc(hpa.metadata.name) + ' <small>' + esc(spec.minReplicas == null ? 1 : spec.minReplicas) + '–' + esc(spec.maxReplicas || '—') + '</small>'; }).join('<br>') || 'No HPA';
      panel.innerHTML = '<div class="app-title"><div><h2>Application map · ' + esc(kind) + '/' + esc(name) + '</h2><p class="muted">Relationships are resolved live from selectors, Services, EndpointSlices, HPA targets, and Ingress backends.</p></div><button id="downloadDiagnostics" class="primary">Download diagnostics</button></div>' +
        '<div class="app-map">' +
          '<section class="'+changedClass(workload.kind+'/'+name)+'"><span class="map-label">WORKLOAD</span><b>' + esc(kind) + '/' + esc(name) + '</b><small>Ready ' + esc(ready(workload)) + '</small></section>'+(replicaSets.length?'<i>→</i><section class="'+(replicaSets.some(function(item){return changed.has(('replicaset/'+item.metadata.name).toLowerCase())})?'app-map-changed':'')+'"><span class="map-label">REPLICA SETS</span><div>'+replicaSetNames+'</div></section>':'')+'<i>→</i>' +
          '<section class="'+(pods.some(function(item){return changed.has(('pod/'+item.metadata.name).toLowerCase())})?'app-map-changed':'')+'"><span class="map-label">PODS</span><div>' + podNames + '</div></section><i>→</i>' +
          '<section class="'+(services.some(function(item){return changed.has(('service/'+item.name).toLowerCase())})?'app-map-changed':'')+'"><span class="map-label">SERVICE / ENDPOINTS</span><div>' + serviceNames + '</div></section><i>→</i>' +
          '<section><span class="map-label">INGRESS</span><div>' + routeNames + '</div></section>' +
        '</div>' +
        '<div class="app-grid"><section><h3>Rollout status</h3><table><tbody>' +
          '<tr><td>Desired</td><td><b>' + esc(state.desired) + '</b></td></tr><tr><td>Updated</td><td>' + esc(state.updated) + '</td></tr><tr><td>Available</td><td>' + esc(state.available) + '</td></tr><tr><td>Revision</td><td>' + esc(state.revision) + '</td></tr><tr><td>Generation observed</td><td>' + esc(state.observed) + '/' + esc(state.generation) + '</td></tr><tr><td colspan="2"><small>' + esc(state.conditions) + '</small></td></tr>' +
          '</tbody></table></section><section><h3>Autoscaling</h3><p>' + hpaNames + '</p><h3>Mapped Pods</h3><p>' + podNames + '</p></section></div>';
      $('#downloadDiagnostics').onclick = function () {
        var query = new URLSearchParams({ namespace: ns(), kind: kind, name: name });
        window.location.assign('/api/workload-diagnostics?' + query.toString());
      };
      if (kind === 'domain' || kind === 'cronjob') {
        $('#downloadDiagnostics').remove();
        panel.querySelector('.app-grid section').innerHTML = '<h3>Workload status</h3><p>' + esc(ready(workload)) + '</p><p class="muted">Pod phases are shown in the topology. Deployment rollout counters do not apply to this kind.</p>';
      }
      const navigation=document.createElement('div');navigation.className='tools';
      const back=document.createElement('button');back.textContent='← Applications';back.onclick=loadApplications;
      const recent=document.createElement('button');recent.textContent='Recent changes';recent.onclick=()=>window.openApplicationChanges(data.relatedResources || [kind+'/'+name]);
      const logs=document.createElement('button');logs.textContent='Saved application logs';logs.onclick=()=>window.dispatchEvent(new CustomEvent('show-saved-logs',{detail:{application:name}}));
      navigation.append(back,recent,logs);panel.prepend(navigation);
      const storage=document.createElement('p');storage.textContent='Referenced PVCs: '+((data.pvcs||[]).join(', ')||'None');panel.append(storage);
      const note=document.createElement('p');note.className='muted';note.textContent='Recent changes includes this application and its currently mapped resources. Removed relationships remain available in All namespace changes.';panel.append(note);
      (data.warnings||[]).forEach(function(message){var warning=document.createElement('p');warning.className='error';warning.textContent=message;panel.prepend(warning)});
      if(changed.size){const alert=document.createElement('p');alert.className='app-change-note';alert.textContent=changed.size+' related resource(s) changed in the last 24 hours. Highlighted topology cards contain recent changes.';panel.prepend(alert)}
    } catch (error) {
      panel.innerHTML = '<h2>Application map</h2><p class="error">' + esc(error.message) + '</p>';
    }
  }

  async function loadApplications() {
    currentApplication=null;
    var selectedNamespace=ns();
    var panel = $('#applications');
    panel.innerHTML = '<h2>Applications <small>' + esc(ns()) + '</small></h2><p class="muted">Loading workloads…</p>';
    try {
      var data = await api('/api/applications?namespace=' + encodeURIComponent(ns()));
      if(ns()!==selectedNamespace)return;
      var changeData=await api('/api/history?'+new URLSearchParams({namespace:selectedNamespace,kind:'changes',days:'1'})).catch(function(){return {items:[]}});
      var changed=new Set((changeData.items||[]).map(function(item){return String(item.resource||'').toLowerCase()}));
      var items=data.items||[], attention=items.filter(function(item){return appHealthy(item)===false}).length;
      var changedApps=items.filter(function(item){return changed.has((item.kind+'/'+item.metadata.name).toLowerCase())}).length;
      panel.innerHTML = '<div class="app-list-title"><div><h2>Applications <small>' + esc(ns()) + '</small></h2><p class="muted">Open a workload to view its live relationship map, rollout status, recent changes, and diagnostics.</p></div><button id="namespaceChanges">Recent changes</button></div>'+
        '<div class="application-summary"><section><b>'+items.length+'</b><span>Applications</span></section><section class="'+(attention?'summary-attention':'')+'"><b>'+attention+'</b><span>Need attention</span></section><section class="'+(changedApps?'summary-changed':'')+'"><b>'+changedApps+'</b><span>Changed in 24h</span></section><label>Find application<input id="applicationSearch" placeholder="Name or kind…"></label></div>'+
        '<table id="applicationTable"><thead><tr><th>Kind</th><th>Name</th><th>Status</th><th></th></tr></thead><tbody>' + (appRows(items,changed) || '<tr><td colspan="4">No workloads found.</td></tr>') + '</tbody></table>';
      panel.querySelectorAll('.open-application').forEach(function (button) {
        button.onclick = function () { openApplication(button.dataset.appKind, button.dataset.appName); };
      });
      $('#namespaceChanges').onclick=()=>window.openApplicationChanges(null);
      $('#applicationSearch').oninput=function(){var query=this.value.trim().toLowerCase();panel.querySelectorAll('#applicationTable tbody tr[data-app-name]').forEach(function(row){row.hidden=!(row.dataset.appName+' '+row.dataset.appKind).toLowerCase().includes(query)})};
      (data.warnings||[]).forEach(message=>{const warning=document.createElement('p');warning.className='error';warning.textContent=message;panel.append(warning)});
    } catch (error) {
      panel.innerHTML = '<h2>Applications</h2><p class="error">' + esc(error.message) + '</p>';
    }
  }

  document.querySelector('[data-tab="applications"]').onclick = function () { tab('applications'); loadApplications(); };
  $('#namespace').addEventListener('change',()=>{if(!$('#applications').classList.contains('hidden'))loadApplications()});
  document.addEventListener('click',event=>{if(event.target.closest('[data-ns]')&&!$('#applications').classList.contains('hidden'))loadApplications()});
  document.addEventListener('dashboard-resource-change',()=>{if($('#applications').classList.contains('hidden'))return;if(currentApplication)openApplication(currentApplication.kind,currentApplication.name);else loadApplications()});
  document.head.insertAdjacentHTML('beforeend', '<style>.app-title{display:flex;justify-content:space-between;gap:16px;align-items:start}.app-list-title{display:flex;justify-content:space-between;gap:16px;align-items:start;margin-bottom:16px}.app-list-title h2,.app-list-title p{margin-top:0}.application-summary{display:grid;grid-template-columns:repeat(3,minmax(130px,1fr)) minmax(240px,2fr);gap:12px;margin:0 0 16px}.application-summary section,.application-summary label{background:#142542;border:1px solid #2c4d74;border-radius:10px;padding:13px}.application-summary section{display:flex;flex-direction:column}.application-summary b{font-size:24px;color:#5ce0c6}.application-summary span{font-size:12px;color:#9ec7f1;margin-top:3px}.application-summary .summary-attention b{color:#ffb84d}.application-summary .summary-changed b{color:#70aaff}.application-summary input{margin-top:6px}.status-pill,.recent-badge{display:inline-block;border-radius:999px;padding:3px 8px;font-size:11px;background:#243b5b;color:#b9d7f7}.status-pill.status-healthy{background:#123d3a;color:#69ebd4}.status-pill.status-attention{background:#49351d;color:#ffd080}.recent-badge{margin-left:8px;background:#183f68;color:#8fc7ff}.ready-count{display:block;color:#8eb5de;margin-top:5px}.application-changed td:first-child{box-shadow:inset 3px 0 #70aaff}.app-map{display:flex;align-items:stretch;gap:10px;margin:18px 0;overflow:auto}.app-map section{min-width:175px;flex:1;background:#142542;border:1px solid #2c4d74;border-radius:9px;padding:14px}.app-map section b,.app-map section small{display:block;margin-top:7px}.app-map i{align-self:center;color:#5ce0c6;font-size:24px;font-style:normal}.map-label{font-size:10px;letter-spacing:.12em;color:#8eb5de}.app-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.app-grid section{background:#142542;border:1px solid #2c4d74;border-radius:9px;padding:14px}.app-grid h3{margin:0 0 10px}@media(max-width:900px){.application-summary{grid-template-columns:1fr 1fr}.app-map{flex-direction:column}.app-map i{transform:rotate(90deg)}.app-grid{grid-template-columns:1fr}.app-title,.app-list-title{flex-direction:column}}@media(max-width:600px){.application-summary{grid-template-columns:1fr}}</style>');
}());
