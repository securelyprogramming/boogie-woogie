'use strict';
const params=new URLSearchParams(location.search);
const gameHash=params.get('game'),host=params.get('host')==='1'&&/^[a-f0-9]{64}$/.test(gameHash||'');
document.querySelector('#game').hidden=!host;document.querySelector('#guest').hidden=host;window.boogieLayout?.refresh();
if(host){
 window.EJS_player='#game';window.EJS_core='fceumm';window.EJS_threads=false;window.EJS_forceLegacyCores=true;window.EJS_defaultOptions={retroarch_core:'fceumm',ejs_threads:'disabled'};window.EJS_gameUrl='/boogie/game/'+gameHash+'.nes';window.EJS_gameName='NES '+gameHash;window.EJS_gameID=parseInt(gameHash.slice(0,12),16);
 window.EJS_pathtodata='/boogie/data/';window.EJS_startOnLoaded=true;window.EJS_color='#26734d';window.EJS_backgroundColor='#07150f';
 window.EJS_onGameStart=()=>{window.emulatormayoEnableGamepads();window.BoogieNative.postMessage(JSON.stringify({type:'status',message:'core-started'}));};
 const loader=document.createElement('script');loader.src='/boogie/data/loader.js';document.body.append(loader);
}
