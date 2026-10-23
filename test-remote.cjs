'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(__dirname + '/assets/remote.js', 'utf8');
const zero = () => Array(16).fill(0);
function fixture({audio = false, guestVideo=false} = {}) {
  let clock = 1000;
  const timers = [], messages = [], effects = [], connections = [], winEvents = {}, docEvents = {},frameCallbacks=[];
  const videoTrack = {kind:'video',readyState:'live',stop(){this.readyState='ended';}};
  class Stream {
    constructor(tracks = []) { this.tracks = tracks; }
    addTrack(track) { this.tracks.push(track); }
    getTracks() { return this.tracks; }
    getVideoTracks() { return this.tracks.filter(t => t.kind === 'video'); }
    getAudioTracks() { return this.tracks.filter(t => t.kind === 'audio'); }
  }
  class PC {
    constructor() { this.connectionState='new'; this.signalingState='stable'; this.remoteDescription=null; this.ice=[]; connections.push(this); }
    addTrack() {}
    getSenders(){return [{track:{kind:'video'},getParameters:()=>({encodings:[{}]}),setParameters:async value=>{this.lastVideoParameters=value;}}];}
    createDataChannel(label, options) {
      this.channel = {label, options,readyState:'open',bufferedAmount:0,sent:[],send(data){this.sent.push(JSON.parse(data));},close(){this.readyState='closed';this.onclose?.();}};
      return this.channel;
    }
    async createOffer() { return {type:'offer',sdp:'test'}; }
    async createAnswer() { return {type:'answer',sdp:'test'}; }
    async setLocalDescription(sdp) { this.localDescription={...sdp,toJSON:()=>sdp}; }
    async setRemoteDescription(sdp) { this.remoteDescription=sdp; }
    async addIceCandidate(ice) { this.ice.push(ice); }
    close() { this.connectionState='closed'; }
  }
  let nativeFeeds = 0, publishedPads = null;
  const engine = {started:true,canvas:{width:256,height:240,captureStream:()=>new Stream([videoTrack])},gameManager:{functions:{simulateInput(...args){effects.push(args);}}}};
  if (audio) {
    const context = {createMediaStreamDestination:()=>({stream:new Stream([{kind:'audio',readyState:'live',stop(){}}])}),
      createAnalyser:()=>({fftSize:512,connect(){},disconnect(){},getFloatTimeDomainData(values){values[0]=.25;}})};
    engine.gameManager.Module = {AL:{currentCtx:{sources:{one:{gain:{context,connect(){},disconnect(){}}}}}}};
  }
  const video={muted:true,srcObject:null,play:()=>Promise.resolve(),pause(){},requestVideoFrameCallback(fn){frameCallbacks.push(fn);}},audioButton={};
  const document = {hidden:false,addEventListener:(name,fn)=>{docEvents[name]=fn;},getElementById:id=>guestVideo?(id==='remoteVideo'?video:id==='enableAudio'?audioButton:null):null};
  const window = {MayoBackdropModel:require('./assets/backdrop-model.js'),EJS_emulator:engine,BoogieNative:{postMessage:json=>messages.push(JSON.parse(json))},addEventListener:(name,fn)=>{winEvents[name]=fn;},emulatormayoGamepads(pads){nativeFeeds++;publishedPads=pads;}};
  const sandbox = {window,document,performance:{now:()=>clock},crypto:require('node:crypto').webcrypto,TextEncoder,RTCPeerConnection:PC,MediaStream:Stream,
    Uint8Array,Float32Array,Map,Set,console,setInterval:fn=>timers.push(fn)};
  vm.runInNewContext(source,sandbox);
  const tick = (ms=50) => {clock+=ms;timers.forEach(fn=>fn());};
  const session = (host=true,role='player',gameKey=null) => {window.boogieEvent({type:'session',selfId:host?'host':'guest1',host,role,gameKey,port:role==='player2'?1:role==='player'?0:null});tick();};
  const peer = (id='guest1',role='player') => {window.boogieEvent({type:'peer-approved',peerId:id,role,port:role==='player2'?1:role==='player'?0:null});tick();const pc=connections.at(-1);pc.channel.onopen();return pc;};
  const input = (pc,buttons,seq=0,extra={}) => pc.channel.onmessage({data:JSON.stringify({t:'input',nonce:pc.channel.sent.find(m=>m.t==='grant').nonce,seq,buttons,...extra})});
  return {window,tick,session,peer,input,connections,messages,effects,engine,winEvents,docEvents,frameCallbacks,video,document,get nativeFeeds(){return nativeFeeds;},get publishedPads(){return publishedPads;}};
}
test('shared input release preserves the other source and opposite directions neutralize',()=>{
  const f=fixture();f.session();const p=f.peer();const b=zero();b[8]=1;f.input(p,zero());f.input(p,b,1);
  f.engine.gameManager.functions.simulateInput(0,8,1);
  f.engine.gameManager.functions.simulateInput(0,8,0);
  assert.equal(f.window.boogieDebug().inputMask,256);
  f.input(p,zero(),2);assert.equal(f.window.boogieDebug().inputMask,0);
  const left=zero();left[6]=1;f.input(p,left,3);f.window.boogieTouch(7,true);
  assert.equal(f.window.boogieDebug().inputMask,0);
  f.window.boogieTouch(7,false);assert.equal(f.window.boogieDebug().inputMask,64);
});
test('spectators, unauthorized peers, invalid nonce, replay, oversized and hotkey inputs fail closed',()=>{
  const f=fixture();f.session();f.window.boogieEvent({type:'signal',peerId:'notApproved',offer:{type:'offer',sdp:'x'}});
  assert.equal(f.connections.length,0);
  const p=f.peer();f.input(p,zero(),0,{nonce:'bad'});f.input(p,zero(),0);f.input(p,zero(),0);
  f.input(p,Array(25).fill(1),1);f.input(p,zero(),1,{extra:'x'.repeat(512)});
  const s=f.peer('spectator1','spectator');const b=zero();b[8]=1;f.input(s,b);
  assert.equal(f.window.boogieDebug().acceptedInputs,1);assert.equal(f.window.boogieDebug().inputMask,0);
  assert.equal(f.window.boogieDebug().rejectedInputs,6);
});
test('stale disconnect and native focus release held remote inputs',()=>{
  const f=fixture();f.session();const p=f.peer();const b=zero();b[8]=1;
  f.input(p,zero());f.input(p,b,1);f.tick(501);assert.equal(f.window.boogieDebug().inputMask,0);assert.equal(f.window.boogieDebug().staleReleases,1);
  f.input(p,b,2);f.window.boogieEvent({type:'focus',active:false});assert.equal(f.window.boogieDebug().inputMask,0);
  f.input(p,b,3);assert.equal(f.window.boogieDebug().inputMask,0);
  f.window.boogieEvent({type:'focus',active:true});f.input(p,zero(),4);f.input(p,b,5);assert.equal(f.window.boogieDebug().inputMask,256);
  p.connectionState='disconnected';p.onconnectionstatechange();assert.equal(f.window.boogieDebug().inputMask,0);
});
test('native standard pad has one hold owner and neutral discovery reaches normal bridge',()=>{
  const f=fixture();f.session();const pad={id:'test',buttons:Array(17).fill(0),axes:[-1,0,0,0]};pad.buttons[0]=pad.buttons[1]=pad.buttons[9]=1;
  f.window.boogieNativePads([pad,null,null,null]);assert.equal(f.window.boogieDebug().inputMask,256+1+8+64);assert.equal(f.nativeFeeds,1);
  assert.equal(f.publishedPads[0].id,'test');assert.equal(f.publishedPads[0].buttons.some(Boolean),false);assert.equal(f.publishedPads[0].axes.some(Boolean),false);
  assert.equal(f.effects.some(([,action,value])=>action===9 && value===1),false);
  f.window.boogieNativePads([null,null,null,null]);assert.equal(f.window.boogieDebug().inputMask,0);
});
test('idempotent session keeps live peers and stop restores raw core function and releases input',()=>{
  const f=fixture();const raw=f.engine.gameManager.functions.simulateInput;f.session();const p=f.peer();const b=zero();b[8]=1;f.input(p,zero());f.input(p,b,1);
  f.session();assert.equal(f.window.boogieDebug().peers,1);assert.equal(f.window.boogieDebug().inputMask,256);
  f.window.boogieEvent({type:'stop'});assert.equal(f.window.boogieDebug().peers,0);assert.equal(f.window.boogieDebug().inputMask,0);
  assert.equal(f.engine.gameManager.functions.simulateInput,raw);assert.deepEqual(f.effects.at(-1),[0,8,0]);
});
test('new grants and host focus restoration quarantine held heartbeats until neutral then fresh press',()=>{
  const f=fixture();f.session();const p=f.peer();const held=zero();held[8]=1;
  f.input(p,held,0);assert.equal(f.window.boogieDebug().inputMask,0);
  f.input(p,held,1);assert.equal(f.window.boogieDebug().inputMask,0);
  f.input(p,zero(),2);f.input(p,held,3);assert.equal(f.window.boogieDebug().inputMask,256);
  f.window.boogieEvent({type:'focus',active:false});f.window.boogieEvent({type:'focus',active:true});
  f.input(p,held,4);f.tick(100);f.input(p,held,5);assert.equal(f.window.boogieDebug().inputMask,0);
  f.input(p,zero(),6);assert.equal(f.window.boogieDebug().inputMask,0);
  f.input(p,held,7);assert.equal(f.window.boogieDebug().inputMask,256);
});
test('audio without real connected game source is not reported as captured',()=>{
  const f=fixture();f.session();assert.equal(f.window.boogieDebug().videoTrack,true);assert.equal(f.window.boogieDebug().audioTrack,false);assert.equal(f.window.boogieDebug().audioSignalObserved,false);
  const a=fixture({audio:true});a.session();assert.equal(a.window.boogieDebug().audioTapConnected,true);assert.equal(a.window.boogieDebug().audioSignalObserved,true);
});
test('guest ICE is queued until remote offer and guest snapshot uses grant capability',async()=>{
  const f=fixture();f.session(false);f.window.boogieEvent({type:'signal',peerId:'host',candidate:{candidate:'test-candidate'}});
  const p=f.connections[0];assert.equal(p.ice.length,0);
  f.window.boogieEvent({type:'signal',peerId:'host',offer:{type:'offer',sdp:'test'}});
  await new Promise(resolve=>setImmediate(resolve));assert.equal(p.ice.length,1);
  const dc=p.createDataChannel('boogie-input',{});p.ondatachannel({channel:dc});
  dc.onmessage({data:JSON.stringify({t:'grant',nonce:'1'.repeat(32),role:'player',port:0})});
  f.tick(20);f.window.boogieTouch(8,true);assert.equal(dc.sent.at(-1).buttons[8],1);
  f.window.boogieEvent({type:'focus',active:false});assert.equal(dc.sent.at(-1).buttons[8],0);
});

test('role downgrade revokes player capability and held input',()=>{
 const f=fixture();f.session();const p=f.peer();f.input(p,zero());const b=zero();b[8]=1;f.input(p,b,1);
 f.window.boogieEvent({type:'peer-approved',peerId:'guest1',role:'spectator'});f.tick();
 assert.equal(f.window.boogieDebug().inputMask,0);assert.equal(p.connectionState,'closed');
 f.input(p,b,2);assert.equal(f.window.boogieDebug().inputMask,0);
 const replacement=f.connections.at(-1);replacement.channel.onopen();
 assert.equal(replacement.channel.sent.at(-1).role,'spectator');
 f.input(replacement,b,2);assert.equal(f.window.boogieDebug().inputMask,0);
});

test('input authority waits for game start before capturing initialized core callback',()=>{
 const f=fixture();f.engine.started=false;f.session();
 assert.equal(f.window.boogieDebug().coreReady,false);
 const applied=[];f.engine.gameManager.functions.simulateInput=(...args)=>applied.push(args);
 f.engine.started=true;f.tick();f.window.boogieTouch(3,true);
 assert.equal(f.window.boogieDebug().coreReady,true);assert.deepEqual(applied,[[0,3,1]]);
});
test('editing sends neutral, ignores touches and quarantines held native input until release',async()=>{
 const f=fixture();f.session(false);f.window.boogieEvent({type:'signal',peerId:'host',offer:{type:'offer',sdp:'test'}});await new Promise(r=>setImmediate(r));const p=f.connections[0],dc=p.createDataChannel('boogie-input',{});p.ondatachannel({channel:dc});dc.onmessage({data:JSON.stringify({t:'grant',nonce:'1'.repeat(32),role:'player',port:0})});
 f.window.boogieTouch(8,true);assert.equal(dc.sent.at(-1).buttons[8],1);f.window.boogieSetEditing(true);assert.equal(dc.sent.at(-1).buttons.some(Boolean),false);f.window.boogieTouch(8,true);assert.equal(dc.sent.at(-1).buttons.some(Boolean),false);
 const pad={buttons:Array(17).fill(0),axes:[0,0,0,0]};pad.buttons[0]=1;f.window.boogieNativePads([pad,null,null,null]);f.window.boogieSetEditing(false);assert.equal(dc.sent.at(-1).buttons.some(Boolean),false);f.window.boogieNativePads([pad,null,null,null]);assert.equal(dc.sent.at(-1).buttons.some(Boolean),false);pad.buttons[0]=0;f.window.boogieNativePads([pad,null,null,null]);pad.buttons[0]=1;f.window.boogieNativePads([pad,null,null,null]);assert.equal(dc.sent.at(-1).buttons[8],1);
});
test('approved game metadata contains only bounded display identity, not grant tokens',async()=>{
 const f=fixture();f.session(false);f.window.boogieEvent({type:'signal',peerId:'host',offer:{type:'offer',sdp:'test'}});await new Promise(r=>setImmediate(r));const p=f.connections[0],dc=p.createDataChannel('boogie-input',{});p.ondatachannel({channel:dc});dc.onmessage({data:JSON.stringify({t:'grant',nonce:'1'.repeat(32),role:'player',port:0,gameKey:'sha256:'+'a'.repeat(64),hostLabel:'Retroid',gameTitle:'NES game'})});const msg=f.messages.find(m=>m.type==='approved-metadata');assert.deepEqual(Object.keys(msg).sort(),['gameKey','gameTitle','hostLabel','type']);assert.equal(msg.hostLabel,'Retroid');
});

test('approved spectator quality affects its own sender only and cannot inject gameplay',async()=>{
 const f=fixture();f.session();const spectator=f.peer('watcher','spectator'),player=f.peer('guest2','player');spectator.connectionState=player.connectionState='connected';
 const nonce=spectator.channel.sent.find(v=>v.t==='grant').nonce;
 spectator.channel.onmessage({data:JSON.stringify({t:'quality',nonce,profile:'sharp'})});await new Promise(r=>setImmediate(r));
 assert.equal(spectator.lastVideoParameters.encodings[0].maxBitrate,2000000);assert.equal(spectator.lastVideoParameters.encodings[0].maxFramerate,30);assert.equal(spectator.lastVideoParameters.encodings[0].scaleResolutionDownBy,1);assert.equal(player.lastVideoParameters,undefined);
 f.tick(1100);spectator.channel.onmessage({data:JSON.stringify({t:'quality',nonce,profile:'arbitrary',maxBitrate:999999999})});await new Promise(r=>setImmediate(r));assert.equal(spectator.lastVideoParameters.encodings[0].maxBitrate,2000000);
 const b=zero();b[8]=1;f.input(spectator,b,1);assert.equal(f.window.boogieDebug().inputMask,0);
});

test('presented frame loop rejects replaced peers and excludes background intervals',async()=>{
 const f=fixture({guestVideo:true});f.session(false);f.window.boogieEvent({type:'signal',peerId:'host',offer:{type:'offer',sdp:'test'}});await new Promise(r=>setImmediate(r));const p=f.connections[0];p.ontrack({streams:[{getTracks:()=>[],getVideoTracks:()=>[],getAudioTracks:()=>[]}],track:{kind:'video'}});let frame=f.frameCallbacks.shift();frame(0,{presentedFrames:10});assert.equal(f.window.boogieDebug().videoFrames,1);
 f.winEvents.blur();f.tick(10000);frame=f.frameCallbacks.shift();frame(0,{presentedFrames:11});f.tick(10000);f.winEvents.focus();frame=f.frameCallbacks.shift();frame(0,{presentedFrames:12});assert.equal(f.window.boogieDebug().presentationFreezes,0);
 const old=f.frameCallbacks.shift();f.window.boogieEvent({type:'session',selfId:'guest1',host:false,role:'spectator'});f.window.boogieEvent({type:'signal',peerId:'host',offer:{type:'offer',sdp:'new'}});await new Promise(r=>setImmediate(r));let count=f.window.boogieDebug().videoFrames;old(0,{presentedFrames:100});assert.equal(f.window.boogieDebug().videoFrames,count);assert.equal(f.frameCallbacks.length,0);
});

test('dedicated player two owns only port one and cannot spoof player one',()=>{
 const f=fixture();f.session();const p=f.peer('second','player2');f.input(p,zero());
 const left=zero();left[6]=1;f.window.boogieTouch(7,true);f.input(p,left,1);
 assert.deepEqual(Array.from(f.window.boogieDebug().portMasks),[128,64,0,0]);
 assert.ok(f.effects.some(([port,action,value])=>port===1&&action===6&&value===1));
 f.input(p,zero(),2,{port:0});assert.deepEqual(Array.from(f.window.boogieDebug().portMasks),[128,64,0,0]);
 f.input(p,zero(),2);assert.deepEqual(Array.from(f.window.boogieDebug().portMasks),[128,0,0,0]);
});
test('player two slot is unique and disconnect releases its port without releasing host',()=>{
 const f=fixture();f.session();const p=f.peer('second','player2');f.input(p,zero());const held=zero();held[8]=1;f.input(p,held,1);f.window.boogieTouch(0,true);
 const count=f.connections.length;f.window.boogieEvent({type:'peer-approved',peerId:'third',role:'player2',port:1});f.tick();assert.equal(f.connections.length,count);
 f.window.boogieEvent({type:'peer-left',peerId:'second'});assert.deepEqual(Array.from(f.window.boogieDebug().portMasks),[1,0,0,0]);
 const next=f.peer('third','player2');f.input(next,zero());f.input(next,held,1);assert.equal(f.window.boogieDebug().portMasks[1],256);
});
test('player two guest accepts only its approved grant and uses unchanged snapshots',async()=>{
 const f=fixture();f.session(false,'player2');f.window.boogieEvent({type:'signal',peerId:'host',offer:{type:'offer',sdp:'p2'}});await new Promise(r=>setImmediate(r));const pc=f.connections[0],dc=pc.createDataChannel('boogie-input',{});pc.ondatachannel({channel:dc});
 dc.onmessage({data:JSON.stringify({t:'grant',nonce:'a'.repeat(32),role:'player2',port:0})});f.window.boogieTouch(8,true);assert.equal(dc.sent.filter(m=>m.t==='input').length,0);
 dc.onmessage({data:JSON.stringify({t:'grant',nonce:'b'.repeat(32),role:'player2',port:1})});f.window.boogieTouch(8,false);f.window.boogieTouch(8,true);assert.equal(dc.sent.at(-1).buttons[8],1);assert.equal(Object.hasOwn(dc.sent.at(-1),'port'),false);
});
test('host mapping editor releases local port while independent guest remains held',()=>{
 const f=fixture();f.session();const p=f.peer('second','player2');f.input(p,zero());const held=zero();held[8]=1;f.input(p,held,1);const pad={buttons:Array(17).fill(0),axes:[0,0,0,0]};pad.buttons[0]=1;f.window.boogieNativePads([pad,null,null,null]);
 f.window.boogieSetEditing(true);assert.deepEqual(Array.from(f.window.boogieDebug().portMasks),[0,256,0,0]);f.window.boogieNativePads([pad,null,null,null]);assert.equal(f.window.boogieDebug().portMasks[0],0);
 f.window.boogieSetEditing(false);f.window.boogieNativePads([pad,null,null,null]);assert.equal(f.window.boogieDebug().portMasks[0],0);pad.buttons[0]=0;f.window.boogieNativePads([pad,null,null,null]);pad.buttons[0]=1;f.window.boogieNativePads([pad,null,null,null]);assert.equal(f.window.boogieDebug().portMasks[0],256);
});
test('checkpoint releases all controller ports and rejects holds until checkpoint end and fresh neutral',()=>{
 const f=fixture();f.session();const p=f.peer('second','player2');f.input(p,zero());const held=zero();held[8]=1;f.input(p,held,1);f.window.boogieTouch(7,true);
 f.window.boogieCheckpoint(true);assert.deepEqual(Array.from(f.window.boogieDebug().portMasks),[0,0,0,0]);f.input(p,held,2);f.window.boogieTouch(7,true);f.engine.gameManager.functions.simulateInput(0,8,1);assert.deepEqual(Array.from(f.window.boogieDebug().portMasks),[0,0,0,0]);
 f.window.boogieCheckpoint(false);f.input(p,held,3);assert.equal(f.window.boogieDebug().portMasks[1],0);f.input(p,zero(),4);f.input(p,held,5);assert.equal(f.window.boogieDebug().portMasks[1],256);
});
test('new incoming track restores a reachable audio gesture after previous session enabled audio',async()=>{
 const f=fixture({guestVideo:true});f.session(false);f.window.boogieEvent({type:'signal',peerId:'host',offer:{type:'offer',sdp:'test'}});await new Promise(r=>setImmediate(r));
 const pc=f.connections.at(-1),audio=f.document.getElementById('enableAudio');
 pc.ontrack({track:{kind:'video'}});audio.onclick();await new Promise(r=>setImmediate(r));assert.equal(audio.hidden,true);assert.equal(f.video.muted,false);
 pc.ontrack({track:{kind:'audio'}});assert.equal(f.video.muted,true);assert.equal(audio.hidden,false);
 audio.onclick();await new Promise(r=>setImmediate(r));assert.equal(f.video.muted,false);
 f.window.boogieEvent({type:'stop'});f.session(false);f.window.boogieEvent({type:'signal',peerId:'host',offer:{type:'offer',sdp:'test2'}});await new Promise(r=>setImmediate(r));
 f.connections.at(-1).ontrack({track:{kind:'video'}});assert.equal(f.video.muted,true);assert.equal(audio.hidden,false);
});

const mappingGame='sha256:'+'c'.repeat(64);
async function mappingGuest(role='player2'){
 const f=fixture();f.session(false,role);f.window.boogieEvent({type:'signal',peerId:'host',offer:{type:'offer',sdp:'fixture'}});await new Promise(r=>setImmediate(r));const p=f.connections[0],dc=p.createDataChannel('boogie-input',{});p.ondatachannel({channel:dc});
 const nonce='c'.repeat(32),port=role==='player2'?1:role==='player'?0:null;dc.onmessage({data:JSON.stringify({t:'grant',nonce,role,port,gameKey:mappingGame})});
 const request=(extra={})=>dc.onmessage({data:JSON.stringify({t:'mapping-setup',nonce,role,port,gameKey:mappingGame,requestId:'a'.repeat(32),...extra})});
 return {f,p,dc,request};
}
test('host invites only active input peers to their own mapping setup without altering game inputs',()=>{
 const f=fixture();f.session(true,'player',mappingGame);const one=f.peer('shared','player'),two=f.peer('second','player2'),watch=f.peer('watch','spectator');f.input(one,zero());f.input(two,zero());const b=zero();b[0]=1;f.input(two,b,1);f.window.boogieTouch(8,true);
 assert.equal(f.window.boogieRemote.requestMappingSetup(),2);const requests=[one,two].map(p=>p.channel.sent.find(m=>m.t==='mapping-setup'));assert.ok(requests.every(m=>/^[a-f0-9]{32}$/.test(m.requestId)&&m.gameKey===mappingGame));assert.equal(requests[0].nonce,one.channel.sent.find(m=>m.t==='grant').nonce);assert.equal(requests[0].role,'player');assert.equal(requests[0].port,0);assert.equal(requests[1].role,'player2');assert.equal(requests[1].port,1);assert.equal(watch.channel.sent.some(m=>m.t==='mapping-setup'),false);assert.deepEqual(Array.from(f.window.boogieDebug().portMasks),[256,1,0,0]);assert.equal(f.window.boogieRemote.requestMappingSetup(),0);
});
test('mapping setup requests require current grant nonce, role, port and game and cannot be forged toward host',async()=>{
 const {f,request,dc}=await mappingGuest();const pad={buttons:Array(17).fill(0),axes:[0,0,0,0]};pad.buttons[0]=1;f.window.boogieNativePads([pad,null,null,null]);assert.equal(dc.sent.at(-1).buttons[8],1);
 for(const extra of [{nonce:'d'.repeat(32)},{role:'player'},{port:0},{gameKey:'sha256:'+'d'.repeat(64)},{gameKey:null},{requestId:'bad'},{requestId:null}])request(extra);
 assert.equal(f.messages.filter(m=>m.type==='mapping-setup-request').length,0);assert.equal(dc.sent.at(-1).buttons[8],1);assert.equal(f.window.boogieRemote.requestMappingSetup(),0);
 const h=fixture();h.session(true,'player',mappingGame);const p=h.peer();p.channel.onmessage({data:JSON.stringify({t:'mapping-setup',nonce:p.channel.sent.find(m=>m.t==='grant').nonce,requestId:'a'.repeat(32),role:'player',port:0,gameKey:mappingGame})});assert.equal(h.messages.some(m=>m.type==='mapping-setup-request'),false);
});
test('valid setup invitation releases only this guest, deduplicates/rate-bounds, and quarantines held controls',async()=>{
 const {f,request,dc}=await mappingGuest();const pad={buttons:Array(17).fill(0),axes:[0,0,0,0]};pad.buttons[0]=1;f.window.boogieNativePads([pad,null,null,null]);request();const msg=f.messages.find(m=>m.type==='mapping-setup-request');assert.equal(msg.role,'player2');assert.equal(msg.port,1);assert.equal(msg.gameKey,mappingGame);assert.equal(Object.hasOwn(msg,'nonce'),false);assert.ok(dc.sent.at(-1).buttons.every(v=>v===0));
 request();request({requestId:'b'.repeat(32)});assert.equal(f.messages.filter(m=>m.type==='mapping-setup-request').length,1);f.window.boogieSetEditing(false);f.window.boogieNativePads([pad,null,null,null]);assert.ok(dc.sent.at(-1).buttons.every(v=>v===0));pad.buttons[0]=0;f.window.boogieNativePads([pad,null,null,null]);pad.buttons[0]=1;f.window.boogieNativePads([pad,null,null,null]);assert.equal(dc.sent.at(-1).buttons[8],1);
 f.tick(2100);request();assert.equal(f.messages.filter(m=>m.type==='mapping-setup-request').length,1);request({requestId:'b'.repeat(32)});assert.equal(f.messages.filter(m=>m.type==='mapping-setup-request').length,2);
});
test('spectators and retired host channels cannot trigger mapping setup',async()=>{
 const s=await mappingGuest('spectator');s.request();assert.equal(s.f.messages.some(m=>m.type==='mapping-setup-request'),false);
 const {f,request}=await mappingGuest();f.window.boogieEvent({type:'stop'});request();assert.equal(f.messages.some(m=>m.type==='mapping-setup-request'),false);
});

test('ignored mapping UI request does not leave guest in permanent edit mode',async()=>{
 const {f,request,dc}=await mappingGuest();const pad={buttons:Array(17).fill(0),axes:[0,0,0,0]};pad.buttons[0]=1;f.window.boogieNativePads([pad,null,null,null]);request();assert.ok(dc.sent.at(-1).buttons.every(v=>v===0));f.window.boogieNativePads([pad,null,null,null]);assert.ok(dc.sent.at(-1).buttons.every(v=>v===0));pad.buttons[0]=0;f.window.boogieNativePads([pad,null,null,null]);pad.buttons[0]=1;f.window.boogieNativePads([pad,null,null,null]);assert.equal(dc.sent.at(-1).buttons[8],1);
});
test('owned native host mapping dialog keeps remote player running; explicit background still releases all',()=>{
 const f=fixture();f.session(true,'player',mappingGame);const p=f.peer('second','player2'),held=zero();held[8]=1;f.input(p,zero());f.input(p,held,1);f.window.boogieTouch(0,true);f.window.boogieEvent({type:'native-mapping',active:true});f.window.boogieSetEditing(true);f.winEvents.blur();assert.equal(f.window.boogieDebug().focused,true);assert.deepEqual(Array.from(f.window.boogieDebug().portMasks),[0,256,0,0]);f.input(p,held,2);assert.equal(f.window.boogieDebug().portMasks[1],256);
 f.window.boogieEvent({type:'focus',active:false});assert.ok(f.window.boogieDebug().portMasks.every(v=>v===0));assert.equal(f.window.boogieDebug().focused,false);f.input(p,held,3);assert.equal(f.window.boogieDebug().portMasks[1],0);f.window.boogieEvent({type:'focus',active:true});f.winEvents.blur();assert.equal(f.window.boogieDebug().focused,false);
});
test('native mapping flag cannot suppress hidden-page releases or be set by a guest',async()=>{
 const f=fixture();f.session();const p=f.peer(),held=zero();held[8]=1;f.input(p,zero());f.input(p,held,1);f.window.boogieEvent({type:'native-mapping',active:true});f.document.hidden=true;f.docEvents.visibilitychange();assert.equal(f.window.boogieDebug().inputMask,0);assert.equal(f.window.boogieDebug().focused,false);
 const g=await mappingGuest();g.f.window.boogieEvent({type:'native-mapping',active:true});g.f.winEvents.blur();assert.equal(g.f.window.boogieDebug().focused,false);
});

const coverFixture=JSON.parse(fs.readFileSync(__dirname+'/docs/fixtures/boogie-original-cover.json','utf8'));const originalCover=Object.fromEntries(['mime','width','height','sha256','data'].map(key=>[key,coverFixture[key]]));
const artEnvelope=(nonce='c'.repeat(32))=>({...originalCover,t:'game-art',nonce,gameKey:mappingGame});
const settleCrypto=()=>new Promise(r=>setTimeout(r,10));
test('host artwork cache sends only validated current-game JPEGs and authenticated art requests remain bounded',async()=>{
 const f=fixture();f.session(true,'player',mappingGame);const p=f.peer('watcher','spectator');const art={...originalCover,gameKey:mappingGame};assert.equal(await f.window.boogieRemote.publishGameArtwork({...art,sha256:'0'.repeat(64)}),false);assert.equal(await f.window.boogieRemote.publishGameArtwork({...art,gameKey:'sha256:'+'a'.repeat(64)}),false);assert.equal(await f.window.boogieRemote.publishGameArtwork(art),true);const sent=p.channel.sent.filter(m=>m.t==='game-art');assert.equal(sent.length,1);assert.equal(sent[0].nonce,p.channel.sent.find(m=>m.t==='grant').nonce);
 const request={t:'art-request',nonce:sent[0].nonce,gameKey:mappingGame};p.channel.onmessage({data:JSON.stringify(request)});assert.equal(p.channel.sent.filter(m=>m.t==='game-art').length,2);p.channel.onmessage({data:JSON.stringify(request)});assert.equal(p.channel.sent.filter(m=>m.t==='game-art').length,2);f.tick(2100);p.channel.onmessage({data:JSON.stringify({...request,nonce:'x'})});assert.equal(p.channel.sent.filter(m=>m.t==='game-art').length,2);f.window.boogieEvent({type:'stop'});assert.equal(await f.window.boogieRemote.publishGameArtwork(art),false);
});
test('guest artwork requires exact grant binding, bounded SOF dimensions and SHA, then deduplicates verified data',async()=>{
 const {f,dc}=await mappingGuest('spectator'),received=[];f.window.boogieBackdrop={applyVerifiedGuestArtwork:(...v)=>{received.push(v);return true;},clearGameArtwork(){}};
 for(const change of [{nonce:'a'.repeat(32)},{gameKey:'sha256:'+'e'.repeat(64)},{width:320},{extra:'forbidden'}]){dc.onmessage({data:JSON.stringify({...artEnvelope(),...change})});await settleCrypto();}assert.equal(received.length,0);
 dc.onmessage({data:JSON.stringify({...artEnvelope(),sha256:'0'.repeat(64)})});await settleCrypto();assert.equal(received.length,0);f.tick(2100);dc.onmessage({data:JSON.stringify(artEnvelope())});await settleCrypto();assert.equal(received.length,1);assert.equal(received[0][1],mappingGame);dc.onmessage({data:JSON.stringify(artEnvelope())});await settleCrypto();assert.equal(received.length,1);
});
test('unordered artwork arriving before grant is retried at most twice and stale async verification never paints a new game',async()=>{
 const {f,dc}=await mappingGuest(),received=[];f.window.boogieBackdrop={applyVerifiedGuestArtwork:(...v)=>{received.push(v);return true;},clearGameArtwork(){}};assert.equal(dc.sent.filter(m=>m.t==='art-request').length,1);f.tick(2100);f.tick(2100);f.tick(2100);assert.equal(dc.sent.filter(m=>m.t==='art-request').length,3);
 dc.onmessage({data:JSON.stringify(artEnvelope())});f.window.boogieEvent({type:'stop'});await settleCrypto();assert.equal(received.length,0);
});

test('host waits for decoded crop frames before offering and falls back once when decoder fails',()=>{
 const f=fixture();let ready=false,failed=false,closed=0,starts=0;f.window.MayoViewportCapture={start(){starts++;return {canvas:{width:128,height:120},stream:f.engine.canvas.captureStream(),ready:()=>ready,failed:()=>failed,close(){closed++;},rectangle:()=>null};}};f.session();f.window.boogieEvent({type:'peer-approved',peerId:'guest1',role:'player2',port:1});f.tick();assert.equal(f.connections.length,0);ready=true;f.tick();assert.equal(f.connections.length,1);assert.equal(starts,1);f.window.boogieEvent({type:'stop'});assert.equal(closed,1);
 const fallback=fixture();let attempts=0,retired=0;fallback.window.MayoViewportCapture={start(){attempts++;return {canvas:{width:128,height:120},stream:fallback.engine.canvas.captureStream(),ready:()=>false,failed:()=>failed,close(){retired++;},rectangle:()=>null};}};failed=false;fallback.session();fallback.window.boogieEvent({type:'peer-approved',peerId:'guest2',role:'player2',port:1});fallback.tick();assert.equal(fallback.connections.length,0);failed=true;fallback.tick();assert.equal(fallback.connections.length,1);fallback.tick();assert.equal(attempts,1);assert.equal(retired,1);assert.equal(fallback.window.boogieDebug().captureViewport,null);
});
test('a later decoded capture failure replaces existing sender video before retiring its old capture',async()=>{
 const f=fixture();let failed=false,closed=0,replaced=0;f.window.MayoViewportCapture={start(){return {canvas:{width:128,height:120},stream:f.engine.canvas.captureStream(),ready:()=>true,failed:()=>failed,close(){closed++;},rectangle:()=>null};}};f.session();const peer=f.peer();peer.getSenders=()=>[{track:{kind:'video'},async replaceTrack(track){assert.equal(track.kind,'video');replaced++;}}];failed=true;f.tick();assert.equal(replaced,1);assert.equal(closed,0);await settleCrypto();assert.equal(closed,1);assert.notEqual(peer.connectionState,'closed');assert.equal(f.window.boogieDebug().videoTrack,true);
});
