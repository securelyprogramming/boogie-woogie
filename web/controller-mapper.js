/* Browser Gamepad API editor. Network roles and virtual ports remain host-owned. */
(() => {'use strict';
 const M=window.MayoControllerModel;if(!M)return;
 const $=id=>document.getElementById(id), neutral=()=>[null,null,null,null];
 let session={active:false,approved:false,role:'',port:null},game=null,title='',pads=[],draft=null,selected='',capture=null,wizard=null,editing=false,lastRoster=0,returnFocus=null,mappingGeneration=0;
 const profiles=new Map(),resolved=new Map(),mappers=new Map(),hostRequests=new Set();let lastHostRequest=-Infinity;let localStore=null;try{localStore=localStorage;}catch(_){}
 const el=(tag,text,attrs={})=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
 const button=(text,fn)=>{const n=el('button',text,{type:'button'});n.onclick=()=>{if(editing)fn();};return n;};
 const dialog=el('dialog',undefined,{id:'controllerMapperDialog','aria-labelledby':'controllerMapperTitle'});document.body.append(dialog);
 const heading=el('h2','Controllers',{id:'controllerMapperTitle'}),intro=el('p'),tabs=el('div',undefined,{class:'mapper-tabs'}),content=el('div'),notice=el('p','',{role:'status','aria-live':'polite'}),footer=el('div',undefined,{class:'mapper-actions'});
 dialog.append(heading,intro,tabs,content,notice,footer);
 const key=p=>M.deviceKey(p)+'#'+p.index;
 const chosen=()=>pads.find(p=>key(p)===selected);
 const roleLabel=()=>session.role==='spectator'?'Watch only':session.port===0?'Shared player 1':session.port===1?'Player 2':'Waiting for host approval';
 const release=()=>{for(const mapper of mappers.values())mapper.release();window.boogieNativePads?.(neutral());window.dispatchEvent(new CustomEvent('boogie-mapper-editing',{detail:editing}));};
 function close(){if(!editing)return;editing=false;mappingGeneration++;capture=null;wizard=null;draft=null;release();window.boogieSetEditing?.(false);if(dialog.open)dialog.close();returnFocus?.focus?.();}
 function scopeProfile(p){const k=key(p);if(profiles.has(k))return profiles.get(k);if(!resolved.has(k)){while(resolved.size>=32)resolved.delete(resolved.keys().next().value);resolved.set(k,M.load(localStore,M.deviceKey(p),game));}return resolved.get(k);}
 function current(){return draft||M.defaults();}
 function setCapture(action,append=false){if(!editing||dialog.dataset.page!=='mapping')return;if(!chosen()){notice.textContent='Connect a controller, then press a button once to let the browser discover it.';return;}capture={action,append,detector:new M.Capture()};notice.textContent='Release all buttons and center the sticks. Then press '+M.actions[action]+'. Esc cancels capture.';}
 function renderRows(){content.replaceChildren();const token=++mappingGeneration,draftAtRender=draft,selectedAtRender=selected;
  const guard=fn=>()=>{if(editing&&dialog.dataset.page==='mapping'&&mappingGeneration===token&&draft===draftAtRender&&selected===selectedAtRender)fn();};
  const b=(text,fn)=>button(text,guard(fn));
  const label=el('label','Physical controller '),select=el('select',undefined,{'aria-label':'Physical controller'});
  for(const p of pads){const option=el('option',M.deviceKey(p)+' · browser index '+p.index,{value:key(p)});option.selected=key(p)===selected;select.append(option);}
  if(!pads.length){select.append(el('option','No controller discovered'));select.disabled=true;}
  select.onchange=guard(()=>{selected=select.value;draft=M.clone(scopeProfile(chosen()));capture=null;wizard=null;renderRows();});label.append(select);content.append(label);
  content.append(el('p','All enabled local controllers merge into your approved '+roleLabel()+'. Identical controller models share saved device profiles; session changes can differ by browser index.'));
  if(!chosen()){content.append(el('p','Connect a controller and press any button. The browser only exposes controllers after a physical interaction. Keyboard play continues to use the documented keys.'));return;}
  const enabled=el('input',undefined,{type:'checkbox'});enabled.checked=current().enabled;enabled.onchange=guard(()=>{draft.enabled=enabled.checked;});const enabledLabel=el('label',' Use this controller');enabledLabel.prepend(enabled);content.append(enabledLabel);
  const wizardButton=b('Guided setup · every button',()=>{wizard={index:0};setCapture(0);});content.append(wizardButton,b('Skip guided action',()=>{if(!wizard||!capture)return;if(++wizard.index<M.actions.length)setCapture(wizard.index);else{wizard=null;capture=null;notice.textContent='Guided setup finished. Save to apply the draft.';}}),b('Cancel capture',()=>{capture=null;wizard=null;notice.textContent='Capture canceled. Your draft is unchanged.';}));
  const rows=el('div',undefined,{class:'mapper-rows'});
  M.actions.forEach((name,action)=>{const row=el('div',undefined,{class:'mapper-row'}),bindings=current().bindings[action];row.append(el('strong',name),el('span',bindings.length?bindings.map(M.label).join(' + '):'Unassigned'));
   const replace=b('Set',()=>{wizard=null;setCapture(action,false);}),add=b('+ Add',()=>{wizard=null;setCapture(action,true);}),clear=b('Clear',()=>{draft.bindings[action]=[];capture=null;wizard=null;renderRows();});
   replace.setAttribute('aria-label','Set '+name);add.setAttribute('aria-label','Add another input for '+name);clear.setAttribute('aria-label','Clear '+name);row.append(replace,add,clear);rows.append(row);});content.append(rows);
  const controls=el('div',undefined,{class:'mapper-actions'}),scope=el('select',undefined,{'aria-label':'Save mapping scope'});
  for(const[value,text]of [['session','This session'],['game','This game + this controller model'],['device','This controller model · all games']]){const option=el('option',text,{value});option.disabled=value==='game'&&!game;scope.append(option);}
  scope.value='session';
  controls.append(scope,b('Save mapping',()=>{const p=chosen();if(!p||!M.valid(draft))return;capture=null;wizard=null;const which=scope.value;
   if(which==='game'&&!game){notice.textContent='Wait for the host to identify this game.';return;}
   if(which!=='session'&&!M.save(localStore,M.deviceKey(p),which==='game'?game:null,draft)){notice.textContent='Storage unavailable or full. Choose This session to keep your mapping in memory.';return;}
   // Replace this controller's session override, leaving other indices' session choices intact.
   if(which!=='session')profiles.delete(key(p));
   resolved.clear();if(which==='session')profiles.set(key(p),M.clone(draft));
   while(profiles.size>32)profiles.delete(profiles.keys().next().value);release();notice.textContent='Saved '+(which==='session'?'for this session.':which==='game'?'for this game on this browser.':'for this controller model on this browser.');
  }),b('Reset draft',()=>{capture=null;wizard=null;draft=M.defaults();renderRows();notice.textContent='Default mapping is a draft. Save to apply it.';}));content.append(controls);
 }
 function roster(){content.replaceChildren();content.append(el('h3','Playing '+(title||'the host game')),el('p',pads.length+' physical controller'+(pads.length===1?'':'s')+' available to this browser (up to four). '+roleLabel()+'.'));
  const list=el('ul');for(const p of pads)list.append(el('li',M.deviceKey(p)+' · index '+p.index+' → '+(scopeProfile(p).enabled?roleLabel():'disabled locally')));if(!pads.length)list.append(el('li','No physical controller discovered. Touch / keyboard input uses the same host-approved player slot.'));content.append(list);
  const slots=el('ul');for(const text of ['Player 1 — host local controls; approved shared guests may also control it','Player 2 — one host-approved remote player','Players 3 and 4 — unavailable in this preview'])slots.append(el('li',text));content.append(el('h3','Virtual controller assignments'),slots,el('p','This browser cannot see the host’s physical device inventory or the full peer roster. The list above describes available slots; it does not claim each slot is occupied.'),el('p','To change who controls a player, leave and request that role again. The host must approve the new assignment. Mappings only change your local inputs; they cannot claim another player’s port.'));
  content.append(button('Remap this browser’s controller',()=>show('mapping')));content.lastChild.disabled=session.role==='spectator';
 }
 function show(page='mapping'){if(!session.active||!session.approved)return;if(page==='mapping'&&session.role==='spectator')return;
  if(!editing){window.boogieBackdrop?.close?.();window.boogieLayout?.cancel();window.boogieVideoPanel?.close();returnFocus=document.activeElement;editing=true;release();window.boogieSetEditing?.(true);dialog.showModal();}
  capture=null;wizard=null;dialog.dataset.page=page;heading.textContent=page==='roster'?'Players & controllers':'Your '+roleLabel()+' controls';intro.textContent='This device controls '+roleLabel()+'. Its mappings stay on this device. '+(title||'Game identity pending.');tabs.replaceChildren(button('Controls',()=>show('mapping')),button('Players',()=>show('roster')));tabs.firstChild.disabled=session.role==='spectator';footer.replaceChildren(button('Done',close));notice.textContent='Changes apply only after Save mapping. Session overrides take priority, followed by this game, then device defaults.';
  if(!pads.some(p=>key(p)===selected)){selected=pads[0]?key(pads[0]):'';draft=null;}if(!draft)draft=chosen()?M.clone(scopeProfile(chosen())):null;if(page==='roster')roster();else renderRows();
 }
 dialog.addEventListener('cancel',e=>{e.preventDefault();if(capture){capture=null;wizard=null;notice.textContent='Capture canceled. Your draft is unchanged.';}else close();});
 window.addEventListener('blur',()=>{capture=null;wizard=null;release();if(editing)notice.textContent='Window lost focus. Capture canceled; inputs released.';});
 document.addEventListener('visibilitychange',()=>{if(document.hidden){capture=null;wizard=null;release();}});
 window.addEventListener('pagehide',close);
 if($('controllerMapper'))$('controllerMapper').onclick=()=>show('mapping');if($('controllerRoster'))$('controllerRoster').onclick=()=>show('roster');
 window.boogieControllerMapper={open:show,close,editing:()=>editing,
  hostRequest(request){
   if(!session.active||!session.approved||session.role==='spectator'||!M.gameKey(game)||request?.gameKey!==game||request?.role!==session.role||request?.port!==session.port||typeof request?.requestId!=='string'||!(/^[a-f0-9]{32}$/.test(request.requestId)))return false;
   const at=performance.now();if(hostRequests.has(request.requestId)||at-lastHostRequest<2000)return false;
   hostRequests.add(request.requestId);while(hostRequests.size>32)hostRequests.delete(hostRequests.values().next().value);lastHostRequest=at;
   if(editing){intro.textContent='Host invited this device to set up '+roleLabel()+'. Your current draft and capture remain unchanged.';return true;}
   if(window.boogieLayout?.editing?.()||$('videoPanel')&&!$('videoPanel').hidden){if($('layoutNotice'))$('layoutNotice').textContent='Host invited your '+roleLabel()+' controller setup. Finish this editor, then choose Map controls.';return true;}
   show('mapping');intro.textContent='Host invited this device to set up '+roleLabel()+'. Other devices edit their own mappings independently.';return true;
  },setGame(k,name){const next=M.gameKey(k);title=typeof name==='string'?name.slice(0,80):'';if(next===game)return;game=next;draft=null;resolved.clear();release();if(editing)show(dialog.dataset.page);},
  resetSession(){close();profiles.clear();resolved.clear();mappers.clear();hostRequests.clear();lastHostRequest=-Infinity;game=null;title='';pads=[];session={active:false,approved:false,role:'',port:null};},
  setSession(value){const previous=session;session={active:value?.active===true,approved:value?.approved===true,role:value?.role,port:value?.port};if(!session.active||!session.approved||previous.approved&&(previous.role!==session.role||previous.port!==session.port)){close();release();}for(const id of ['controllerMapper','controllerRoster'])if($(id)){$(id).hidden=!session.active||!session.approved;$(id).disabled=id==='controllerMapper'&&session.role==='spectator';}},
  sample(raw){const next=Array.from(raw||[]).filter(p=>p&&p.connected!==false).slice(0,4).map(M.sanitize),ids=new Set(next.map(key));
   for(const [id,mapper]of mappers)if(!ids.has(id)){mapper.release();mappers.delete(id);if(selected===id){capture=null;wizard=null;selected='';draft=null;notice.textContent='Controller disconnected. Its held inputs were released.';}}
   const changed=pads.map(key).join('\n')!==next.map(key).join('\n');pads=next;
   if(editing&&changed){if(!selected&&pads.length){selected=key(pads[0]);draft=M.clone(scopeProfile(pads[0]));}capture=null;wizard=null;if(dialog.dataset.page==='roster')roster();else renderRows();}
   if(editing&&capture){const found=capture.detector.sample(chosen());if(found){const {action,append}=capture;let list=append?draft.bindings[action].slice():[];if(!list.some(v=>JSON.stringify(v)===JSON.stringify(found))&&list.length<6)list.push(found);draft.bindings[action]=list;capture=null;
    if(wizard&&++wizard.index<M.actions.length){const target=wizard.index;renderRows();setCapture(target);}else{wizard=null;renderRows();notice.textContent='Captured '+M.label(found)+'. Save your mapping to apply it.';}}}
   if(editing&&dialog.dataset.page==='roster'&&performance.now()-lastRoster>1000){lastRoster=performance.now();roster();}
   const output=pads.map(p=>{const id=key(p);if(!mappers.has(id))mappers.set(id,new M.Mapper());const mapper=mappers.get(id);if(editing||document.hidden||!session.approved||session.role==='spectator'){mapper.release();return {id:p.id,buttons:Array(17).fill(0),axes:Array(4).fill(0)};}return mapper.sample(p,scopeProfile(p));});while(output.length<4)output.push(null);return output;
  }
 };
})();
