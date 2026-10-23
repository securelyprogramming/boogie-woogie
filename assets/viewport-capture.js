/* Crop only the core-declared viewport, as EmulatorJS's own recorder does. */
(function(root){'use strict';
 const validMetadata=(aspect,rotation)=>typeof aspect==='number'&&Number.isFinite(aspect)&&aspect>=.5&&aspect<=3&&Number.isInteger(rotation)&&rotation>=0&&rotation<=3;
 function rectangle(width,height,aspect,rotation){
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width>8192||height>8192)return null;
  if(!validMetadata(aspect,rotation))return {x:0,y:0,width,height,cropped:false};
  const ratio=rotation%2?1/aspect:aspect;let w=width,h=height;if(width/height>ratio)w=Math.max(1,Math.min(width,Math.round(height*ratio)));else h=Math.max(1,Math.min(height,Math.round(width/ratio)));
  return {x:Math.floor((width-w)/2),y:Math.floor((height-h)/2),width:w,height:h,cropped:w!==width||h!==height};
 }
 function start({document,getSource,getMetadata,onViewport,setTimer=setTimeout,clearTimer=clearTimeout}){
  const source=getSource(),metadata=getMetadata()||{},initial=source&&rectangle(source.width,source.height,metadata.aspect,metadata.rotation);
  if(!initial||typeof source.captureStream!=='function')throw Error('Invalid capture source');
  const canvas=document.createElement('canvas'),context=canvas.getContext('2d',{alpha:false}),video=document.createElement('video');
  // WebGL's default framebuffer can be discarded outside its paint callback. A
  // decoded captureStream frame owns its pixels; never read the WebGL canvas.
  if(!context||typeof canvas.captureStream!=='function'||typeof video.requestVideoFrameCallback!=='function'||typeof video.cancelVideoFrameCallback!=='function')throw Error('Decoded frame capture unavailable');
  canvas.width=initial.width;canvas.height=initial.height;
  let active=true,frame=null,timer=null,current=null,ready=false,failure=false,input=null,stream=null,last=-Infinity;const owned=new Set();
  function failed(){if(!active)return;failure=true;onViewport?.(null,null);}
  function next(timestamp){
   if(!active||failure)return;
   if(getSource()!==source){failed();return;}
   const m=getMetadata()||{},rect=rectangle(video.videoWidth,video.videoHeight,m.aspect,m.rotation);
   if(rect&&timestamp-last>=1000/30-.5){try{
    if(canvas.width!==rect.width||canvas.height!==rect.height){canvas.width=rect.width;canvas.height=rect.height;}
    context.imageSmoothingEnabled=false;context.drawImage(video,rect.x,rect.y,rect.width,rect.height,0,0,rect.width,rect.height);
    current=rect;ready=true;last=timestamp;if(timer!==null){clearTimer(timer);timer=null;}
    onViewport?.(source,validMetadata(m.aspect,m.rotation)&&source.width===video.videoWidth&&source.height===video.videoHeight?rect:null);
   }catch(_){failed();return;}}
   if(active&&!failure)try{frame=video.requestVideoFrameCallback(next);}catch(_){failed();}
  }
  function close(){if(!active)return;active=false;if(frame!==null)video.cancelVideoFrameCallback(frame);frame=null;if(timer!==null)clearTimer(timer);timer=null;onViewport?.(null,null);video.onerror=null;video.pause?.();video.srcObject=null;for(const track of owned)if(track.readyState!=='ended')track.stop();video.remove?.();canvas.remove?.();}
  try{
   input=source.captureStream(30);for(const track of input.getTracks?.()||[])owned.add(track);if(!input.getVideoTracks?.().length)throw Error('No source video');
   video.muted=true;video.autoplay=true;video.playsInline=true;video.setAttribute?.('playsinline','');video.setAttribute?.('aria-hidden','true');
   // Keep one imperceptible, pointer-free pixel presented: Chromium may throttle
   // detached, offscreen or display:none video frame callbacks.
   if(video.style)Object.assign(video.style,{position:'fixed',right:'0',bottom:'0',width:'1px',height:'1px',opacity:'.001',zIndex:'2147483647',pointerEvents:'none'});
   video.srcObject=input;video.onerror=failed;document.body?.appendChild(video);
   stream=canvas.captureStream(30);for(const track of stream.getTracks?.()||[])owned.add(track);if(!stream.getVideoTracks?.().length)throw Error('No output video');
   timer=setTimer(failed,2000);frame=video.requestVideoFrameCallback(next);
   const playing=video.play();if(playing&&typeof playing.catch==='function')playing.catch(failed);
  }catch(error){close();throw error;}
  return {canvas,stream,ready:()=>ready&&!failure,failed:()=>failure,rectangle:()=>current&&({...current}),close};
 }

 const api={rectangle,start,validMetadata};root.MayoViewportCapture=api;if(typeof module==='object')module.exports=api;
})(typeof window==='object'?window:globalThis);
