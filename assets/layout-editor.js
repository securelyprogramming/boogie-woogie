(() => {'use strict';
 const M=window.MayoLayoutModel,board=document.getElementById('touchBoard'),panel=document.getElementById('layoutPanel'),message=document.getElementById('layoutMessage');
 const sizeForBoard=()=>Math.floor(Math.max(28,Math.min(62,board.clientWidth/8,board.clientHeight/3.3)));
 const factory=()=>M.consoleLayout(board.clientWidth,board.clientHeight,sizeForBoard());
 let game=null,enabled=true,editing=false,current=M.load(localStorage,null,M.defaults),draft=null,drag=null;
 const buttons=[...board.querySelectorAll('[data-control]')],held=new Map();
 const release=()=>{for(const action of new Set(held.values()))window.boogieTouch?.(action,false);held.clear();};
 function render(){board.classList.toggle('editing',editing);const value=editing?draft:current;for(const b of buttons){const size=sizeForBoard();b.style.width=size+'px';b.style.height=size+'px';let p=M.position(value[b.dataset.control],board.clientWidth,board.clientHeight,size);b.style.left=p.left+'px';b.style.top=p.top+'px';}board.classList.toggle('editing',editing);panel.hidden=!editing;document.getElementById('editLayout').hidden=!enabled||editing;document.getElementById('saveGameLayout').disabled=!game;}
 function edit(active){if(active&&!enabled)return;if(active)window.boogieVideoPanel?.close();release();drag=null;editing=active;window.boogieSetEditing?.(active);if(active){draft=M.copy(current);message.textContent=game?'Drag buttons. Choose this game or all games.':'Drag buttons. Game-specific save becomes available after host approval.';}else draft=null;render();}
 function save(all){release();if(!all&&!game)return;const ok=M.save(localStorage,all?null:game,draft);if(!ok){message.textContent='Could not save on this device. Your layout is still being edited.';return;}current=all?M.load(localStorage,game,factory()):M.copy(draft);edit(false);document.getElementById('layoutNotice').textContent=all?'Default saved. Existing game layouts stay unchanged.':'Layout saved for this game.';}
 window.boogieLayout={release,cancel:()=>edit(false),setEnabled(value){if(typeof value!=='boolean')return;enabled=value;if(!enabled)edit(false);else render();},refresh(){if(!editing)current=M.load(localStorage,game,factory());render();},setGame(key){let next=M.gameKey(key);if(next===game)return;release();if(editing)edit(false);game=next;current=M.load(localStorage,game,factory());render();},editing:()=>editing,debug:()=>({editing,gameKnown:!!game,controls:M.copy(editing?draft:current)})};
 for(const b of buttons){
  b.addEventListener('pointerdown',e=>{e.preventDefault();if(!enabled)return;b.setPointerCapture(e.pointerId);if(editing){drag={id:e.pointerId,button:b};move(e);return;}held.set(e.pointerId,Number(b.dataset.action));window.boogieTouch?.(Number(b.dataset.action),true);});
  b.addEventListener('pointermove',e=>{if(editing&&drag?.id===e.pointerId)move(e);});
  for(const name of ['pointerup','pointercancel','lostpointercapture'])b.addEventListener(name,e=>{e.preventDefault();if(drag?.id===e.pointerId)drag=null;const action=held.get(e.pointerId);held.delete(e.pointerId);if(action!==undefined&&![...held.values()].includes(action))window.boogieTouch?.(action,false);});
 }
 function move(e){let r=board.getBoundingClientRect(),b=drag.button,size=b.offsetWidth;draft[b.dataset.control]={x:M.clamp((e.clientX-r.left-size/2)/Math.max(1,r.width-size)),y:M.clamp((e.clientY-r.top-size/2)/Math.max(1,r.height-size))};render();}
 document.getElementById('editLayout').onclick=()=>edit(true);
 document.getElementById('saveGameLayout').onclick=()=>save(false);
 document.getElementById('saveDefaultLayout').onclick=()=>save(true);
 document.getElementById('resetLayout').onclick=()=>{release();draft=factory();message.textContent='Console layout restored in preview. Save to apply, or Cancel.';render();};
 document.getElementById('cancelLayout').onclick=()=>edit(false);
 window.addEventListener('resize',()=>{release();drag=null;if(!editing)current=M.load(localStorage,game,factory());render();});
 window.addEventListener('blur',release);document.addEventListener('visibilitychange',()=>{if(document.hidden)release();});
 render();
})();
