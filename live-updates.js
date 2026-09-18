/* Near-live refresh without broadening Kubernetes permissions. */
(function(){
  var revision=null,busy=false,namespace=null;
  var indicator=document.createElement('span');indicator.className='live-indicator';indicator.innerHTML='<b></b><span>Live updates starting…</span>';
  var actions=document.querySelector('.header-actions');if(actions)actions.prepend(indicator);
  function label(text){var span=indicator.querySelector('span');if(span)span.textContent=text}
  async function poll(){
    if(document.hidden||busy||!ns())return;busy=true;
    try{
      var selected=ns(),result=await api('/api/namespace-revision?namespace='+encodeURIComponent(selected));
      if(selected!==ns())return;
      if(namespace!==selected){namespace=selected;revision=result.revision;label('Watching '+selected);return}
      if(revision&&revision!==result.revision){
        revision=result.revision;label('Updated '+new Date().toLocaleTimeString());
        document.dispatchEvent(new CustomEvent('dashboard-resource-change',{detail:{namespace:selected}}));
        var active=document.querySelector('.tabs button.active');
        if(active&&active.dataset.tab!=='applications'){
          if(['overview','workloads','pods','events'].includes(active.dataset.tab))loadNamespace();else active.click();
        }
      }else{revision=result.revision;label('Watching '+selected)}
    }catch(error){label('Live update check unavailable')}finally{busy=false}
  }
  $('#namespace').addEventListener('change',function(){namespace=null;revision=null;poll()});
  document.addEventListener('visibilitychange',function(){if(!document.hidden)poll()});
  setInterval(poll,15000);setTimeout(poll,1500);
}());
