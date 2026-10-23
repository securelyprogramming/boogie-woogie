'use strict';
(() => {
 let pads=[null,null,null,null];
 Object.defineProperty(navigator,'getGamepads',{value:()=>pads.slice()});
 window.emulatormayoGamepads = states => {
  if(!Array.isArray(states)||states.length!==4)return;
  pads=states.map((s,index)=>s&&Array.isArray(s.buttons)&&s.buttons.length===17&&Array.isArray(s.axes)&&s.axes.length===4 ?
   {id:s.id||'Boogie controller',index,connected:true,mapping:'standard',timestamp:performance.now(),buttons:s.buttons.map(n=>({value:n,pressed:n>.5,touched:n>0})),axes:s.axes.slice()}:null);
 };
 window.emulatormayoEnableGamepads=()=>window.EJS_emulator?.gamepad?.updateGamepadState();
})();
