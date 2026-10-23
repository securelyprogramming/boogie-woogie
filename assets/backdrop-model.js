/* Bounded local appearance settings and image-envelope parsing. No network I/O. */
(function(root){'use strict';
 const KEY='mayo.appearance.v1',MAX=49152,defaults={schema:1,mode:'game',dim:82};
 const gameKey=v=>typeof v==='string'&&/^sha256:[a-f0-9]{64}$/.test(v)?v:null;
 function preferences(v){return v&&typeof v==='object'&&['off','brand','game'].includes(v.mode)&&typeof v.dim==='number'&&Number.isFinite(v.dim)&&v.dim>=40&&v.dim<=95?{schema:1,mode:v.mode,dim:Math.round(v.dim)}:null;}
 function load(storage){try{const raw=storage.getItem(KEY);if(raw&&raw.length<=256){const v=JSON.parse(raw);if(v.schema===1&&preferences(v))return preferences(v);}}catch(_){}return {...defaults};}
 function save(storage,v){const p=preferences(v);if(!p)return false;try{storage.setItem(KEY,JSON.stringify(p));return true;}catch(_){return false;}}
 function base64(value){if(typeof value!=='string'||!value.length||value.length>65536||value.length%4||!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value))return null;try{const raw=atob(value);if(raw.length>MAX||btoa(raw)!==value)return null;return Uint8Array.from(raw,c=>c.charCodeAt(0));}catch(_){return null;}}
 function dimensions(bytes,mime){if(!(bytes instanceof Uint8Array)||bytes.length<24||bytes.length>MAX)return null;let width,height;
  if(mime==='image/png'){if(![137,80,78,71,13,10,26,10].every((v,i)=>bytes[i]===v)||bytes[8]!==0||bytes[9]!==0||bytes[10]!==0||bytes[11]!==13||String.fromCharCode(...bytes.slice(12,16))!=='IHDR')return null;const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);width=view.getUint32(16);height=view.getUint32(20);}
  else if(mime==='image/jpeg'){if(bytes[0]!==255||bytes[1]!==216||bytes.at(-2)!==255||bytes.at(-1)!==217)return null;let at=2,found=false;
   while(at+3<bytes.length){if(bytes[at++]!==255)return null;while(bytes[at]===255)at++;const marker=bytes[at++];if(marker===0||marker===216||marker===217||marker===218||marker>=208&&marker<=215)return null;if(marker===1)continue;const length=bytes[at]*256+bytes[at+1];if(length<2||at+length>bytes.length)return null;
    if([193,195,197,198,199,201,202,203,205,206,207].includes(marker))return null;if([192,194].includes(marker)){if(length<8||bytes[at+2]!==8)return null;height=bytes[at+3]*256+bytes[at+4];width=bytes[at+5]*256+bytes[at+6];found=true;break;}at+=length;
   }if(!found)return null;
  }else return null;
  return Number.isInteger(width)&&width>0&&width<=320&&Number.isInteger(height)&&height>0&&height<=320?{width,height}:null;
 }
 function dataURL(value){if(typeof value!=='string'||value.length>65600)return null;const match=/^data:(image\/(?:jpeg|png));base64,([A-Za-z0-9+/=]+)$/.exec(value);if(!match)return null;const bytes=base64(match[2]),size=bytes&&dimensions(bytes,match[1]);return size?{...size,mime:match[1],bytes,data:match[2],url:value}:null;}
 function artwork(value){if(!value||typeof value!=='object'||!gameKey(value.gameKey)||value.mime!=='image/jpeg'||typeof value.sha256!=='string'||!/^[a-f0-9]{64}$/.test(value.sha256)||!Number.isInteger(value.width)||!Number.isInteger(value.height))return null;const bytes=base64(value.data),size=bytes&&dimensions(bytes,'image/jpeg');return size&&size.width===value.width&&size.height===value.height?{gameKey:value.gameKey,mime:'image/jpeg',width:size.width,height:size.height,sha256:value.sha256,data:value.data,bytes}:null;}
 function margins(box,width,height,rect){
  if(!box||![box.left,box.top,box.width,box.height,width,height,rect?.x,rect?.y,rect?.width,rect?.height].every(Number.isFinite)||box.width<=0||box.height<=0||box.width>32768||box.height>32768||Math.abs(box.left)>32768||Math.abs(box.top)>32768||width<=0||height<=0||rect.x<0||rect.y<0||rect.width<=0||rect.height<=0||rect.x+rect.width>width||rect.y+rect.height>height)return null;
  const sx=box.width/width,sy=box.height/height,left=box.left+rect.x*sx,top=box.top+rect.y*sy,right=left+rect.width*sx,bottom=top+rect.height*sy;
  return {viewport:{left,top,width:rect.width*sx,height:rect.height*sy},panels:[{left:box.left,top:box.top,width:left-box.left,height:box.height},{left:right,top:box.top,width:box.left+box.width-right,height:box.height},{left,top:box.top,width:right-left,height:top-box.top},{left,top:bottom,width:right-left,height:box.top+box.height-bottom}]};
 }
 const api={KEY,MAX,defaults,margins,gameKey,preferences,load,save,base64,dimensions,dataURL,artwork};root.MayoBackdropModel=api;if(typeof module==='object')module.exports=api;
})(typeof window==='object'?window:globalThis);
