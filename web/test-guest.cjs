'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/guest.js','utf8');
const flush=()=>new Promise(r=>setImmediate(r));
function fixture({fragment='',joinDelay=false,approval=null,iconsInitial=false}={}){
 const elements=new Map(),calls=[],events=[],history=[],storage=[],touches=[],winEvents={},docEvents={},frames=[],rawPads=[];let resolveJoin;
 const element=id=>{if(!elements.has(id))elements.set(id,{value:id==='joinRole'?'player':'',hidden:false,textContent:'',disabled:false,attrs:{},classes:{},listeners:{},addEventListener(n,f){this.listeners[n]=f;},querySelector(){return {disabled:false};},setAttribute(k,v){this.attrs[k]=v;},querySelectorAll(){return [...elements.values()].filter(v=>v!==this&&v.id!=='guest');},classList:{toggle(k,v){elements.get(id).classes[k]=v;}}});return elements.get(id);};
 let first=true;
 const response=value=>new Response(JSON.stringify(value),{status:200});
 const fetch=async(route,opts)=>{calls.push({route,opts});
  if(route==='/client-info')return response({protocolVersion:1,roles:['player','player2','spectator'],ports:{player:0,player2:1,spectator:null}});
  if(route==='/join'){if(joinDelay)return new Promise(r=>{resolveJoin=r;});return response({peerId:'guestFixture',peerCredential:'x'.repeat(32)});}
  if(route.startsWith('/events')){if(first&&approval){first=false;return response({events:[{id:1,type:'approved',peerId:'guestFixture',...approval}]});}return new Promise(()=>{});}
  return response({left:true});};
 const window={isSecureContext:true,boogieEvent:v=>events.push(v),boogieNativePads(){},boogieTouch:(...v)=>touches.push(v),addEventListener(n,f){(winEvents[n]??=[]).push(f);},dispatchEvent(e){for(const fn of winEvents[e.type]||[])fn(e);}};
 const sandbox={window,document:{hidden:false,getElementById:element,addEventListener(n,f){(docEvents[n]??=[]).push(f);}},navigator:{getGamepads:()=>rawPads},location:{protocol:'https:',hash:fragment,pathname:'/'},history:{replaceState:(...args)=>history.push(args)},localStorage:{getItem:key=>key==='mayo.toolbar.icons-only'&&iconsInitial?'true':null,setItem:(...args)=>storage.push(args)},URLSearchParams,TextEncoder,TextDecoder,Uint8Array,AbortController,Response,Event,fetch,requestAnimationFrame(fn){frames.push(fn);},setTimeout(){return 1;},clearTimeout(){}};
 vm.runInNewContext(source,sandbox);return {window,element,calls,events,history,storage,touches,winEvents,docEvents,frames,rawPads,completeJoin:()=>resolveJoin(response({peerId:'guestFixture',peerCredential:'y'.repeat(32)}))};
}
test('fragment consumed, no automatic join, no invitation in URL or persistent storage',async()=>{
 const f=fixture({fragment:'#invite=fragment-secret'});await flush();
 assert.equal(f.element('invitation').value,'fragment-secret');assert.equal(f.history[0][2],'/');assert.equal(f.calls.length,1);assert.equal(f.calls[0].route,'/client-info');assert.equal(f.storage.length,0);
 f.element('displayName').value='Guest';await f.element('joinForm').listeners.submit({preventDefault(){}});await flush();
 assert.equal(f.element('invitation').value,'');const join=f.calls.find(c=>c.route==='/join');assert.equal(JSON.parse(join.opts.body).invite,'fragment-secret');assert.equal(join.opts.headers.Authorization,undefined);
 assert.ok(f.calls.every(c=>!c.route.includes('fragment-secret')));assert.equal(f.storage.length,0);assert.ok(f.events.some(e=>e.type==='session'&&e.host===false));
});
test('authoritative player2 port flows into session; stale join leaves its own credential',async()=>{
 const f=fixture({approval:{role:'player2',port:1}});await flush();f.element('invitation').value='fixture-invite';f.element('displayName').value='Guest';f.element('joinRole').value='player2';await f.element('joinForm').listeners.submit({preventDefault(){}});await flush();
 assert.ok(f.events.some(e=>e.type==='peer-approved'&&e.role==='player2'&&e.port===1));
 const s=fixture({joinDelay:true});await flush();s.element('invitation').value='fixture-invite';s.element('displayName').value='Guest';const promise=s.element('joinForm').listeners.submit({preventDefault(){}});await flush();s.element('leaveSession').onclick();s.completeJoin();await promise;await flush();
 assert.equal(s.events.some(e=>e.type==='session'),false);const leave=s.calls.find(c=>c.route==='/leave');assert.equal(leave.opts.headers.Authorization,'Bearer '+'y'.repeat(32));
});
test('mismatched approved player2 port fails closed and revokes current peer',async()=>{
 const f=fixture({approval:{role:'player2',port:0}});await flush();f.element('invitation').value='fixture-invite';f.element('displayName').value='Guest';f.element('joinRole').value='player2';await f.element('joinForm').listeners.submit({preventDefault(){}});await flush();
 assert.equal(f.events.some(e=>e.type==='peer-approved'),false);assert.ok(f.events.some(e=>e.type==='stop'));assert.ok(f.calls.some(c=>c.route==='/leave'));
});

async function join(f, role='player') { await flush();f.element('invitation').value='fixture-invite';f.element('displayName').value='Guest';f.element('joinRole').value=role;await f.element('joinForm').listeners.submit({preventDefault(){}});await flush(); }
const key=(code,target=null)=>({code,target,preventDefault(){this.prevented=true;}});
function emit(f,name,e) { for(const fn of f.winEvents[name]||[])fn(e); }
test('keyboard controls require approval and release on focus loss; pointer overlap preserves holds',async()=>{
 const f=fixture({approval:{role:'player',port:0}});f.element('videoPanel').hidden=true;
 emit(f,'keydown',key('ArrowRight'));assert.equal(f.touches.length,0);
 await join(f);emit(f,'keydown',key('ArrowRight'));assert.deepEqual(f.touches.at(-1),[7,true]);
 f.window.boogieTouch(7,true);emit(f,'keyup',key('ArrowRight'));assert.deepEqual(f.touches.at(-1),[7,true]);
 f.window.boogieTouch(7,false);assert.deepEqual(f.touches.at(-1),[7,false]);
 emit(f,'keydown',key('KeyZ'));emit(f,'blur',{});assert.deepEqual(f.touches.at(-1),[8,false]);
 const formTarget={closest:selector=>selector.includes('input,')?{}:null};emit(f,'keydown',key('KeyZ',formTarget));assert.deepEqual(f.touches.at(-1),[8,false]);
 f.window.boogieLayout={editing:()=>true};emit(f,'keydown',key('KeyZ'));assert.deepEqual(f.touches.at(-1),[8,false]);
});
test('spectator cannot use keyboard or hide controls; player hide retains reachable Show button and leave clears editor identity/audio',async()=>{
 const s=fixture({approval:{role:'spectator',port:null}});s.element('videoPanel').hidden=true;await join(s,'spectator');
 emit(s,'keydown',key('KeyZ'));assert.equal(s.touches.length,0);assert.equal(s.element('toggleControls').hidden,true);
 const f=fixture({approval:{role:'player',port:0}});await join(f);let cancelled=0,released=0,game='old';
 f.window.boogieLayout={cancel(){cancelled++;},release(){released++;},setGame(v){game=v;},setEnabled(){}};
 f.element('toggleControls').onclick();assert.equal(f.element('toggleControls').hidden,false);assert.equal(f.element('toggleControls').textContent,'Show controls');assert.equal(cancelled,1);assert.equal(released,1);assert.deepEqual(f.storage[0],['mayo.controls.visible','false']);
 f.element('enableAudio').hidden=true;f.element('leaveSession').onclick();assert.equal(game,null);assert.equal(f.element('enableAudio').hidden,false);
});

test('controller mapper receives actual raw pads and only approved game metadata; leave clears session profiles',async()=>{
 const f=fixture({approval:{role:'player2',port:1}}),sessions=[],games=[],inputs=[];let cleared=0;
 f.window.boogieControllerMapper={setSession:v=>sessions.push(v),setGame:(...v)=>games.push(v),resetSession(){cleared++;},sample:p=>{inputs.push(p);return [null,null,null,null];},editing:()=>false};
 f.window.BoogieNative.postMessage(JSON.stringify({type:'approved-metadata',gameKey:'sha256:'+'a'.repeat(64),gameTitle:'Before approval'}));assert.equal(games.length,0);
 await join(f,'player2');assert.ok(sessions.some(s=>s.approved&&s.port===1&&s.role==='player2'));
 const pad={id:'Actual controller',index:2,buttons:[{value:1}],axes:[.5]};f.rawPads.push(null,null,pad);f.frames.shift()();assert.equal(inputs[0][2],pad);
 f.window.BoogieNative.postMessage(JSON.stringify({type:'approved-metadata',gameKey:'sha256:'+'a'.repeat(64),gameTitle:'Test game'}));assert.deepEqual(games,[['sha256:'+'a'.repeat(64),'Test game']]);
 f.window.BoogieNative.postMessage(JSON.stringify({type:'approved-metadata',gameKey:'invalid',gameTitle:'Bad'}));assert.equal(games.length,1);
 f.element('leaveSession').onclick();assert.equal(cleared,1);assert.equal(sessions.at(-1).active,false);
});
test('mapper opening releases keyboard and pointer holds; capture prevents new gameplay keys',async()=>{
 const f=fixture({approval:{role:'player',port:0}});f.element('videoPanel').hidden=true;await join(f);emit(f,'keydown',key('KeyZ'));f.window.boogieTouch(7,true);
 emit(f,'boogie-mapper-editing',{detail:true});assert.deepEqual(f.touches.slice(-2),[[7,false],[8,false]]);
 f.window.boogieControllerMapper={editing:()=>true};const count=f.touches.length;emit(f,'keydown',key('KeyZ'));assert.equal(f.touches.length,count);
});

test('browser forwards mapping invites only to the current approved input player editor',async()=>{
 const f=fixture({approval:{role:'player2',port:1}}),requests=[];await join(f,'player2');f.window.boogieControllerMapper={hostRequest:r=>requests.push(r)};
 const message={type:'mapping-setup-request',role:'player2',port:1,gameKey:'sha256:'+'f'.repeat(64),requestId:'a'.repeat(32)};f.window.BoogieNative.postMessage(JSON.stringify({...message,port:0}));assert.equal(requests.length,0);f.window.BoogieNative.postMessage(JSON.stringify(message));assert.equal(requests.length,1);assert.equal(f.element('controllerMapper').textContent,'Map Player 2');
 const s=fixture({approval:{role:'spectator',port:null}});await join(s,'spectator');s.window.boogieControllerMapper={hostRequest:r=>requests.push(r)};s.window.BoogieNative.postMessage(JSON.stringify({...message,role:'spectator',port:null}));assert.equal(requests.length,1);
});
test('icons-only toolbar preference keeps dynamic accessible labels and is locally persisted',async()=>{
 const f=fixture({approval:{role:'player2',port:1},iconsInitial:true});await join(f,'player2');assert.equal(f.element('guest').classes['toolbar-icons-only'],true);assert.equal(f.element('controllerMapper').attrs['aria-label'],'Map Player 2');assert.equal(f.element('controllerMapper').attrs.title,'Map Player 2');assert.equal(f.element('toolbarLabels').textContent,'Show labels');f.element('toolbarLabels').onclick();assert.equal(f.element('guest').classes['toolbar-icons-only'],false);assert.equal(f.element('toolbarLabels').textContent,'Icons only');assert.deepEqual(f.storage.at(-1),['mayo.toolbar.icons-only','false']);
});
