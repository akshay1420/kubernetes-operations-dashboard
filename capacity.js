/* Namespace capacity view: read-only sizing data, isolated from core startup. */
(function () {
  var latest = [], metricsEnabled = false;

  function csvCell(value) { return '"' + String(value == null ? '' : value).replace(/"/g, '""') + '"'; }
  function isMissing(value) { return !value || value === '—'; }
  function cpuMilli(value) {
    if (isMissing(value)) return 0;
    var number = parseFloat(value), unit = String(value).replace(/[0-9.]/g, '').toLowerCase();
    if (isNaN(number)) return 0;
    return unit === 'm' ? number : number * 1000;
  }
  function memoryMi(value) {
    if (isMissing(value)) return 0;
    var number = parseFloat(value), unit = String(value).replace(/[0-9.]/g, '').toLowerCase();
    if (isNaN(number)) return 0;
    if (unit === 'gi' || unit === 'g') return number * 1024;
    if (unit === 'ki' || unit === 'k') return number / 1024;
    if (unit === 'mi' || unit === 'm' || unit === '') return number;
    return number;
  }
  function visibleRows() {
    var select = $('#capacityFilter'), policy = $('#capacityPolicy'), podName = $('#capacityPodName');
    if (!select || !policy || !podName) return latest;
    return latest.filter(function (item) {
      var typeOk = select.value === 'all' || (select.value === 'main' && item.containerType === 'App') || (select.value === 'init' && item.containerType === 'Init');
      var policyOk = policy.value === 'all' || (policy.value === 'missing-limit' && (isMissing(item.cpuLimit) || isMissing(item.memoryLimit))) || (policy.value === 'missing-request' && (isMissing(item.cpuRequest) || isMissing(item.memoryRequest)));
      return typeOk && policyOk && item.pod.toLowerCase().indexOf(podName.value.trim().toLowerCase()) >= 0;
    });
  }
  function display(value, inherited) { return esc(value) + (inherited ? '<small class="inherited" title="Inherited from the namespace LimitRange default"> †</small>' : ''); }
  function sums(rows) {
    return {
      cpuRequest: rows.reduce(function (n, item) { return n + cpuMilli(item.cpuRequest); }, 0),
      cpuLimit: rows.reduce(function (n, item) { return n + cpuMilli(item.cpuLimit); }, 0),
      cpuUsage: rows.reduce(function (n, item) { return n + cpuMilli(item.cpuUsage); }, 0),
      memoryRequest: rows.reduce(function (n, item) { return n + memoryMi(item.memoryRequest); }, 0),
      memoryLimit: rows.reduce(function (n, item) { return n + memoryMi(item.memoryLimit); }, 0),
      memoryUsage: rows.reduce(function (n, item) { return n + memoryMi(item.memoryUsage); }, 0)
    };
  }
  function renderRows() {
    var rows = visibleRows(), body = $('#capacityRows'), footer = $('#capacityTotals'), count = $('#capacityCount'), total = sums(rows);
    if (!body) return;
    body.innerHTML = rows.map(function (item) {
      var missing = isMissing(item.cpuLimit) || isMissing(item.memoryLimit);
      return '<tr class="' + (missing ? 'capacity-missing' : '') + '"><td><b>' + esc(item.pod) + '</b></td><td>' + esc(item.container) + '</td><td>' + esc(item.containerType) + '</td><td>' + esc(item.phase) + '</td><td>' + display(item.cpuRequest, item.cpuRequestDefaulted) + '</td><td>' + display(item.cpuLimit, item.cpuLimitDefaulted) + '</td><td>' + esc(item.cpuUsage) + '</td><td>' + display(item.memoryRequest, item.memoryRequestDefaulted) + '</td><td>' + display(item.memoryLimit, item.memoryLimitDefaulted) + '</td><td>' + esc(item.memoryUsage) + '</td><td><small>' + esc(item.workload) + '</small><br><b>' + esc(item.replicas) + '</b></td></tr>';
    }).join('') || '<tr><td colspan="11">No containers match this filter.</td></tr>';
    footer.innerHTML = '<tr><td colspan="4"><b>Total (shown)</b></td><td><b>' + Math.round(total.cpuRequest) + 'm</b></td><td><b>' + Math.round(total.cpuLimit) + 'm</b></td><td><b>' + (metricsEnabled ? Math.round(total.cpuUsage) + 'm' : '—') + '</b></td><td><b>' + Math.round(total.memoryRequest) + 'Mi</b></td><td><b>' + Math.round(total.memoryLimit) + 'Mi</b></td><td><b>' + (metricsEnabled ? Math.round(total.memoryUsage) + 'Mi' : '—') + '</b></td><td>—</td></tr>';
    count.textContent = rows.length + ' container rows';
  }
  function download() {
    var rows = visibleRows(), headers = ['Namespace', 'Pod', 'Container', 'Container type', 'Phase', 'CPU request', 'CPU request source', 'CPU limit', 'CPU limit source', 'CPU usage', 'Memory request', 'Memory request source', 'Memory limit', 'Memory limit source', 'Memory usage', 'Workload', 'Ready/desired replicas'];
    var output = [headers.map(csvCell).join(',')].concat(rows.map(function (item) {
      return [ns(), item.pod, item.container, item.containerType, item.phase, item.cpuRequest, item.cpuRequestDefaulted ? 'LimitRange default' : 'Container spec', item.cpuLimit, item.cpuLimitDefaulted ? 'LimitRange default' : 'Container spec', item.cpuUsage, item.memoryRequest, item.memoryRequestDefaulted ? 'LimitRange default' : 'Container spec', item.memoryLimit, item.memoryLimitDefaulted ? 'LimitRange default' : 'Container spec', item.memoryUsage, item.workload, item.replicas].map(csvCell).join(',');
    })).join('\r\n');
    var blob = new Blob(['\ufeff' + output], { type: 'text/csv;charset=utf-8' }), link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = ns() + '-capacity-and-limits-' + new Date().toISOString().slice(0, 10) + '.csv';
    link.click();
    setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
  }
  async function loadCapacity() {
    var panel = $('#capacity');
    panel.innerHTML = '<h2>Capacity & limits <small>' + esc(ns()) + '</small></h2><p class="muted">Loading Pod requests, limits, and live container usage…</p>';
    try {
      var data = await api('/api/capacity?namespace=' + encodeURIComponent(ns()));
      latest = data.items || [];
      metricsEnabled = !!data.metricsAvailable;
      var appRows = latest.filter(function (item) { return item.containerType === 'App'; });
      var missing = appRows.filter(function (item) { return isMissing(item.cpuLimit) || isMissing(item.memoryLimit); });
      var cpuUsage = appRows.reduce(function (sum, item) { return sum + cpuMilli(item.cpuUsage); }, 0);
      var memoryUsage = appRows.reduce(function (sum, item) { return sum + memoryMi(item.memoryUsage); }, 0);
      panel.innerHTML = '<div class="capacity-title"><div><h2>Capacity & limits <small>' + esc(ns()) + '</small></h2><p class="muted">One row per container. Missing CPU or memory limits are highlighted. Live usage requires Metrics Server.</p></div><button id="downloadCapacity" class="primary">Export for Excel (.csv)</button></div>' +
        '<div class="capacity-cards"><div><b>' + appRows.length + '</b><span>App containers</span></div><div><b class="warn">' + missing.length + '</b><span>Missing a limit</span></div><div><b>' + (data.metricsAvailable ? Math.round(cpuUsage) + 'm' : '—') + '</b><span>Current CPU usage</span></div><div><b>' + (data.metricsAvailable ? Math.round(memoryUsage) + 'Mi' : '—') + '</b><span>Current memory usage</span></div></div>' +
        '<div class="capacity-tools"><label>Pod name<input id="capacityPodName" placeholder="Search Pod name…"></label><label>Container type<select id="capacityFilter"><option value="all">All containers</option><option value="main">Main (app) containers</option><option value="init">Init containers</option></select></label><label>Resource policy<select id="capacityPolicy"><option value="all">All policies</option><option value="missing-limit">Missing CPU or memory limit</option><option value="missing-request">Missing CPU or memory request</option></select></label><span id="capacityCount"></span>' + (data.metricsAvailable ? '' : '<span class="warn">Metrics Server is unavailable; usage values are shown as —.</span>') + '</div>' +
        '<p class="muted"><small>† Value inherited from a namespace LimitRange default. Totals use the rows currently shown; use “Main (app) containers” for normal runtime sizing. The last column is the matching workload and its ready/desired replicas—not a container count.</small></p><div class="capacity-table"><table><thead><tr><th>Pod</th><th>Container</th><th>Type</th><th>Phase</th><th>CPU request</th><th>CPU limit</th><th>CPU usage</th><th>Memory request</th><th>Memory limit</th><th>Memory usage</th><th>Workload / replicas</th></tr></thead><tbody id="capacityRows"></tbody><tfoot id="capacityTotals"></tfoot></table></div>';
      $('#capacityFilter').onchange = renderRows;
      $('#capacityPolicy').onchange = renderRows;
      $('#capacityPodName').oninput = renderRows;
      $('#downloadCapacity').onclick = download;
      renderRows();
    } catch (error) {
      panel.innerHTML = '<h2>Capacity & limits</h2><p class="error">' + esc(error.message) + '</p>';
    }
  }
  document.querySelector('[data-tab="capacity"]').onclick = function () {
    document.querySelectorAll('.tabs button').forEach(function (button) { button.classList.toggle('active', button.dataset.tab === 'capacity'); });
    document.querySelectorAll('.panel').forEach(function (panel) { panel.classList.toggle('hidden', panel.id !== 'capacity'); });
    loadCapacity();
  };
  document.head.insertAdjacentHTML('beforeend', '<style>.capacity-title{display:flex;justify-content:space-between;gap:16px;align-items:start}.capacity-cards{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:12px;margin:16px 0}.capacity-cards div{background:#142542;border:1px solid #2c4d74;border-radius:9px;padding:14px}.capacity-cards b{display:block;font-size:23px;color:#5ce0c6}.capacity-cards span{color:#a9c7ed;font-size:12px}.capacity-tools{display:flex;align-items:end;gap:14px;flex-wrap:wrap;margin:12px 0}.capacity-tools label{min-width:220px;color:#b9cde7;font-size:12px}.capacity-tools select{margin-top:5px}.capacity-tools span{color:#9ec7f1;font-size:12px;padding:8px 0}.capacity-table{overflow:auto;border:1px solid #2c4d74;border-radius:9px}.capacity-table table{min-width:1100px}.capacity-table tfoot td{background:#10213a;border-top:2px solid #3d628c}.capacity-missing td:nth-child(5),.capacity-missing td:nth-child(6),.capacity-missing td:nth-child(8),.capacity-missing td:nth-child(9),.inherited{color:#ffcd70;font-weight:650}@media(max-width:900px){.capacity-title{flex-direction:column}.capacity-cards{grid-template-columns:repeat(2,1fr)}}</style>');
}());
