"""Owned native guest options/controller editor, independent of host mappings."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

from boogie_protocol import DEFAULT_BUTTONS, GAME
from boogie_appearance import AppearanceStore

ACTIONS = (("Up",4),("Down",5),("Left",6),("Right",7),("A / Jump",8),
           ("B / Action",0),("Select",2),("Start",3))
SOURCE = re.compile(r"(?:b(?:[0-9]|1[0-4])|x[0-5][+-])\Z")


def source_label(source):
    labels=('A / South','B / East','X / West','Y / North','View / Select','Guide',
            'Menu / Start','L3','R3','LB','RB','D-pad Up','D-pad Down','D-pad Left','D-pad Right')
    if source.startswith('b'):return labels[int(source[1:])]
    axis=int(source[1]);positive=source[2]=='+'
    return (('Left stick '+('Right' if positive else 'Left')) if axis==0 else
            ('Left stick '+('Down' if positive else 'Up')) if axis==1 else
            ('Right stick '+('Right' if positive else 'Left')) if axis==2 else
            ('Right stick '+('Down' if positive else 'Up')) if axis==3 else
            ('Left trigger' if axis==4 else 'Right trigger'))


def defaults(mapping=DEFAULT_BUTTONS):
    bindings={str(action):[] for _,action in ACTIONS}
    for index, action in enumerate(mapping):
        if str(action) in bindings and index != 5:bindings[str(action)].append('b'+str(index))
    for source, action in (("x0-",6),("x0+",7),("x1-",4),("x1+",5)):
        bindings[str(action)].append(source)
    return bindings


def validate(value):
    if not isinstance(value,dict) or set(value)!={str(a) for _,a in ACTIONS}:raise ValueError('Invalid bindings')
    result={}
    for action, sources in value.items():
        if not isinstance(sources,list) or len(sources)>8 or any(not isinstance(s,str) for s in sources) or len(set(sources))!=len(sources):raise ValueError('Invalid bindings')
        if any(not isinstance(s,str) or not SOURCE.fullmatch(s) or s=='b5' for s in sources):raise ValueError('Invalid source')
        result[action]=list(sources)
    return result


def sources(buttons,axes):
    result={'b'+str(i) for i in range(15) if buttons&(1<<i) and i!=5}
    for index, value in enumerate(axes[:6]):
        if value < -.55:result.add('x'+str(index)+'-')
        elif value > .55:result.add('x'+str(index)+'+')
    return result


def mapped(active,bindings):
    output=[0]*16
    for action,inputs in bindings.items():output[int(action)]=int(bool(set(inputs)&active))
    for a,b in ((4,5),(6,7)):
        if output[a] and output[b]:output[a]=output[b]=0
    return output


class MappingStore:
    def __init__(self,root=None):
        self.root=Path(root or Path.home()/'.local/share/boogie-woogie/controls')

    def path(self,scope,game,device):
        if scope not in ('game','device') or not re.fullmatch(r'[a-f0-9]{64}',device):raise ValueError('Invalid device scope')
        if scope=='game' and not GAME.fullmatch(game):raise ValueError('A game is required')
        identity=(game+'|'+device) if scope=='game' else device
        return self.root/scope/(hashlib.sha256(identity.encode()).hexdigest()+'.json')

    def load(self,game,device,fallback):
        for scope in ('game','device'):
            try:
                path=self.path(scope,game,device)
                with path.open('rb') as stream:raw=stream.read(8193)
                if len(raw)>8192:continue
                value=json.loads(raw)
                if not isinstance(value,dict) or value.get('schema')!=1:continue
                return validate(value['bindings'])
            except (OSError,ValueError,TypeError,KeyError):pass
        return validate(fallback)

    def save(self,scope,game,device,bindings):
        path=self.path(scope,game,device);bindings=validate(bindings)
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,temporary=tempfile.mkstemp(prefix='.mapping-',dir=path.parent)
        try:
            with os.fdopen(fd,'w') as stream:json.dump({'schema':1,'bindings':bindings},stream,separators=(',',':'))
            os.replace(temporary,path)
        finally:
            Path(temporary).unlink(missing_ok=True)


class NativeUI:
    def __init__(self,mapping=None,store=None,appearance=None,brand='rommayo'):
        self.store=store or MappingStore();self.factory=defaults(mapping or DEFAULT_BUTTONS)
        self.appearance=appearance or AppearanceStore(brand)
        self.role='pending';self.game='';self.title='Waiting for host approval'
        self.page='';self.selection=0;self.message='';self.leave=False
        self.devices=[];self.selected_device='';self.applied={};self.session={}
        self.draft=None;self.scope='session';self.mode='replace';self.capture=None
        self.draft_game='';self.draft_title=''
        self.capture_neutral=True;self.wizard_index=None;self.last_sources=set()
        self.nav_previous=set();self.nav_due=0;self.nav_axis=''
        self.nav_armed=False
        self.pointer_down=False;self.generation=0;self.invites=[];self.last_invite=-1e9

    @property
    def editing(self):return self.page=='controls'
    @property
    def blocked(self):return bool(self.page)
    @property
    def heading(self):
        return {'player':'SHARED PLAYER 1','player2':'PLAYER 2','spectator':'WATCHING'}.get(self.role,'CONNECTING')

    def change(self):self.generation+=1

    def set_session(self,role,game,title=''):
        self.role=role
        if game!=self.game:
            self.game=game if isinstance(game,str) and GAME.fullmatch(game) else ''
            self.applied.clear()
        self.title=''.join(c for c in str(title) if 32<=ord(c)<127)[:64] or 'Host game'
        self.change()

    def set_devices(self,devices):
        if devices==self.devices:return
        self.devices=devices
        if self.selected_device not in [d['key'] for d in devices]:
            if self.draft is not None:
                self.message='Controller disconnected. Reconnect it to finish this draft.'
            else:self.selected_device=devices[0]['key'] if devices else ''
        self.change()

    def bindings(self,device):
        if device in self.session:return self.session[device]
        if device not in self.applied:self.applied[device]=self.store.load(self.game,device,self.factory)
        return self.applied[device]

    def toggle(self):
        if self.page=='confirm-leave':
            self.page='options';self.selection=0;self.nav_armed=False
            self.message='Session kept open.'
        elif self.editing:
            if self.capture is not None:
                self.capture=None;self.wizard_index=None;self.message='Capture canceled; draft kept.'
            else:
                self.page='options';self.selection=1;self.nav_armed=False
                self.message='Draft kept. Save it in Controls to apply.'
        elif self.page=='appearance':
            self.page='options';self.selection=2 if self.role!='spectator' else 1;self.nav_armed=False
        else:
            self.page='' if self.page else 'options';self.selection=0
            self.nav_armed=False;self.nav_previous=set()
        self.change()

    def controls(self,remote=False):
        if self.role=='spectator':return False
        if self.editing:
            if remote:self.message='Host invited you to map controls. Your current draft is kept.'
            self.change();return False
        had_draft=self.draft is not None
        self.page='controls';self.selection=0;self.capture=None;self.wizard_index=None
        self.nav_armed=False;self.nav_previous=set()
        if not had_draft:
            self.draft=validate(self.bindings(self.selected_device)) if self.selected_device else validate(self.factory)
            self.draft_game=self.game;self.draft_title=self.title
            self.scope='session'
        self.message='Your draft is kept. Save to apply.' if had_draft else 'Your controls only. Other players keep playing.'
        self.change();return True

    def request_mapping(self,message,capability,now=None):
        now=time.monotonic() if now is None else now
        if (not capability.approved or not capability.nonce or capability.port is None
                or not isinstance(message,dict) or set(message)!={'t','nonce','requestId','role','port','gameKey'}
                or message.get('t')!='mapping-setup' or message.get('nonce')!=capability.nonce
                or message.get('role')!=capability.role or type(message.get('port')) is not int
                or message['port']!=capability.port or not isinstance(message.get('gameKey'),str)
                or not GAME.fullmatch(message['gameKey']) or message['gameKey']!=capability.game_key
                or not isinstance(message.get('requestId'),str) or not re.fullmatch(r'[a-f0-9]{32}',message['requestId'])):return False
        request=message['requestId']
        if request in self.invites or now-self.last_invite<2:return False
        self.invites=(self.invites+[request])[-32:];self.last_invite=now
        return self.controls(remote=True)

    def rows(self):
        if self.page=='confirm-leave':return ['Keep playing' if self.role!='spectator' else 'Keep watching','Leave session']
        if self.page=='options':return ['Resume game','Controls / button mapper','Appearance','Leave session'] if self.role!='spectator' else ['Resume watching','Appearance','Leave session']
        if self.page=='appearance':
            return ['Background: '+{'off':'Off','brand':'App brand','game':'Current game (brand fallback)'}[self.appearance.mode],
                    'Dim less / brighter: '+str(self.appearance.dim)+'%',
                    'Dim more / darker: '+str(self.appearance.dim)+'%','Back']
        if self.page!='controls':return []
        if self.capture is not None:
            label=dict((a,n) for n,a in ACTIONS)[self.capture]
            step=(' ('+str(self.wizard_index+1)+'/'+str(len(ACTIONS))+')') if self.wizard_index is not None else ''
            return ['Press a control for '+label+step,'Cancel capture']
        label=next((d['label'] for d in self.devices if d['key']==self.selected_device),'No controller connected')
        rows=['Controller: '+label,'Guided setup (one action at a time)']
        for name,action in ACTIONS:
            bound=', '.join(source_label(s) for s in self.draft[str(action)]) or 'unassigned'
            rows.append(name+': '+bound)
        rows.extend(['Binding mode: '+self.mode,'Save for: '+{'session':'this session','game':'this game + controller','device':'this controller, all games'}[self.scope],
                     'Save controls','Discard draft','Restore defaults in draft'])
        return rows

    def activate(self,index):
        if self.page=='options':
            if index==0:self.page=''
            elif index==1 and self.role!='spectator':self.controls()
            elif index==(2 if self.role!='spectator' else 1):
                self.page='appearance';self.selection=0;self.nav_armed=False
                self.message='Backdrop only. Gameplay colors and brightness stay unchanged.'
            else:
                self.page='confirm-leave';self.selection=0;self.nav_armed=False;self.nav_previous=set()
                self.message='Leave this session? Other players keep playing.'
        elif self.page=='confirm-leave':
            if index==1:self.leave=True
            else:self.page='options';self.selection=0;self.nav_armed=False;self.message='Session kept open.'
        elif self.page=='appearance':
            try:
                if index==0:
                    modes=('game','brand','off');self.appearance.save(mode=modes[(modes.index(self.appearance.mode)+1)%3])
                elif index in (1,2):self.appearance.save(dim=max(40,min(95,self.appearance.dim+(-5 if index==1 else 5))))
                else:self.toggle()
            except (OSError,ValueError):self.message='Could not save appearance; previous settings kept.'
        elif self.page=='controls':
            if self.capture is not None:
                if index==1:self.capture=None;self.wizard_index=None
            elif index==0 and self.devices:
                if self.selected_device and self.draft!=self.bindings(self.selected_device):
                    self.message='Save or discard this draft before changing controller.';self.change();return
                keys=[d['key'] for d in self.devices]
                self.selected_device=keys[(keys.index(self.selected_device)+1)%len(keys)] if self.selected_device in keys else keys[0]
                self.draft=validate(self.bindings(self.selected_device));self.message='Selected controller; its saved mapping loaded.'
            elif index==1:
                if self.selected_device not in [d['key'] for d in self.devices]:
                    self.message='Connect a controller before starting guided setup.';self.change();return
                self.wizard_index=0;self.capture=ACTIONS[0][1];self.capture_neutral=True;self.last_sources=set()
            elif 2<=index<10:
                if self.selected_device not in [d['key'] for d in self.devices]:
                    self.message='Connect a controller before capturing a binding.';self.change();return
                self.capture=ACTIONS[index-2][1];self.wizard_index=None;self.capture_neutral=True;self.last_sources=set()
            elif index==10:self.mode='add' if self.mode=='replace' else 'replace'
            elif index==11:
                scopes=['session','game','device'] if self.draft_game else ['session','device']
                self.scope=scopes[(scopes.index(self.scope)+1)%len(scopes)]
            elif index==12:
                if not self.selected_device:self.message='Connect a controller before saving.'
                else:
                    try:
                        bindings=validate(self.draft)
                        if self.scope!='session':self.store.save(self.scope,self.draft_game,self.selected_device,bindings)
                        if self.scope=='session':self.session[self.selected_device]=bindings
                        else:
                            self.session.pop(self.selected_device,None);self.applied.pop(self.selected_device,None)
                            self.bindings(self.selected_device)
                        self.page='options';self.selection=0;self.draft=None
                        self.message=('Saved. This game\'s override still takes priority.'
                                      if self.bindings(self.selected_device)!=bindings else 'Your controls saved.')
                    except (OSError,ValueError):self.message='Could not save. Your draft is kept.'
            elif index==13:self.page='options';self.selection=0;self.draft=None
            elif index==14:self.draft=validate(self.factory);self.message='Defaults restored in draft. Save to apply.'
        self.change()

    def capture_sources(self,device,active):
        if self.capture is None or device!=self.selected_device:return
        if self.capture_neutral:
            if not active:self.capture_neutral=False
            return
        fresh=sorted(active-self.last_sources);self.last_sources=set(active)
        if not fresh:return
        source=fresh[0]
        if source in ('b5','b7','b8') and ('b7' in active and 'b8' in active):return
        action=str(self.capture)
        if self.mode=='replace' or self.wizard_index is not None:self.draft[action]=[source]
        elif source not in self.draft[action] and len(self.draft[action])<8:self.draft[action].append(source)
        self.capture_neutral=True;self.last_sources=set()
        if self.wizard_index is not None and self.wizard_index+1<len(ACTIONS):
            self.wizard_index+=1;self.capture=ACTIONS[self.wizard_index][1]
        else:
            self.capture=None;self.wizard_index=None;self.message='Captured. Save controls to apply your draft.'
            self.nav_armed=False;self.nav_previous=set()
        self.change()

    def navigation(self,active,now=None):
        now=time.monotonic() if now is None else now
        if not self.page or self.capture is not None:return
        if not self.nav_armed:
            if not active:self.nav_armed=True
            return
        new=active-self.nav_previous;self.nav_previous=set(active)
        direction='up' if {'b11','x1-'}&active else 'down' if {'b12','x1+'}&active else ''
        if direction and (direction!=self.nav_axis or now>=self.nav_due):
            self.selection=(self.selection+(-1 if direction=='up' else 1))%max(1,len(self.rows()))
            self.nav_due=now+(.3 if direction!=self.nav_axis else .12);self.change()
        self.nav_axis=direction
        if 'b0' in new:self.activate(self.selection)
        elif 'b1' in new:
            if self.editing:
                self.page='options';self.selection=1;self.nav_armed=False
                self.message='Draft kept. Save it in Controls to apply.'
            elif self.page in ('appearance','confirm-leave'):self.toggle()
            else:self.page=''
            self.change()
