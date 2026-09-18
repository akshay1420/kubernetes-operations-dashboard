/* One namespace selection for every namespaced view; nodes remain cluster-wide. */
(function () {
  let generation=0, selected=ns();
  const originalFetch=window.fetch.bind(window);
  window.fetch=async function(input,options){
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    const requested=url.searchParams.get('namespace'), version=generation;
    const response=await originalFetch(input,options);
    if(requested){
      const read=response.json.bind(response);
      response.json=async()=>{const data=await read();if(version!==generation||requested!==ns())throw Error('Namespace changed; previous response discarded.');return data};
    }
    return response;
  };
  function changed(){
    if(selected===ns())return;
    selected=ns();generation++;
    document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
    // Clear old namespace content immediately, including hidden views.
    document.querySelectorAll('.panel').forEach(panel=>{
      if(!['changes','history'].includes(panel.id))panel.innerHTML='<p>Loading namespace '+esc(selected)+'…</p>';
    });
    const active=document.querySelector('.tabs button.active');
    if(active&&['resources','capacity'].includes(active.dataset.tab))active.click();
  }
  $('#namespace').addEventListener('change',changed,true);
  document.addEventListener('click',event=>{
    const shortcut=event.target.closest('[data-ns]');
    if(shortcut){$('#namespace').value=shortcut.dataset.ns;changed()}
  },true);
  // Refresh must preserve the chosen namespace rather than reset to default.
  const clusterLoad=loadCluster;
  loadCluster=async function(){const previous=ns();await clusterLoad();if([...$('#namespace').options].some(option=>option.value===previous))$('#namespace').value=previous;selected=ns()};
}());
