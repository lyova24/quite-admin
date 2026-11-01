/* Same-origin, permission-checked single-field edits. Values stay in the dialog. */
(function () {
  const dialog=document.querySelector('[data-inline-dialog]');
  if(!dialog)return;
  const form=dialog.querySelector('form'),host=dialog.querySelector('[data-inline-control]');
  const error=dialog.querySelector('[data-inline-error]'),save=dialog.querySelector('[data-inline-save]');
  const cancel=dialog.querySelector('[data-inline-cancel]'),title=dialog.querySelector('h2');
  const messages=JSON.parse(dialog.dataset.messages);
  dialog.setAttribute('aria-labelledby',title.id);
  let source,model,control,busy=false,controller,cleanup;
  function close(){if(!busy){controller?.abort();cleanup?.();cleanup=null;dialog.close();source?.focus();}}
  cancel.addEventListener('click',close);
  dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
  for(const button of document.querySelectorAll('[data-inline-endpoint]'))button.addEventListener('click',async()=>{
    cleanup?.();cleanup=null;source=button;model=null;host.replaceChildren();error.textContent='';title.textContent=messages.loading;
    save.disabled=true;dialog.showModal();controller=new AbortController();
    try{
      const response=await fetch(button.dataset.inlineEndpoint,{credentials:'same-origin',headers:{Accept:'application/json'},signal:controller.signal});
      if(!response.ok)throw new Error(messages.error);
      model=await response.json();title.textContent=model.label;
      if(model.kind==='boolean'||model.choices.length){
        control=document.createElement('select');
        const choices=model.kind==='boolean'?[['true','True'],['false','False']]:model.choices.map(c=>[c,c]);
        if(model.nullable)choices.unshift(['','—']);
        for(const [value,label] of choices){const option=document.createElement('option');option.value=value;option.textContent=label;control.append(option);}
        if(model.kind==='boolean')control.setAttribute('data-boolean-toggle','');
      }else if(model.kind==='json'||model.multiline){
        control=document.createElement('textarea');control.rows=6;
        if(model.kind==='json'){control.setAttribute('data-json-editor','');control.className='code-input';control.spellcheck=false;}
      }else{
        control=document.createElement('input');
        control.type=['integer','number'].includes(model.kind)?'number':model.kind==='date'?'date':'text';
        if(['integer','number'].includes(model.kind))control.step=model.kind==='integer'?'1':'any';
        if(model.kind==='date')control.setAttribute('data-calendar-input','');
        if(['datetime','time'].includes(model.kind))control.dataset.temporal=model.kind;
      }
      control.id='inline-value';control.name=model.name;control.value=model.value;
      control.setAttribute('aria-labelledby',title.id);control.setAttribute('aria-describedby','inline-error');
      if(model.max_length)control.maxLength=model.max_length;
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
      const data=new URLSearchParams();data.set('__csrf',model.csrf);data.set('__revision',model.revision);data.set(model.name,control.value);
      const response=await fetch(source.dataset.inlineEndpoint,{method:'POST',credentials:'same-origin',headers:{Accept:'application/json'},body:data});
      const result=response.headers.get('content-type')?.includes('application/json')?await response.json():null;
      if(!response.ok){error.textContent=result?.errors?Object.values(result.errors).join(' '):messages.error;return;}
      const row=source.closest('tr');
      for(const td of row.querySelectorAll('[data-list-field]')){
        const cell=result.cells[td.dataset.listField],span=td.querySelector('[data-cell-value]');
        if(!cell||!span)continue;
        span.textContent=cell.text.length>90?cell.text.slice(0,87)+'…':cell.text;
        span.title=cell.text.slice(0,4096);
        if(cell.null)span.className='null-value';
        else if(cell.kind==='boolean')span.className='boolean-badge '+(cell.boolean?'yes':'no');
        else if(!span.classList.contains('record-id'))span.className='cell-value';
      }
      for(const link of row.querySelectorAll('.record-row-link'))link.setAttribute('aria-label',result.label_record);
      busy=false;close();
    }catch(_){error.textContent=messages.error;}
    finally{busy=false;save.disabled=false;cancel.disabled=false;}
  });
})();
