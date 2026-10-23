/* Browser-local controller profiles. These never assign network player ports. */
(function(root){'use strict';
 const actions=['A / South','B / East','X / West','Y / North','L bumper','R bumper','L trigger','R trigger','Select / View','Start / Menu','Left stick click','Right stick click','Up','Down','Left','Right'];
 const clone=v=>JSON.parse(JSON.stringify(v)), PREFIX='mayo.controller-profiles.v1', MAX=32;
 const gameKey=v=>typeof v==='string'&&/^sha256:[a-f0-9]{64}$/.test(v)?v:null;
 const deviceKey=pad=>typeof pad?.id==='string'?pad.id.slice(0,128):'Unknown controller';
 function sourceValid(s){return !!s&&typeof s==='object'&&!Array.isArray(s)&&((s.type==='button'&&Object.keys(s).length===2&&Number.isInteger(s.index)&&s.index>=0&&s.index<64)||(s.type==='axis'&&Object.keys(s).length===3&&Number.isInteger(s.index)&&s.index>=0&&s.index<16&&(s.sign===1||s.sign===-1)));}
 function valid(v){return !!v&&typeof v==='object'&&Object.keys(v).length===2&&typeof v.enabled==='boolean'&&Array.isArray(v.bindings)&&v.bindings.length===16&&v.bindings.every(list=>Array.isArray(list)&&list.length<=6&&list.every(sourceValid)&&new Set(list.map(JSON.stringify)).size===list.length);}
 function defaults(){const v={enabled:true,bindings:actions.map((_,index)=>[{type:'button',index}])};for(const [target,index,sign]of [[12,1,-1],[13,1,1],[14,0,-1],[15,0,1]])v.bindings[target].push({type:'axis',index,sign});return v;}
 function sanitize(pad){if(!pad)return null;return {id:deviceKey(pad),index:Number.isInteger(pad.index)?pad.index:0,buttons:Array.from(pad.buttons||[]).slice(0,64).map(v=>Math.max(0,Math.min(1,Number(typeof v==='number'?v:v?.value)||0))),axes:Array.from(pad.axes||[]).slice(0,16).map(v=>Math.max(-1,Math.min(1,Number(v)||0)))};}
 function neutral(pad){return !pad||pad.buttons.every(v=>v<.35)&&pad.axes.every(v=>Math.abs(v)<.35);}
 function label(s){return s.type==='button'?'Button '+s.index:'Axis '+s.index+(s.sign<0?' −':' +');}
 class Capture {
  constructor(){this.reset();}
  reset(){this.armed=false;this.previous=new Set();}
  sample(pad){const p=sanitize(pad);if(!p){this.reset();return null;}if(!this.armed){if(neutral(p))this.armed=true;return null;}const candidates=[];p.buttons.forEach((v,index)=>{if(v>=.6)candidates.push({type:'button',index});});p.axes.forEach((v,index)=>{if(Math.abs(v)>=.6)candidates.push({type:'axis',index,sign:v<0?-1:1});});if(!candidates.length)return null;this.armed=false;return candidates[0];}
 }
 // Hysteresis avoids axis chatter; callers retain one instance per physical controller.
 class Mapper {
  constructor(){this.held=new Map();this.blocked=true;}
  release(){this.held.clear();this.blocked=true;}
  sample(raw,profile=defaults()) {const p=sanitize(raw);if(!p)return null;const out={id:p.id,buttons:Array(17).fill(0),axes:Array(4).fill(0)};
   if(!valid(profile)||!profile.enabled){this.release();return out;}
   if(this.blocked){if(neutral(p))this.blocked=false;return out;}
   profile.bindings.forEach((list,target)=>{for(const s of list){const key=JSON.stringify(s),value=s.type==='button'?p.buttons[s.index]||0:(p.axes[s.index]||0)*s.sign;const down=value>=(this.held.get(key) ? .35 : .6);this.held.set(key,down);if(down)out.buttons[target]=1;}});
   // Opposed directions must never reach downstream navigation/gameplay together.
   for(const[a,b]of [[12,13],[14,15]])if(out.buttons[a]&&out.buttons[b])out.buttons[a]=out.buttons[b]=0;return out;
  }
 }
 function read(storage){try{const raw=storage?.getItem(PREFIX);if(!raw||raw.length>160000)return [];const v=JSON.parse(raw);if(v.schema!==1||!Array.isArray(v.profiles)||v.profiles.length>MAX)return [];return v.profiles.filter(p=>p&&typeof p.device==='string'&&p.device.length<=128&&(p.game===null||gameKey(p.game))&&Number.isSafeInteger(p.savedAt)&&p.savedAt>=0&&valid(p.value)).map(clone);}catch(_){return [];}}
 function load(storage,device,game){const rows=read(storage),key=gameKey(game);return clone(rows.find(p=>key&&p.device===device&&p.game===key)?.value||rows.find(p=>p.device===device&&p.game===null)?.value||defaults());}
 function save(storage,device,game,value){if(typeof device!=='string'||!device.length||device.length>128||game!==null&&!gameKey(game)||!valid(value))return false;try{const rows=read(storage).filter(p=>p.device!==device||p.game!==game);rows.unshift({device,game,value:clone(value),savedAt:Date.now()});storage.setItem(PREFIX,JSON.stringify({schema:1,profiles:rows.slice(0,MAX)}));return true;}catch(_){return false;}}
 const api={actions,clone,gameKey,deviceKey,sourceValid,valid,defaults,sanitize,neutral,label,Capture,Mapper,read,load,save,PREFIX};root.MayoControllerModel=api;if(typeof module==='object')module.exports=api;
})(typeof window==='object'?window:globalThis);
