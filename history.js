/* Isolated history view: collection never depends on an open browser. */
(function () {
  'use strict';
  const tab = document.createElement('button');
  tab.dataset.tab = 'history'; tab.textContent = 'History & insights';
  document.querySelector('.tabs').appendChild(tab);
  const panel = document.createElement('div');
  panel.id = 'history'; panel.className = 'panel hidden';
  document.querySelector('.content').appendChild(panel);
  panel.innerHTML = '<div class="history-heading"><div><span class="eyebrow">OBSERVE · UNDERSTAND · IMPROVE</span><h2>History & insights</h2><p class="muted">Retained evidence for your next capacity review.</p></div><button id="historyExport">Export CSV</button></div><div class="tools"><label>Period<select id="historyDays"><option value="1">24 hours</option><option value="7" selected>7 days</option><option value="30">30 days</option></select></label><label>View<select id="historyKind"><option value="metrics">Resource insights</option><option value="logs">Retained application logs</option></select></label><label>Search<input id="historySearch" placeholder="Application, Pod or log text"></label><button id="historyLoad">Load history</button></div><div id="historyStatus" role="status"></div><div id="historyResults"></div>';
  let items = [], request = 0;
  $('#historyKind').closest('label').remove();
  $('#historySearch').placeholder='Application or Pod name';
  const logsLink=document.createElement('button');logsLink.type='button';logsLink.textContent='Open saved logs';$('#historyExport').before(logsLink);logsLink.onclick=()=>window.dispatchEvent(new CustomEvent('show-saved-logs',{detail:{}}));
  const fmt = (x, unit) => x == null ? '—' : Math.round(x) + unit;
  async function load() {
    const id = ++request, namespace = ns(), kind = 'metrics';
    $('#historyStatus').textContent = 'Reading retained records…';
    try {
      const data = await api('/api/history?' + new URLSearchParams({namespace, kind, days: $('#historyDays').value, search: $('#historySearch').value}));
      if (id !== request || namespace !== ns()) return;
      items = kind === 'logs' ? data.items.filter(x => String(x.text || '').trim()) : data.items;
      $('#historyStatus').textContent = (data.enabled ? 'Collection enabled' : 'Collection disabled') + ' · ' + data.retentionDays + ' day retention · ' + (data.lastCollection ? 'Last cycle ' + new Date(data.lastCollection * 1000).toLocaleString() : 'No completed cycle') + (data.truncated ? ' · Results capped: narrow your search.' : '') + (data.errors.length ? ' · Collection issues: ' + data.errors.join('; ') : '');
      $('#historyResults').innerHTML = !items.length ? '<div class="history-empty"><h3>No retained data yet</h3><p>Enable history with a PVC and explicit namespaces in Helm. History starts at installation.</p></div>' : kind === 'logs' ? '<p class="muted">Periodic stdout/stderr captures. Gaps and overlapping lines are possible; this is not a guaranteed complete log archive.</p>' + items.map(x => '<details class="insight"><summary>' + esc(x.application + ' / ' + x.pod + ' / ' + x.container) + ' · ' + esc(new Date(x.ts*1000).toLocaleString()) + '</summary><pre>' + esc(x.text) + '</pre></details>').join('') : '<p class="muted">Values are per container across the displayed application group. Candidate = observed peak + 30% headroom; review gaps, replica differences and release changes before use.</p><div class="insight-grid">' + items.map(x => '<article class="insight"><span class="eyebrow">' + esc(x.container) + '</span><h3>' + esc(x.application) + '</h3><div class="insight-values"><div><b>' + fmt(x.peakMemory,'Mi') + '</b><small>Peak memory</small></div><div><b>' + fmt(x.p95Memory,'Mi') + '</b><small>P95 memory</small></div><div><b>' + fmt(x.peakCpu,'m') + '</b><small>Peak CPU</small></div></div><p>' + x.observedDays + ' days observed · ' + x.metricSamples + ' memory samples</p><p>Memory limit candidate: <strong>' + fmt(x.candidateMemoryLimit,'Mi') + '</strong></p><ul>' + x.suggestions.map(s => '<li>' + esc(s) + '</li>').join('') + '</ul><small class="muted">' + esc(x.confidence) + '</small></article>').join('') + '</div>';
      $('#historyStatus').textContent = (data.enabled ? 'Collection enabled' : 'Collection disabled') + ' · ' + data.retentionDays + ' day retention · ' + (data.lastCollection ? 'Last cycle ' + new Date(data.lastCollection * 1000).toLocaleString() : 'Waiting for first cycle') + (data.truncated ? ' · Results capped: narrow your search.' : '');
      if (kind === 'logs' && !items.length) {
        const reason = !data.logsEnabled ? 'Log collection is disabled. Enable history.logsEnabled in your private Helm values.' : 'No non-empty stdout/stderr logs were captured for this selection. Quiet containers may produce no output during the collection interval. Try another period or clear the search. File-only application logs are not captured.';
        $('#historyResults').innerHTML = '<div class="history-empty"><h3>No captured log lines</h3><p>' + esc(reason) + '</p><p>Check the Pod’s live Logs view to confirm whether it writes to stdout/stderr.</p></div>';
      }
      if(data.errors.length) $('#historyStatus').insertAdjacentHTML('beforeend', '<details class="history-issues"><summary>' + data.errors.length + ' collection issue(s) for this namespace — show details</summary><ul>' + data.errors.map(e=>'<li>'+esc(e)+'</li>').join('') + '</ul><p>Collection will retry next cycle. Other successful captures remain available.</p></details>');
      $('#historyExport').disabled = !items.length;
    } catch (e) { if(id===request){items=[];$('#historyStatus').textContent=e.message;$('#historyResults').textContent='';$('#historyExport').disabled=true;} }
  }
  tab.onclick = function () {
    document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b === tab));
    document.querySelectorAll('.panel').forEach(p => p.classList.toggle('hidden', p !== panel)); load();
  };
  $('#historyLoad').onclick = load;
  $('#historyDays').onchange = load;
  $('#namespace').addEventListener('change', () => {items=[]; if (!panel.classList.contains('hidden')) load();});
  $('#historyExport').onclick = function () {
    if(!items.length) return;
    const cell = v => '"' + String(v == null ? '' : Array.isArray(v) ? v.join('; ') : v).replace(/^[=+@-]/, "'$&").replace(/"/g,'""') + '"';
    const keys = Object.keys(items[0]), text = '\ufeff' + [keys.map(cell).join(','), ...items.map(x=>keys.map(k=>cell(x[k])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'})), a=document.createElement('a');
    a.href=url; a.download='history-'+ns()+'.csv'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
}());
