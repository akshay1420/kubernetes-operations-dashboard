/* Progressive visual enhancement. No API, permission, or stored cluster state changes. */
(function(){
  var content=document.querySelector('.content'),tabs=document.querySelector('.tabs');
  if(!content||!tabs)return;
  var bar=document.createElement('section');bar.className='workspace-bar';bar.setAttribute('aria-label','Current operations workspace');
  bar.innerHTML='<div class="workspace-title"><span class="workspace-icon" aria-hidden="true">K8s</span><div class="workspace-copy"><small>Operations workspace</small><strong id="workspaceView">Namespace overview</strong></div></div><div class="workspace-meta"><span class="scope-chip" id="workspaceScope">Namespace</span></div>';
  tabs.before(bar);
  function selectedNamespace(){var field=document.querySelector('#namespace');return field&&field.value||'Loading namespace…'}
  function activeTab(){var button=tabs.querySelector('button.active');return button?button.textContent.trim():'Overview'}
  function updateChrome(){
    var scope=document.querySelector('#workspaceScope'),title=document.querySelector('#workspaceView');
    var scopeText=selectedNamespace(),titleText=activeTab()+' · '+scopeText;
    if(scope&&scope.textContent!==scopeText)scope.textContent=scopeText;
    if(title&&title.textContent!==titleText)title.textContent=titleText;
    document.querySelectorAll('.ns').forEach(function(button){button.classList.toggle('ns-active',button.dataset.ns===selectedNamespace());button.setAttribute('aria-current',button.dataset.ns===selectedNamespace()?'true':'false')});
    tabs.querySelectorAll('button').forEach(function(button){var active=button.classList.contains('active');button.setAttribute('aria-selected',active?'true':'false');button.setAttribute('role','tab')});
  }
  function enhanceTables(root){
    var tables=[];if(root&&root.matches&&root.matches('table'))tables.push(root);tables=tables.concat(Array.from((root||document).querySelectorAll('table')));
    tables.forEach(function(table){
      if(table.parentElement&&table.parentElement.classList.contains('table-shell'))return;
      var shell=document.createElement('div');shell.className='table-shell';shell.setAttribute('tabindex','0');shell.setAttribute('role','region');shell.setAttribute('aria-label','Scrollable data table');
      table.parentNode.insertBefore(shell,table);shell.appendChild(table);
      table.querySelectorAll('tbody tr').forEach(function(row){if(row.cells.length===1||row.querySelector('td[colspan]'))row.classList.add('empty-row')});
    });
  }
  function enhanceLoading(root){
    var nodes=[];if(root&&root.matches&&root.matches('.panel>p'))nodes.push(root);nodes=nodes.concat(Array.from((root||document).querySelectorAll('.panel>p')));nodes.forEach(function(node){if(/^Loading\b/i.test(node.textContent.trim()))node.classList.add('loading-state')});
  }
  tabs.addEventListener('click',function(){setTimeout(updateChrome,0)});
  document.querySelector('#namespace').addEventListener('change',function(){setTimeout(updateChrome,0)});
  document.addEventListener('click',function(event){if(event.target.closest('[data-ns]'))setTimeout(updateChrome,0)});
  new MutationObserver(function(records){records.forEach(function(record){record.addedNodes.forEach(function(node){if(node.nodeType!==1)return;enhanceTables(node);enhanceLoading(node)})});updateChrome()}).observe(content,{childList:true,subtree:true});
  document.querySelectorAll('dialog').forEach(function(dialog){if(!dialog.getAttribute('aria-modal'))dialog.setAttribute('aria-modal','true')});
  enhanceTables(document);enhanceLoading(document);updateChrome();
}());
