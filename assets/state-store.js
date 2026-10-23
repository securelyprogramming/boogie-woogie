/* Host-only bounded native checkpoint transport. No states or ROMs cross the LAN. */
(() => {
 'use strict';
 const host=new URLSearchParams(location.search).get('host')==='1', MAX=8*1024*1024, CHUNK=32768;
 let pending=null, readySent=false;
 const send=(id,phase,extra={})=>window.BoogieNative?.postMessage(JSON.stringify({type:'state-result',id,phase,...extra}));
 const engine=()=>{const e=window.EJS_emulator;return e?.started===true&&e.gameManager&&e.getCore?.()==='fceumm'&&e.config?.forceLegacyCores===true&&e.config?.threads===false&&e.preGetSetting?.('ejs_threads')!=='enabled'?e:null;};
 function finish(){if(!pending)return;const p=pending;pending=null;clearTimeout(p.timer);clearTimeout(p.poll);try{if(p.paused)p.engine.pause(true);else p.engine.play(true);}finally{window.boogieCheckpoint?.(false);}}
 function fail(id){send(id,'error',{message:'Checkpoint operation failed; previous saves are unchanged.'});finish();}
 function begin(c){const e=engine();if(!e||pending||!['save','load'].includes(c.op))throw Error();pending={id:c.id,engine:e,paused:e.paused===true,index:0,offset:0,timer:setTimeout(()=>fail(c.id),30000)};window.boogieCheckpoint?.(true);e.pause(true);}
 window.boogieState=c=>{
  if(!host||!c||typeof c.id!=='string'||!/^s[0-9a-f]{32}$/.test(c.id))return;
  if(['cancel','finish'].includes(c.op)){if(pending?.id===c.id)finish();return;}
  try{
   if(c.op==='save'){begin(c);const bytes=pending.engine.gameManager.getState();if(!(bytes instanceof Uint8Array)||!bytes.length||bytes.length>MAX)throw Error();pending.bytes=new Uint8Array(bytes);send(c.id,'begin',{size:bytes.length});return;}
   if(c.op==='load'){begin(c);if(!Number.isSafeInteger(c.size)||c.size<1||c.size>MAX)throw Error();pending.bytes=new Uint8Array(c.size);pending.loading=true;send(c.id,'ready');return;}
   const p=pending;if(!p||p.id!==c.id)return;
   if(c.op==='next'&&!p.loading){if(c.index!==p.index)throw Error();if(p.offset===p.bytes.length){send(c.id,'end');return;}const b=p.bytes.subarray(p.offset,p.offset+CHUNK);let raw='';for(const v of b)raw+=String.fromCharCode(v);send(c.id,'chunk',{index:p.index++,data:btoa(raw)});p.offset+=b.length;return;}
   if(c.op==='append'&&p.loading){if(c.index!==p.index||typeof c.data!=='string'||c.data.length>43692||! /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(c.data))throw Error();const raw=atob(c.data);if(!raw.length||raw.length!==Math.min(CHUNK,p.bytes.length-p.offset))throw Error();for(let i=0;i<raw.length;i++)p.bytes[p.offset+i]=raw.charCodeAt(i);p.offset+=raw.length;p.index++;send(c.id,'ack',{index:c.index});return;}
   if(c.op==='commit'&&p.loading&&!p.committing){
    if(p.offset!==p.bytes.length||typeof p.engine.gameManager.getFrameNum!=='function')throw Error();
    let last=p.engine.gameManager.getFrameNum(),advances=0,attempts=0;const deadline=Date.now()+2000;
    if(!Number.isFinite(last))throw Error();p.committing=true;p.engine.gameManager.loadState(p.bytes);p.engine.play(true);
    const consumed=()=>{if(pending!==p||!p.committing)return;try{
     if(Date.now()>deadline||++attempts>120)throw Error();const frame=p.engine.gameManager.getFrameNum();if(!Number.isFinite(frame))throw Error();
     if(frame!==last){last=frame;advances++;}
     if(advances>=2){send(c.id,'loaded');finish();return;}
     p.poll=setTimeout(consumed,16);
    }catch(_){fail(c.id);}};p.poll=setTimeout(consumed,16);return;
   }
   throw Error();
  }catch(_){if(pending?.id===c.id)fail(c.id);else send(c.id,'error',{message:'Game is not ready or another checkpoint is active.'});}
 };
 setInterval(()=>{if(host&&!readySent&&engine()){readySent=true;send('','core-ready');}},250);
 addEventListener('pagehide',finish);
})();
