const {test}=require('node:test'),a=require('node:assert/strict'),M=require('./assets/layout-model.js');
const game='sha256:'+'a'.repeat(64),other='sha256:'+'b'.repeat(64);
const store=()=>{let data=new Map();return {getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),data}};
test('game override, all-games default and malformed layout handling',()=>{let s=store(),def=M.copy(M.defaults),per=M.copy(def);def.a.x=.7;per.a.x=.2;a.equal(M.save(s,null,def),true);a.equal(M.save(s,game,per),true);a.equal(M.load(s,game).a.x,.2);a.equal(M.load(s,other).a.x,.7);s.data.set('mayo.touch-layout.v1.'+game,'{"schema":1,"controls":{"a":{"x":999}}}');a.equal(M.load(s,game).a.x,.7);a.equal(M.save(s,'../../bad',per),false);a.equal(M.save(s,game,{...per,a:{x:NaN,y:0}}),false);a.equal(M.save(s,game,{...per,a:{x:.3,y:.3,z:2}}),false);});
test('corrupt, oversized and inaccessible storage safely falls back',()=>{let s=store();s.data.set('mayo.touch-layout.v1.default','x'.repeat(5000));a.deepEqual(M.load(s,null),M.defaults);a.deepEqual(M.load({getItem(){throw Error()}},null),M.defaults);a.equal(M.save({setItem(){throw Error()}},null,M.defaults),false);});
test('console layouts and saved positions remain inside portrait, landscape and tiny viewports',()=>{for(let [w,h,size]of [[369,650,42],[840,260,62],[200,140,42]]){let layout=M.consoleLayout(w,h,size);a.equal(M.valid(layout),true);for(let p of Object.values(layout)){let pos=M.position(p,w,h,size);a.ok(pos.left>=0&&pos.top>=0&&pos.left+size<=w&&pos.top+size<=h);}}});
test('editor capability survives resize and game metadata; revocation closes and releases editing',()=>{
 const vm=require('node:vm'),fs=require('node:fs'),elements=new Map(),events={},touches=[],editing=[];
 const element=id=>{if(!elements.has(id))elements.set(id,{hidden:false,disabled:false,textContent:'',style:{},classList:{toggle(){}},listeners:{},dataset:{},addEventListener(n,f){this.listeners[n]=f;}});return elements.get(id);};
 const board=element('touchBoard');board.clientWidth=840;board.clientHeight=300;
 const button=element('button');button.dataset={control:'a',action:'8'};button.setPointerCapture=()=>{};board.querySelectorAll=()=>[button];
 const window={MayoLayoutModel:M,addEventListener(n,f){events[n]=f;},boogieTouch:(...v)=>touches.push(v),boogieSetEditing:v=>editing.push(v)};
 vm.runInNewContext(fs.readFileSync('assets/layout-editor.js','utf8'),{window,document:{getElementById:element,addEventListener(){}},localStorage:store()});
 // Android has no capability call and retains its existing default behavior.
 a.equal(element('editLayout').hidden,false);
 window.boogieLayout.setEnabled(false);events.resize();window.boogieLayout.setGame(game);
 a.equal(element('editLayout').hidden,true);element('editLayout').onclick();a.equal(window.boogieLayout.editing(),false);
 button.listeners.pointerdown({preventDefault(){},pointerId:1});a.equal(touches.length,0);
 window.boogieLayout.setEnabled(true);element('editLayout').onclick();a.equal(window.boogieLayout.editing(),true);
 window.boogieLayout.setEnabled(false);a.equal(window.boogieLayout.editing(),false);a.equal(element('layoutPanel').hidden,true);a.equal(editing.at(-1),false);
 events.resize();a.equal(element('editLayout').hidden,true);
});
