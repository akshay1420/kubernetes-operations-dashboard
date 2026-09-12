/* Application view is optional: failures here must never prevent core dashboard startup. */
(function () {
  function tab(name) {
    document.querySelectorAll('.tabs button').forEach(function (button) {
      button.classList.toggle('active', button.dataset.tab === name);
    });
    document.querySelectorAll('.panel').forEach(function (panel) {
      panel.classList.toggle('hidden', panel.id !== name);
    });
  }

  function ready(workload) {
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

  function appRows(workloads) {
    return workloads.map(function (workload) {
      var kind = String(workload.kind || '').toLowerCase();
      return '<tr data-app-kind="' + esc(kind) + '" data-app-name="' + esc(workload.metadata.name) + '">' +
        '<td>' + esc(workload.kind) + '</td><td><b>' + esc(workload.metadata.name) + '</b></td><td>' + esc(ready(workload)) + '</td>' +
        '<td><button class="open-application" data-app-kind="' + esc(kind) + '" data-app-name="' + esc(workload.metadata.name) + '">Open map</button></td></tr>';
    }).join('');
  }

  async function openApplication(kind, name) {
    var panel = $('#applications');
    panel.innerHTML = '<h2>Application map <small>' + esc(ns()) + '</small></h2><p class="muted">Loading live application relationships…</p>';
    try {
      var data = await api('/api/workload-context?namespace=' + encodeURIComponent(ns()) + '&kind=' + encodeURIComponent(kind) + '&name=' + encodeURIComponent(name));
      var workload = data.workload || {}, pods = data.pods || [], services = data.services || [], hpas = data.hpas || [];
      var state = rollout(workload);
      var podNames = pods.map(function (pod) { return esc(pod.metadata.name) + ' <small>' + esc(phase(pod)) + '</small>'; }).join('<br>') || 'No selector-matched Pods';
      var serviceNames = services.map(function (service) { return esc(service.name) + ' <small>' + esc(service.readyEndpoints) + '/' + esc(service.endpointCount) + ' endpoints</small>'; }).join('<br>') || 'No matching Service';
      var routeNames = services.reduce(function (all, service) { return all.concat(service.routes || []); }, []).map(function (route) { return esc((route.host || '*') + (route.path || '/')); }).join('<br>') || 'No Ingress route';
      var hpaNames = hpas.map(function (hpa) { var spec = hpa.spec || {}; return esc(hpa.metadata.name) + ' <small>' + esc(spec.minReplicas == null ? 1 : spec.minReplicas) + '–' + esc(spec.maxReplicas || '—') + '</small>'; }).join('<br>') || 'No HPA';
      panel.innerHTML = '<div class="app-title"><div><h2>Application map · ' + esc(kind) + '/' + esc(name) + '</h2><p class="muted">Relationships are resolved live from selectors, Services, EndpointSlices, HPA targets, and Ingress backends.</p></div><button id="downloadDiagnostics" class="primary">Download diagnostics</button></div>' +
        '<div class="app-map">' +
          '<section><span class="map-label">WORKLOAD</span><b>' + esc(kind) + '/' + esc(name) + '</b><small>Ready ' + esc(ready(workload)) + '</small></section><i>→</i>' +
          '<section><span class="map-label">PODS</span><div>' + podNames + '</div></section><i>→</i>' +
          '<section><span class="map-label">SERVICE / ENDPOINTS</span><div>' + serviceNames + '</div></section><i>→</i>' +
          '<section><span class="map-label">INGRESS</span><div>' + routeNames + '</div></section>' +
        '</div>' +
        '<div class="app-grid"><section><h3>Rollout status</h3><table><tbody>' +
          '<tr><td>Desired</td><td><b>' + esc(state.desired) + '</b></td></tr><tr><td>Updated</td><td>' + esc(state.updated) + '</td></tr><tr><td>Available</td><td>' + esc(state.available) + '</td></tr><tr><td>Revision</td><td>' + esc(state.revision) + '</td></tr><tr><td>Generation observed</td><td>' + esc(state.observed) + '/' + esc(state.generation) + '</td></tr><tr><td colspan="2"><small>' + esc(state.conditions) + '</small></td></tr>' +
          '</tbody></table></section><section><h3>Autoscaling</h3><p>' + hpaNames + '</p><h3>Mapped Pods</h3><p>' + podNames + '</p></section></div>';
      $('#downloadDiagnostics').onclick = function () {
        var query = new URLSearchParams({ namespace: ns(), kind: kind, name: name });
        window.location.assign('/api/workload-diagnostics?' + query.toString());
      };
    } catch (error) {
      panel.innerHTML = '<h2>Application map</h2><p class="error">' + esc(error.message) + '</p>';
    }
  }

  async function loadApplications() {
    var panel = $('#applications');
    panel.innerHTML = '<h2>Applications <small>' + esc(ns()) + '</small></h2><p class="muted">Loading workloads…</p>';
    try {
      var data = await api('/api/workloads?namespace=' + encodeURIComponent(ns()));
      panel.innerHTML = '<h2>Applications <small>' + esc(ns()) + '</small></h2><p class="muted">Open a workload to view its live relationship map, rollout status, and downloadable diagnostics bundle.</p><table><thead><tr><th>Kind</th><th>Name</th><th>Ready</th><th></th></tr></thead><tbody>' + (appRows(data.items || []) || '<tr><td colspan="4">No workloads found.</td></tr>') + '</tbody></table>';
      panel.querySelectorAll('.open-application').forEach(function (button) {
        button.onclick = function () { openApplication(button.dataset.appKind, button.dataset.appName); };
      });
    } catch (error) {
      panel.innerHTML = '<h2>Applications</h2><p class="error">' + esc(error.message) + '</p>';
    }
  }

  document.querySelector('[data-tab="applications"]').onclick = function () { tab('applications'); loadApplications(); };
  document.head.insertAdjacentHTML('beforeend', '<style>.app-title{display:flex;justify-content:space-between;gap:16px;align-items:start}.app-map{display:flex;align-items:stretch;gap:10px;margin:18px 0;overflow:auto}.app-map section{min-width:175px;flex:1;background:#142542;border:1px solid #2c4d74;border-radius:9px;padding:14px}.app-map section b,.app-map section small{display:block;margin-top:7px}.app-map i{align-self:center;color:#5ce0c6;font-size:24px;font-style:normal}.map-label{font-size:10px;letter-spacing:.12em;color:#8eb5de}.app-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.app-grid section{background:#142542;border:1px solid #2c4d74;border-radius:9px;padding:14px}.app-grid h3{margin:0 0 10px}@media(max-width:900px){.app-map{flex-direction:column}.app-map i{transform:rotate(90deg)}.app-grid{grid-template-columns:1fr}.app-title{flex-direction:column}}</style>');
}());
