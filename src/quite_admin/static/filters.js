/* Typed condition editor. Values remain strings, including Decimal and large IDs. */
(function () {
  "use strict";
  const ranges = new Set(["integer", "number", "date", "datetime", "time"]);
  const labels = {
    eq:"Equals",ne:"Does not equal",icontains:"Contains",not_icontains:"Does not contain",
    istartswith:"Starts with",iendswith:"Ends with",in:"Is one of",on:"On date",
    gt:"Greater than",gte:"At least",lt:"Less than",lte:"At most",between:"Between",
    null:"Is NULL",not_null:"Is not NULL",empty:"Is empty text",not_empty:"Is not empty text",
  };
  function operators(field) {
    let raw = field.operators;
    if (!raw) raw = field.kind === "relation" ? ["eq"]
      : ["json","binary","unsupported"].includes(field.kind) ? []
      : field.kind === "boolean" ? ["eq"] : field.choices?.length || field.kind === 'enum' ? ['eq','ne','in']
      : field.kind === 'string' ? ['icontains','not_icontains','eq','ne','istartswith','iendswith','in','is_empty']
      : ranges.has(field.kind) ? ['eq','ne','gt','gte','lt','lte','in'] : ['eq','ne','in'];
    const result = raw.flatMap(op => op === 'is_null' ? ['null','not_null'] : op === 'is_empty' ? field.supports_not_empty === false ? ['empty'] : ['empty','not_empty'] : [op]);
    if (raw.includes('gte') && raw.includes('lte') && ranges.has(field.kind)) result.splice(result.indexOf('gte'),0,'between');
    if (!field.operators && field.nullable) result.push('null','not_null');
    return result;
  }
  function entries(field, op, values) {
    if (!operators(field).includes(op)) throw new Error('Invalid filter operator');
    if (op === 'between') return [[field.id+'.gte',values[0]],[field.id+'.lte',values[1]]];
    if (['null','not_null'].includes(op)) return [[field.id+'.is_null',String(op==='null')]];
    if (['empty','not_empty'].includes(op)) return [[field.id+'.is_empty',String(op==='empty')]];
    if (op==='in') return [[field.id+'.in',JSON.stringify(values)]];
    if (op==='on') return [[field.id+'.on',values[0]+(values[1]?'T00:00:00'+values[1]:'')]];
    return [[field.kind==='relation'?field.id:field.id+'.'+op,values[0]]];
  }
  function updateQuery(params, condition, replacement) {
    const next = new URLSearchParams(params);
    (condition?.parameters || []).forEach(name => next.delete(name));
    if(!replacement.length){next.set('page','1');return next;}
    const name=(base,suffix)=>base+(suffix?'~'+suffix:'');
    const slots=new Set(['',...[...next.keys()].map(key=>key.match(/~([1-9][0-9]?)$/)?.[1]).filter(Boolean)]);
    if([...slots].some(slot=>replacement.every(([key,value])=>next.get(name(key,slot))===value)))throw new Error('conflict');
    let slot=condition?.parameters[0]?.match(/~([1-9][0-9]?)$/)?.[1]||'';
    if(replacement.some(([key])=>next.has(name(key,slot)))){
      slot='1';while(replacement.some(([key])=>next.has(name(key,slot)))){slot=String(Number(slot)+1);if(Number(slot)>50)throw new Error('conflict');}
    }
    for(const [key,value] of replacement)next.set(name(key,slot),value);
    next.set('page','1');return next;
  }
  if(typeof module!=='undefined' && module.exports)module.exports={operators,entries,updateQuery,labels};
  if(typeof document==='undefined')return;
  function element(tag,className,text){const n=document.createElement(tag);if(className)n.className=className;if(text!=null)n.textContent=text;return n;}
  function init(root){
    const fields=JSON.parse(root.dataset.fields),conditions=JSON.parse(root.dataset.conditions);
    const messages=JSON.parse(root.dataset.messages),errors=JSON.parse(root.dataset.errors||'{}');
    const t=key=>messages[key]||labels[key]||key;
    const add=root.querySelector('[data-filter-add]'),fallback=root.querySelector('[data-filter-fallback]');
    if(!add||!fallback||typeof HTMLDialogElement==='undefined')return;
    const dialog=element('dialog','filter-dialog');dialog.id='filter-editor';
    dialog.setAttribute('aria-label',t('add'));root.closest('.record-list').append(dialog);
    add.setAttribute('aria-controls',dialog.id);add.setAttribute('aria-haspopup','dialog');add.setAttribute('aria-expanded','false');
    let anchor=add,abort,timer,sequence=0,cleanup,sidebar,pane;
    function stopLookup(){clearTimeout(timer);abort?.abort();sequence++;}
    function close(){stopLookup();cleanup?.();cleanup=null;dialog.close();add.setAttribute('aria-expanded','false');anchor.focus();root.dispatchEvent(new Event('quite-admin:filter-close'));}
    function button(text,classes,action){const n=element('button',classes,text);n.type='button';n.addEventListener('click',action);return n;}
    function navigate(next){stopLookup();if(root.navigate)root.navigate(next);else location.assign(root.action.split('?')[0]+'?'+next);}
    function params(){return new URLSearchParams(new FormData(root));}
    dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
    dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)close();}});
    function menu(trigger=add,initialField=null,initialCondition=undefined){
      stopLookup();cleanup?.();cleanup=null;anchor=trigger;dialog.replaceChildren();
      const header=element('div','filter-dialog-heading');
      const heading=element('h2','',t('add'));heading.id='filter-dialog-title';dialog.setAttribute('aria-labelledby',heading.id);
      header.append(heading,button(t('close'),'button secondary small',close));
      const layout=element('div','filter-dialog-layout');sidebar=element('div','filter-dialog-sidebar');pane=element('div','filter-dialog-pane');
      const search=element('input');search.type='search';search.placeholder=t('find');search.setAttribute('aria-label',t('find'));search.autocomplete='off';
      const list=element('div','filter-field-menu');
      const render=()=>{
        list.replaceChildren();
        for(const field of fields.filter(f=>(f.label+' '+f.id).toLocaleLowerCase().includes(search.value.toLocaleLowerCase()))){
          const matching=conditions.filter(c=>c.id===field.id);
          const b=button('','filter-field-option',()=>editor(field,matching[0]));b.dataset.field=field.id;
          b.append(element('span','filter-option-label',field.label));
          b.append(element('span','filter-option-note',matching.length?String(matching.length):t('type_'+(field.choices?.length?'enum':field.kind))));
          list.append(b);
        }
        if(!list.children.length)list.append(element('p','filter-menu-help',t('no_fields')));
      };
      search.addEventListener('input',render);
      sidebar.addEventListener('keydown',e=>{
        const items=[search,...list.querySelectorAll('button')],i=items.indexOf(document.activeElement);
        if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();items[(i+(e.key==='ArrowDown'?1:items.length-1))%items.length].focus();}
        if(e.key==='Enter'&&document.activeElement===search){e.preventDefault();list.querySelector('button')?.click();}
      });
      sidebar.append(search,list);layout.append(sidebar,pane);dialog.append(header,layout,element('p','filter-dialog-hint',t('hint')));render();
      const field=initialField||fields.find(f=>f.kind==='string'&&!f.choices?.length)||fields[0];
      if(field)editor(field,initialCondition===undefined?conditions.find(c=>c.id===field.id):initialCondition);
      if(!dialog.open)dialog.showModal();add.setAttribute('aria-expanded','true');root.dispatchEvent(new Event('quite-admin:filter-open'));
      (pane.querySelector('.filter-editor-values input,.filter-editor-values textarea,.filter-editor-values select')||search).focus();
    }
    function editor(field,condition){
      stopLookup();cleanup?.();cleanup=null;pane.replaceChildren();
      sidebar.querySelectorAll('[data-field]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.field===field.id)));
      const heading=element('div','filter-editor-heading');heading.append(element('strong','',field.label),element('span','badge',t('type_'+(field.choices?.length?'enum':field.kind))));
      const saved=element('div','filter-saved-conditions');
      for(const item of conditions.filter(c=>c.id===field.id))saved.append(button(item.label,'filter-saved-condition'+(item===condition?' selected':''),()=>editor(field,item)));
      if(saved.children.length&&field.kind!=='relation')saved.append(button('+ '+t('another'),'link-button',()=>editor(field,null)));
      const body=element('div','filter-editor-body'),label=element('label','',t('operator')),operator=element('select');
      label.htmlFor='filter-operator';operator.id=label.htmlFor;
      for(const op of operators(field)){const n=element('option','',t(op));n.value=op;operator.append(n);}
      operator.value=condition?.operator==='is_null'?(condition.values[0]==='true'?'null':'not_null'):condition?.operator==='is_empty'?(condition.values[0]==='true'?'empty':'not_empty'):condition?.operator||operators(field)[0];
      const values=element('div','filter-editor-values'),preview=element('p','filter-preview');preview.setAttribute('aria-live','polite');
      const error=element('p','field-error');error.id='filter-condition-error';error.setAttribute('role','alert');error.hidden=true;
      const footer=element('div','filter-editor-footer'),apply=button(t('apply'),'button primary',submit);
      if(condition)footer.append(button(t('remove'),'button danger-outline small',()=>navigate(updateQuery(params(),condition,[]))));
      footer.append(button(t('cancel'),'button secondary',close),apply);body.append(label,operator,values,preview,error);pane.append(heading,saved,body,footer);
      let currentOp=operator.value,drafts=condition?.values.slice()||[],inputs=[],checks=[],selected=field.kind==='relation'?condition?.values[0]||'':'';
      let relationLabel=(field.choices||[]).find(item=>item[0]===selected)?.[1]||'';
      function showError(text){error.textContent=text;error.hidden=false;inputs.forEach(input=>{input.setAttribute('aria-invalid','true');input.setAttribute('aria-describedby',error.id);});}
      function rawValues(op=operator.value){if(field.kind==='relation')return[selected];if(op==='in')return checks.length?checks.filter(n=>n.checked).map(n=>n.value):inputs[0].value.split(/\r?\n/).filter(v=>v!=='');return inputs.map(input=>input.value);}
      function updatePreview(){const raw=field.kind==='relation'?[relationLabel]:rawValues();preview.textContent=field.label+' '+t(operator.value)+(raw.filter(Boolean).length?' '+raw.filter(Boolean).join(' · '):'');}
      function inputRow(text,input,index){
        const wrap=element('div'),label=element('label','',text);input.id='filter-value-'+index;label.htmlFor=input.id;
        input.addEventListener('input',()=>{error.hidden=true;input.removeAttribute('aria-invalid');updatePreview();});
        input.addEventListener('keydown',e=>{if(e.key==='Enter'&&input.tagName!=='TEXTAREA'&&!e.isComposing){e.preventDefault();submit();}});
        inputs.push(input);wrap.append(label,input);values.append(wrap);return input;
      }
      function renderValues(initial=false){
        stopLookup();cleanup?.();cleanup=null;values.replaceChildren();inputs=[];checks=[];error.hidden=true;
        if(['null','not_null','empty','not_empty'].includes(operator.value)){updatePreview();return;}
        if(field.kind==='relation'){renderRelated();updatePreview();return;}
        values.classList.toggle('filter-editor-range',operator.value==='between');
        if(operator.value==='in'){
          let selected=drafts;
          try{if(initial)selected=JSON.parse(condition?.values[0]||'[]');}catch(_){selected=[];}
          if(field.choices?.length){
            const search=element('input');search.type='search';search.placeholder=t('find_values');search.setAttribute('aria-label',t('find_values'));values.append(search);
            const list=element('div','filter-choice-list');
            for(const value of field.choices){const label=element('label','checkbox-label');const check=element('input');check.type='checkbox';check.value=value;check.checked=selected.includes(value);check.addEventListener('change',updatePreview);checks.push(check);label.append(check,document.createTextNode(value));list.append(label);}
            search.addEventListener('input',()=>list.querySelectorAll('label').forEach(label=>label.hidden=!label.textContent.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())));values.append(list);
          }else{
            const input=element('textarea');input.rows=4;input.maxLength=8192;input.spellcheck=false;input.value=selected.join('\n');inputRow(t('one_per_line'),input,0);
          }
          values.append(element('p','field-help',t('any_value')));updatePreview();return;
        }
        if(operator.value==='on'){
          const date=element('input');date.type='date';date.value=(drafts[0]||'').slice(0,10);date.setAttribute('data-calendar-input','');inputRow(t('date'),date,0);
          const zone=element('input');zone.type='text';zone.placeholder='+03:00';zone.maxLength=6;
          zone.pattern='Z|(?:[+]|-)(?:[01][0-9]|2[0-3]):[0-5][0-9]';zone.value=(drafts[0]||'').match(/(Z|[+-]\d{2}:\d{2})$/)?.[1]||drafts[1]||'';inputRow(t('timezone'),zone,1);
          values.append(element('p','field-help',t('day_hint')));
        }else{
          const count=operator.value==='between'?2:1;
          for(let i=0;i<count;i++){
            let input;
            if(field.kind==='boolean'||field.choices?.length){
              input=element('select');const options=field.kind==='boolean'?[['true',t('true')],['false',t('false')]]:field.choices.map(v=>[v,v]);
              options.unshift(['','—']);for(const [value,text] of options){const option=element('option','',text);option.value=value;input.append(option);}
            }else{
              input=element('input');input.type=field.kind==='date'?'date':'text';input.maxLength=500;input.autocomplete='off';
              if(field.kind==='date')input.setAttribute('data-calendar-input','');
              if(['integer','number'].includes(field.kind))input.inputMode=field.kind==='integer'?'numeric':'decimal';
              if(['datetime','time'].includes(field.kind))input.dataset.temporal=field.kind;
              if(field.kind==='string')input.placeholder=t('text_example');
            }
            const raw=drafts[i]||'';input.value=field.kind==='boolean'?(raw==='1'?'true':raw==='0'?'false':raw.toLowerCase()):raw;
            inputRow(t(count===2?(i===0?'from':'to'):'value'),input,i);
          }
          if(field.kind==='string'&&!field.choices?.length)values.append(element('p','field-help',t('text_hint')));
        }
        cleanup=window.quiteAdminEnhanceFields?.(values);updatePreview();
      }
      function renderRelated() {
        const chosen = element("p", "filter-related-selected");
        function showSelected() { chosen.textContent = selected ? t("selected") + ": " + relationLabel : ""; chosen.hidden = !selected; }
        showSelected();
        const search = element("input"); search.type = "search"; search.placeholder = t("search"); search.setAttribute("aria-label", t("search"));
        const status = element("p", "filter-lookup-status"); status.setAttribute("role", "status");
        const results = element("div", "filter-related-results");
        const pages = element("div", "filter-lookup-pages");
        const hint = element("p", "field-help", field.key_search ? t("search_id") : t("search_text"));
        if(field.search_labels?.length)hint.textContent += ' ' + field.search_labels.join(', ');
        search.setAttribute('aria-describedby','filter-related-hint');hint.id='filter-related-hint';
        values.append(search, hint, chosen, status, results, pages);
        async function load(page = 1) {
          abort?.abort(); abort = new AbortController(); const current = ++sequence;
          status.textContent = t("loading"); results.replaceChildren(); pages.replaceChildren();
          results.setAttribute("aria-busy", "true");
          try {
            let data;
            if (root.loadOptions) data = await root.loadOptions(field, {search: search.value, page});
            else {
              const url = new URL(field.endpoint, location.href); url.searchParams.set("q", search.value); url.searchParams.set("page", page);
              const response = await fetch(url, {signal: abort.signal, credentials: "same-origin", headers: {Accept: "application/json"}});
              if (!response.ok || response.redirected) throw new Error("lookup");
              data = await response.json();
            }
            if (current !== sequence) return;
            results.removeAttribute("aria-busy");
            status.textContent = data.items.length ? "" : t("no_records");
            data.items.forEach((item) => {
              const option = button(item.label, "filter-field-option", () => {
                selected = item.key; relationLabel = item.label; showSelected(); updatePreview();
                results.querySelectorAll("button").forEach((node) => node.setAttribute("aria-pressed", String(node === option)));
                error.hidden = true;
              });
              option.setAttribute("aria-pressed", String(selected === item.key));
              const secondary = [item.description !== item.label ? item.description : '', item.identity ? 'ID: ' + item.identity : ''].filter(Boolean).join(' · ');
              if(secondary)option.append(element('span','filter-result-description',secondary));
              results.append(option);
            });
            if (page > 1) pages.append(button(t("previous"), "button secondary small", () => load(page - 1)));
            if (data.has_next) pages.append(button(t("next"), "button secondary small", () => load(page + 1)));
          } catch (err) {
            if (current !== sequence || err.name === "AbortError") return;
            results.removeAttribute("aria-busy"); status.textContent = t("failed");
            pages.append(button(t("retry"), "button secondary small", () => load(page)));
          }
        }
        let composing = false;
        search.addEventListener("compositionstart", () => {composing=true;stopLookup();});
        search.addEventListener("compositionend", () => {composing=false;stopLookup();timer=setTimeout(()=>load(),350);});
        search.addEventListener("input", () => { stopLookup(); if(!composing)timer = setTimeout(() => load(), 350); });
        load();
      }
      function submit(){
        const raw=rawValues(),op=operator.value;
        if(!['null','not_null','empty','not_empty'].includes(op)&&(!raw.length||raw.some((v,i)=>!v&&!(op==='on'&&i===1)))){showError(t('required'));(inputs.find(n=>!n.value)||inputs[0])?.focus();return;}
        if(inputs.some(n=>!n.checkValidity())){showError(t('invalid'));inputs.find(n=>!n.checkValidity())?.reportValidity();return;}
        if(op==='in'&&raw.length>100){showError(t('max_values'));return;}
        try{navigate(updateQuery(params(),condition,entries(field,op,raw)));}
        catch(err){if(err.message!=='conflict')throw err;showError(t('conflict'));}
      }
      operator.addEventListener('change',()=>{drafts=rawValues(currentOp);currentOp=operator.value;renderValues();});
      renderValues(true);
      const issues=condition?.parameters.map(name=>errors[name]).filter(Boolean);if(issues?.length)showError(issues.join(' '));
    }
    conditions.forEach(condition=>condition.parameters.forEach((name,i)=>{const input=element('input');input.type='hidden';input.name=name;input.value=condition.values[i];root.append(input);}));
    fallback.disabled=true;fallback.hidden=true;add.hidden=false;add.addEventListener('click',()=>menu());
    root.closest('.record-list').querySelectorAll('[data-filter-edit]').forEach(link=>{
      const condition=conditions[Number(link.dataset.filterEdit)],field=fields.find(f=>f.id===condition.id);
      link.hidden=false;link.previousElementSibling.hidden=true;link.setAttribute('aria-haspopup','dialog');
      if(condition.parameters.some(name=>errors[name]))link.classList.add('has-filter-error');
      link.addEventListener('click',e=>{e.preventDefault();menu(link,field,condition);});
    });
    root.dataset.filterReady='true';
    if(Object.keys(errors).length){const bad=conditions.find(c=>c.parameters.some(n=>errors[n]));if(bad)menu(add,fields.find(f=>f.id===bad.id),bad);if(errors.__all__||!bad){const alert=element('p','alert',errors.__all__||Object.values(errors).join(' '));alert.setAttribute('role','alert');root.append(alert);}}
  }
  window.QuiteAdmin=window.QuiteAdmin||{};
  window.QuiteAdmin.initFilters=()=>document.querySelectorAll('[data-filter-builder]:not([data-filter-ready])').forEach(init);
  window.QuiteAdmin.initFilters();
})();
