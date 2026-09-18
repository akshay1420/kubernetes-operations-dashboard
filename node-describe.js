/* Node cards support pointer and keyboard activation, including after refresh. */
(function () {
  const nodes = document.querySelector('#nodes');
  const dialog = document.createElement('dialog');
  dialog.id = 'nodeDescribeDialog';
  dialog.setAttribute('aria-labelledby', 'nodeDescribeTitle');
  dialog.innerHTML = '<form method="dialog"><button class="close" aria-label="Close node details">×</button></form><h2 id="nodeDescribeTitle">Describe node</h2><p>Cluster-scoped worker node details</p><p class="warn" id="nodeDescribeWarning" hidden></p><pre id="nodeDescribeOutput" aria-live="polite"></pre>';
  document.body.append(dialog);
  let request = 0;
  function enhance() {
    nodes.querySelectorAll('[data-node]').forEach(card => {
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      card.setAttribute('aria-label', 'Describe worker node ' + card.dataset.node);
      card.title = 'Click to describe worker node';
      card.style.cursor = 'pointer';
    });
  }
  async function open(card) {
    const id = ++request;
    const output = dialog.querySelector('pre'), warning = dialog.querySelector('.warn');
    dialog.querySelector('h2').textContent = 'Describe node · ' + card.dataset.node;
    output.textContent = 'Loading node description…';
    warning.hidden = true;
    if (!dialog.open) dialog.showModal();
    try {
      const data = await api('/api/node-describe?node=' + encodeURIComponent(card.dataset.node));
      if (id !== request || !dialog.open) return;
      output.textContent = data.output;
      warning.textContent = data.warning || '';
      warning.hidden = !data.warning;
    } catch (error) {
      if (id === request && dialog.open) output.textContent = error.message;
    }
  }
  nodes.addEventListener('click', event => { const card = event.target.closest('[data-node]'); if (card) open(card); });
  nodes.addEventListener('keydown', event => {
    const card = event.target.closest('[data-node]');
    if (card && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); open(card); }
  });
  dialog.addEventListener('close', () => { ++request; });
  new MutationObserver(enhance).observe(nodes, {childList:true});
  enhance();
}());
