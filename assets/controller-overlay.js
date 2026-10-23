'use strict';
(()=>{
 let visible=true;try{visible=localStorage.getItem('mayo.controls.visible')!=='false'}catch{}
 const style=document.createElement('style');document.head.append(style);
 function apply(){style.textContent=visible?'':'#touchBoard,#editLayout,.ejs_virtualGamepad_parent,.ejs_virtualGamepad_open{display:none!important}';window.boogieOverlayChanged?.(visible)}
 window.boogieOverlay={setVisible(value){if(typeof value!=='boolean')return;window.boogieLayout?.release();for(const el of document.querySelectorAll('.ejs_virtualGamepad_parent .ejs_virtualGamepad_button_down,.ejs_virtualGamepad_parent .ejs_dpad_main'))el.dispatchEvent(new Event('touchcancel',{bubbles:true,cancelable:true}));visible=value;try{localStorage.setItem('mayo.controls.visible',String(value))}catch{}apply()},visible:()=>visible};apply();
})();
