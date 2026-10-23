'use strict';
const {test}=require('node:test'), assert=require('node:assert/strict'), vm=require('node:vm'), fs=require('node:fs');
test('frontend settings validate before changing pixels or local volume',()=>{
  let tick, volume, fit;
  const video={style:{setProperty:(key,value)=>{fit=value;}},volume:1},canvas={style:{}},core={canvas,setVolume:value=>{volume=value;}};
  const window={EJS_emulator:core,addEventListener(){}};
  vm.runInNewContext(fs.readFileSync('assets/player-settings.js','utf8'),{window,document:{getElementById:()=>video},setInterval:fn=>{tick=fn;return 1;},clearInterval(){}});
  const apply=window.boogiePlayerSettings.apply;
  assert.equal(apply({scale:'stretch',filter:'linear',volume:25,muted:false}),true);
  assert.equal(fit,'fill');assert.equal(video.volume,.25);assert.equal(volume,.25);assert.equal(canvas.style.imageRendering,'auto');
  assert.equal(apply({scale:'fit',filter:'nearest',volume:90,muted:true}),true);
  assert.equal(fit,'contain');assert.equal(video.volume,0);assert.equal(volume,0);assert.equal(canvas.style.imageRendering,'pixelated');
  for(const invalid of [{volume:101},{volume:'80'},{scale:'unsafe'},{filter:'shader'},{muted:1}]){
    assert.equal(apply({scale:'fit',filter:'nearest',volume:90,muted:true,...invalid}),false);
    assert.equal(video.volume,0);
  }
  window.EJS_emulator={canvas,setVolume:value=>{volume=value;}};volume=-1;tick();assert.equal(volume,0);
});
