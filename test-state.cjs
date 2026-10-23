'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/assets/state-store.js','utf8');
const id='s'+'a'.repeat(32),other='s'+'b'.repeat(32),MAX=8*1024*1024,CHUNK=32768;
function fixture({host=true,paused=false,started=true,core='fceumm',legacy=true,threads=false,threadSetting='disabled',bytes=new Uint8Array([1,2,3]),getError=false,loadError=false}={}){
 const messages=[],pauses=[],plays=[],loads=[],editing=[],timers=new Map(),timerDue=new Map(),events={};let count=0,now=0,frame=0;
 const engine={started,paused,config:{forceLegacyCores:legacy,threads},preGetSetting:()=>threadSetting,getCore:()=>core,pause(value){pauses.push(value);this.paused=true;},play(value){plays.push(value);this.paused=false;},gameManager:{getFrameNum(){return frame;},getState(){if(getError)throw Error();return bytes;},loadState(value){if(loadError)throw Error();loads.push(new Uint8Array(value));}}};
 const window={EJS_emulator:engine,BoogieNative:{postMessage:raw=>messages.push(JSON.parse(raw))},boogieSetEditing:value=>editing.push(value),boogieCheckpoint:value=>editing.push(value)};
 class ClockDate extends Date {static now(){return now;}}
 vm.runInNewContext(source,{window,location:{search:'?host='+(host?'1':'0')},URLSearchParams,Uint8Array,btoa,atob,Date:ClockDate,performance:{now:()=>now},setTimeout:(fn,ms=0)=>{timers.set(++count,fn);timerDue.set(count,now+ms);return count;},clearTimeout:key=>{timers.delete(key);timerDue.delete(key);},setInterval:fn=>{events.interval=fn;},addEventListener:(name,fn)=>events[name]=fn});
 function tick(ms=16,frames=1){now+=ms;if(!engine.paused)frame+=frames;const due=[...timers.keys()].filter(key=>timerDue.get(key)<=now);for(const key of due){const fn=timers.get(key);if(!fn)continue;timers.delete(key);timerDue.delete(key);fn();}}
 return {engine,messages,pauses,plays,loads,editing,timers,events,tick,polls:()=>[...timers].filter(([key])=>timerDue.get(key)-now<=16).map(([,fn])=>fn),command:window.boogieState,last:()=>messages.at(-1)};
}
test('host save copies core bytes, chunks exact order, waits finish and resumes only originally running game',()=>{
 const original=Uint8Array.from({length:CHUNK+5},(_,i)=>i%251),expected=new Uint8Array(original),f=fixture({bytes:original});
 f.command({op:'save',id});assert.deepEqual(f.last(),{type:'state-result',id,phase:'begin',size:CHUNK+5});assert.equal(f.engine.paused,true);
 original.fill(255);f.command({op:'next',id,index:0});let first=Buffer.from(f.last().data,'base64');assert.equal(first.length,CHUNK);assert.deepEqual(first,Buffer.from(expected.subarray(0,CHUNK)));
 f.command({op:'next',id,index:1});assert.deepEqual(Buffer.from(f.last().data,'base64'),Buffer.from(expected.subarray(CHUNK)));
 f.command({op:'next',id,index:2});assert.equal(f.last().phase,'end');assert.equal(f.engine.paused,true);assert.equal(f.plays.length,0);
 f.command({op:'finish',id});assert.equal(f.engine.paused,false);assert.deepEqual(f.plays,[true]);assert.equal(f.timers.size,0);assert.deepEqual(f.editing,[true,false]);
});
test('host load assembles bounded exact chunks and commits once before restoring pause',()=>{
 const f=fixture(),bytes=Uint8Array.from({length:CHUNK+7},(_,i)=>i%237);
 f.command({op:'load',id,size:bytes.length});assert.equal(f.last().phase,'ready');
 for(let index=0;index<2;index++){f.command({op:'append',id,index,data:Buffer.from(bytes.subarray(index*CHUNK,(index+1)*CHUNK)).toString('base64')});assert.equal(f.last().phase,'ack');assert.equal(f.last().index,index);}
 assert.equal(f.loads.length,0);f.command({op:'commit',id});assert.notEqual(f.last().phase,'loaded');assert.deepEqual(f.loads[0],bytes);assert.equal(f.engine.paused,false);
 f.tick();assert.notEqual(f.last().phase,'loaded');f.tick();assert.equal(f.last().phase,'loaded');assert.equal(f.engine.paused,false);assert.equal(f.timers.size,0);
 f.command({op:'commit',id});assert.equal(f.loads.length,1);
});
test('paused load briefly runs a neutral core until two advancing polls then restores pause',()=>{
 const f=fixture({paused:true});f.command({op:'load',id,size:1});f.command({op:'append',id,index:0,data:'AQ=='});f.command({op:'commit',id});
 assert.equal(f.engine.paused,false);assert.deepEqual(f.editing,[true]);assert.equal(f.last().phase,'ack');
 f.tick(16,0);assert.notEqual(f.last().phase,'loaded');f.tick(16,50);assert.notEqual(f.last().phase,'loaded');f.tick(16,0);assert.notEqual(f.last().phase,'loaded');
 f.tick();assert.equal(f.last().phase,'loaded');assert.equal(f.engine.paused,true);assert.deepEqual(f.editing,[true,false]);assert.equal(f.timers.size,0);
});
test('load polling times out without frame progress and restores the original pause state',()=>{
 for(const paused of [true,false]){const f=fixture({paused});f.command({op:'load',id,size:1});f.command({op:'append',id,index:0,data:'AQ=='});f.command({op:'commit',id});
  for(let i=0;i<130&&f.last().phase!=='error';i++)f.tick(16,0);
  assert.equal(f.last().phase,'error');assert.equal(f.engine.paused,paused);assert.equal(f.timers.size,0);assert.deepEqual(f.editing,[true,false]);
 }
});
test('cancelled or departed load polls cannot complete or release a newer operation',()=>{
 for(const departure of ['cancel','pagehide']){const f=fixture({paused:true});f.command({op:'load',id,size:1});f.command({op:'append',id,index:0,data:'AQ=='});f.command({op:'commit',id});
  const stale=f.polls();assert.equal(stale.length,1);if(departure==='cancel')f.command({op:'cancel',id});else f.events.pagehide();
  assert.equal(f.engine.paused,true);f.command({op:'save',id:other});const before=f.messages.length;
  for(const callback of stale)callback();f.tick(32);
  assert.equal(f.messages.length,before);assert.equal(f.last().phase,'begin');assert.equal(f.last().id,other);assert.equal(f.engine.paused,true);assert.equal(f.timers.size,1);
  f.command({op:'finish',id:other});assert.equal(f.engine.paused,true);assert.equal(f.timers.size,0);
 }
});
test('paused games remain paused after finish, cancel, serialization/load errors, timeout and departure',()=>{
 for(const action of ['finish','cancel','save-error','load-error','timeout','pagehide']){
  const f=fixture({paused:true,getError:action==='save-error',loadError:action==='load-error'});
  if(action==='load-error'){f.command({op:'load',id,size:1});f.command({op:'append',id,index:0,data:'AQ=='});f.command({op:'commit',id});}
  else{f.command({op:'save',id});if(action==='timeout')[...f.timers.values()][0]();else if(action==='pagehide')f.events.pagehide();else if(action!=='save-error')f.command({op:action,id});}
  assert.equal(f.engine.paused,true,action);assert.equal(f.plays.length,0,action);assert.equal(f.timers.size,0,action);
 }
});
test('guest, malformed identifiers and unready/wrong cores cannot access checkpoints',()=>{
 for(const settings of [{host:false},{started:false},{core:'other'},{legacy:false},{threads:true},{threadSetting:'enabled'}]){
  const f=fixture(settings);f.command({op:'save',id});assert.equal(f.pauses.length,0);assert.equal(f.loads.length,0);assert.ok(f.messages.every(m=>m.phase!=='begin'));
 }
 const f=fixture();for(const value of [null,{}, {op:'save',id:other.toUpperCase()},{op:'save',id:'../bad'},{op:'save',id:7}])f.command(value);
 assert.equal(f.messages.length,0);assert.equal(f.pauses.length,0);
});
test('stale identifiers and competing requests cannot advance or cancel another active operation',()=>{
 const f=fixture();f.command({op:'save',id});
 for(const op of ['next','append','commit','cancel','finish'])f.command({op,id:other,index:0,data:'AQ=='});
 f.command({op:'save',id:other});assert.equal(f.last().phase,'error');assert.equal(f.engine.paused,true);
 f.command({op:'next',id,index:0});assert.equal(f.last().phase,'chunk');assert.equal(f.last().index,0);
 f.command({op:'cancel',id});assert.equal(f.engine.paused,false);
});
test('wrong chunk order, malformed base64 and partial commits fail without loading game state',()=>{
 for(const bad of [{op:'append',index:1,data:'AQ=='},{op:'append',index:0,data:'!!!='},{op:'append',index:0,data:''},{op:'append',index:0,data:'A'.repeat(43696)},{op:'append',index:0,data:'AQI='},{op:'commit'}]){
  const f=fixture();f.command({op:'load',id,size:1});f.command({id,...bad});assert.equal(f.last().phase,'error');assert.equal(f.loads.length,0);assert.equal(f.engine.paused,false);assert.equal(f.timers.size,0);
 }
 const f=fixture();f.command({op:'save',id});f.command({op:'next',id,index:1});assert.equal(f.last().phase,'error');assert.equal(f.engine.paused,false);
});
test('checkpoint sizes reject empty, negative, oversized and fractional data and allow exact maximum',()=>{
 for(const size of [0,-1,MAX+1,1.5,NaN,Infinity,'2']){const f=fixture();f.command({op:'load',id,size});assert.equal(f.last().phase,'error');assert.equal(f.engine.paused,false);assert.equal(f.loads.length,0);}
 for(const bytes of [new Uint8Array(0),new Uint8Array(MAX+1),[1,2,3]]){const f=fixture({bytes});f.command({op:'save',id});assert.equal(f.last().phase,'error');assert.equal(f.engine.paused,false);}
 const f=fixture();f.command({op:'load',id,size:MAX});assert.equal(f.last().phase,'ready');f.command({op:'cancel',id});assert.equal(f.engine.paused,false);
});
test('running game resumes after operation failure, timeout and pagehide; readiness event contains no data',()=>{
 for(const action of ['failure','timeout','pagehide']){const f=fixture();f.command({op:'save',id});if(action==='failure')f.command({op:'next',id,index:99});else if(action==='timeout')[...f.timers.values()][0]();else f.events.pagehide();assert.equal(f.engine.paused,false);assert.equal(f.plays.length,1);}
 const f=fixture();f.events.interval();f.events.interval();assert.deepEqual(f.messages,[{type:'state-result',id:'',phase:'core-ready'}]);
});
