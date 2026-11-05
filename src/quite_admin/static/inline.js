/* Same-origin, permission-checked single-field edits. Values stay in the dialog. */
(function () {
  function enhance(scope = document, request = window.fetch.bind(window)) {
  const dialog=scope.querySelector('[data-inline-dialog]');
  if(!dialog)return () => {};
  const form=dialog.querySelector('form'),host=dialog.querySelector('[data-inline-control]');
  const error=dialog.querySelector('[data-inline-error]'),save=dialog.querySelector('[data-inline-save]');
  const cancel=dialog.querySelector('[data-inline-cancel]'),title=dialog.querySelector('h2');
  const messages=JSON.parse(dialog.dataset.messages);
  dialog.setAttribute('aria-labelledby',title.id);
  async function readField(endpoint, signal) {
    const response=await request(endpoint,{credentials:'same-origin',headers:{Accept:'application/json'},signal});
    if(!response.ok)throw new Error(messages.error);
    return response.json();
  }
  async function saveField(endpoint, model, value) {
    const body=new URLSearchParams({__csrf:model.csrf,__revision:model.revision,[model.name]:value});
    const response=await request(endpoint,{method:'POST',credentials:'same-origin',headers:{Accept:'application/json'},body});
    const result=response.headers.get('content-type')?.includes('application/json')?await response.json():null;
    if(!response.ok)throw new Error(result?.errors?Object.values(result.errors).join(' '):messages.error);
    return result;
  }
  function updateRow(row,result){
      for(const td of row.querySelectorAll('[data-list-field]')){
        const cell=result.cells[td.dataset.listField]; if(!cell)continue;
        const foreign=td.querySelector('[data-fk-value]');
        if(foreign){
          if(cell.related){const link=document.createElement('a');link.className='relation-value';link.href=cell.related.href;link.title=cell.related.text;link.textContent=cell.related.text.length>90?cell.related.text.slice(0,87)+'…':cell.related.text;foreign.replaceChildren(link);}
          else foreign.textContent=cell.text;
          continue;
        }
        if(cell.display){window.quiteAdminUpdateValue?.(td.querySelector('[data-field-display]'),cell.display);continue;}
        const group=td.querySelector('[data-list-toggle-control]');
        if(group){
          group.dataset.value=cell.null?'null':cell.boolean?'true':'false';
          const toggle=group.querySelector('[data-list-switch]');
          toggle.setAttribute('aria-checked',String(cell.boolean));
          toggle.setAttribute('aria-label',toggle.dataset.fieldLabel+(cell.null?': '+messages.none:''));
          group.querySelector('.toggle-null-state').hidden=!cell.null;
          group.querySelector('[data-list-null]')?.setAttribute('aria-pressed',String(cell.null));
          continue;
        }
        const span=td.querySelector('[data-cell-value]');if(!span)continue;
        span.textContent=cell.text.length>90?cell.text.slice(0,87)+'…':cell.text;
        span.title=cell.text.slice(0,4096);
        if(cell.null)span.className='null-value';
        else if(!span.classList.contains('record-id'))span.className='cell-value';
      }
      for(const link of row.querySelectorAll('.record-row-link'))link.setAttribute('aria-label',result.label_record);
  }
  const status=scope.querySelector('[data-list-save-status]');
  for(const group of scope.querySelectorAll('[data-toggle-endpoint]')){
    let saving=false;
    const toggle=group.querySelector('[data-list-switch]'),nil=group.querySelector('[data-list-null]');
    async function setValue(value){
      if(saving)return;saving=true;toggle.disabled=true;if(nil)nil.disabled=true;status.hidden=true;
      try{
        const state=await readField(group.dataset.toggleEndpoint);
        // The displayed state must still match before choosing a new value.
        // The signed revision then protects the subsequent write atomically.
        const displayed=group.dataset.value==='null'?'':group.dataset.value;
        const actual=state.raw_boolean===null?'':state.raw_boolean?'true':'false';
        if(actual!==displayed)throw new Error(messages.conflict);
        const result=await saveField(group.dataset.toggleEndpoint,state,value);
        updateRow(group.closest('tr'),result);
      }catch(e){status.textContent=e.message||messages.error;status.hidden=false;}
      finally{saving=false;toggle.disabled=false;if(nil)nil.disabled=false;}
    }
    toggle.addEventListener('click',()=>setValue(group.dataset.value==='true'?'false':'true'));
    nil?.addEventListener('click',()=>setValue(group.dataset.value==='null'?'false':''));
  }
  let source,model,control,busy=false,controller,cleanup;
  function close(){if(!busy){controller?.abort();cleanup?.();cleanup=null;dialog.close();source?.focus();}}
  cancel.addEventListener('click',close);
  dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
  for(const button of scope.querySelectorAll('[data-inline-endpoint]'))button.addEventListener('click',async()=>{
    cleanup?.();cleanup=null;source=button;model=null;host.replaceChildren();error.textContent='';title.textContent=messages.loading;
    save.disabled=true;dialog.showModal();controller=new AbortController();
    try{
      model=await readField(button.dataset.inlineEndpoint,controller.signal);title.textContent=model.label;
      control=window.QuiteAdmin.createFieldControl(model,{id:'inline-value',value:model.value});
      control.setAttribute('aria-labelledby',title.id);control.setAttribute('aria-describedby','inline-error');
      error.id='inline-error';host.append(control);
      cleanup=window.quiteAdminEnhanceFields?.(host);
      // Switch and calendar enhancement can hide the canonical control.
      (host.querySelector('input:not([type=hidden]),textarea,button[role=switch],select:not([hidden])')||save).focus();
      save.disabled=false;
    }catch(e){if(e.name!=='AbortError')error.textContent=messages.error;}
  });
  form.addEventListener('submit',async e=>{
    e.preventDefault();if(!model||busy)return;
    busy=true;save.disabled=true;cancel.disabled=true;error.textContent='';
    try{
      const result=await saveField(source.dataset.inlineEndpoint,model,control.value);
      updateRow(source.closest("tr"), result);
      busy=false;close();
    }catch(e){error.textContent=e.message||messages.error;}
    finally{busy=false;save.disabled=false;cancel.disabled=false;}
  });
  return () => {controller?.abort();cleanup?.();if(dialog.open)dialog.close();};
  }
  window.quiteAdminEnhanceInline = enhance;
  enhance();
})();
