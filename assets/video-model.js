(function(root){'use strict';
 const profiles=Object.freeze({smooth:Object.freeze({label:'Smooth',maxWidth:480,maxBitrate:700000,maxFramerate:30}),balanced:Object.freeze({label:'Balanced',maxWidth:720,maxBitrate:1200000,maxFramerate:30}),sharp:Object.freeze({label:'Sharp',maxWidth:1920,maxBitrate:2000000,maxFramerate:30})});
 const valid=v=>typeof v==='string'&&Object.hasOwn(profiles,v),key='mayo.video.v1';
 function load(storage){try{let raw=storage.getItem(key);if(!raw||raw.length>256)return {profile:'sharp',showFps:false};let v=JSON.parse(raw);if(v.schema===1&&valid(v.profile)&&typeof v.showFps==='boolean')return {profile:v.profile,showFps:v.showFps};}catch(_){}return {profile:'sharp',showFps:false};}
 function save(storage,value){if(!valid(value.profile)||typeof value.showFps!=='boolean')return false;try{storage.setItem(key,JSON.stringify({schema:1,profile:value.profile,showFps:value.showFps}));return true;}catch(_){return false;}}
 function encoding(profile,width){if(!valid(profile))return null;let p=profiles[profile];return {maxBitrate:p.maxBitrate,maxFramerate:p.maxFramerate,scaleResolutionDownBy:Math.max(1,(Number.isFinite(width)?width:1)/p.maxWidth)};}
 const api={profiles,valid,load,save,encoding};root.MayoVideoModel=api;if(typeof module==='object')module.exports=api;
})(typeof window==='object'?window:globalThis);
