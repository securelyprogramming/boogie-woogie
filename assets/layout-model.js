/* Normalized local-only layout schema. No account, ROM bytes or session secrets. */
(function(root){'use strict';
 const ids=['up','down','left','right','a','b','x','y','start','select'];
 const defaults={up:{x:.12,y:.68},left:{x:.01,y:.82},right:{x:.23,y:.82},down:{x:.12,y:.96},y:{x:.87,y:.68},x:{x:.76,y:.82},b:{x:.99,y:.82},a:{x:.87,y:.96},select:{x:.40,y:.90},start:{x:.59,y:.90}};
 const copy=v=>JSON.parse(JSON.stringify(v));
 function valid(v){return !!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===ids.length&&ids.every(id=>{let p=v[id];return p&&Object.keys(p).length===2&&typeof p.x==='number'&&Number.isFinite(p.x)&&p.x>=0&&p.x<=1&&typeof p.y==='number'&&Number.isFinite(p.y)&&p.y>=0&&p.y<=1;});}
 function gameKey(v){return typeof v==='string'&&/^sha256:[a-f0-9]{64}$/.test(v)?v:null;}
 function read(storage,key){try{let raw=storage.getItem(key);if(!raw||raw.length>4096)return null;let v=JSON.parse(raw);return v.schema===1&&valid(v.controls)?copy(v.controls):null;}catch(_){return null;}}
 const key='mayo.touch-layout.v1';
 function load(storage,game,fallback=defaults){return gameKey(game)&&read(storage,key+'.'+game)||read(storage,key+'.default')||copy(fallback);}
 function save(storage,game,controls){if(!valid(controls)||game!==null&&!gameKey(game))return false;try{storage.setItem(game===null?key+'.default':key+'.'+game,JSON.stringify({schema:1,controls:copy(controls)}));return true;}catch(_){return false;}}
 function clamp(v){return Math.max(0,Math.min(1,Number.isFinite(v)?v:0));}
 function position(p,width,height,size){return {left:clamp(p.x)*Math.max(0,width-size),top:clamp(p.y)*Math.max(0,height-size)};}
 function consoleLayout(width,height,size){const gap=4,step=size+gap,top=Math.max(0,height-size-2*step),right=Math.max(0,width-size-2*step),mid=Math.max(0,(width-size)/2);const points={up:[step,top],left:[0,top+step],right:[2*step,top+step],down:[step,top+2*step],y:[right+step,top],x:[right,top+step],b:[right+2*step,top+step],a:[right+step,top+2*step],select:[mid-step/2,height-size],start:[mid+step/2,height-size]};return Object.fromEntries(ids.map(id=>[id,{x:clamp(points[id][0]/Math.max(1,width-size)),y:clamp(points[id][1]/Math.max(1,height-size))}]));}
 const api={ids,defaults,copy,valid,gameKey,load,save,position,clamp,consoleLayout};root.MayoLayoutModel=api;if(typeof module==='object')module.exports=api;
})(typeof window==='object'?window:globalThis);
