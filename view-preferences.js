/* Local display preferences only; no credentials or cluster data are stored. */
(function(){
  var prefix='kubernetes-operations-dashboard.';
  function restore(id){var element=document.getElementById(id),saved=localStorage.getItem(prefix+id);if(!element||saved==null)return;if([...element.options||[]].some(function(option){return option.value===saved}))element.value=saved}
  function bind(id){var element=document.getElementById(id);if(!element||element.dataset.preferenceBound)return;restore(id);element.dataset.preferenceBound='true';element.addEventListener('change',function(){localStorage.setItem(prefix+id,element.value)})}
  var observer=new MutationObserver(function(){['changeDays','changeSource','historyDays','discoveredKind'].forEach(bind)});observer.observe(document.body,{childList:true,subtree:true});
  $('#namespace').addEventListener('change',function(){if(ns())localStorage.setItem(prefix+'namespace',ns())});
  var applied=false,timer=setInterval(function(){if(applied||!$('#namespace').options.length)return;var saved=localStorage.getItem(prefix+'namespace');if(saved&&[...$('#namespace').options].some(function(option){return option.value===saved})&&ns()!==saved){$('#namespace').value=saved;$('#namespace').dispatchEvent(new Event('change',{bubbles:true}));loadNamespace()}applied=true;clearInterval(timer)},250);
}());
