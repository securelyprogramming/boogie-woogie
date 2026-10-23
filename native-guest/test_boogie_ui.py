import ctypes as C
import json
import os
from pathlib import Path
import tempfile
import unittest

from boogie_protocol import InputCapability
from boogie_ui import ACTIONS, MappingStore, NativeUI, defaults, mapped, sources, validate

GAME='sha256:'+'a'*64
DEVICE='b'*64


class ModelTests(unittest.TestCase):
    def model(self,directory=None):
        value=NativeUI(store=MappingStore(directory))
        value.set_session('player2',GAME,'Native controls test')
        value.set_devices([{'key':DEVICE,'label':'Deck controller'}])
        return value

    def test_defaults_and_multi_bindings_direction_inversion(self):
        value=defaults();self.assertEqual(mapped(sources(1,[0]*6),value)[8],1)
        self.assertEqual(mapped(sources(1<<3,[0]*6),value)[8],1)
        value['6'],value['7']=value['7'],value['6']
        self.assertEqual(mapped(sources(0,[-1,0]),value)[7],1)
        self.assertEqual(mapped({'b11','b12'},defaults()),[0]*16)
        for invalid in ({},dict(defaults(),**{'8':['b5']}),dict(defaults(),**{'8':['b0']*9})):
            with self.assertRaises(ValueError):validate(invalid)

    def test_options_resume_leave_and_neutral_arm(self):
        value=self.model();value.toggle();self.assertEqual(value.rows(),['Resume game','Controls / button mapper','Appearance','Leave session'])
        value.navigation({'b0'},0);self.assertEqual(value.page,'options')
        value.navigation(set(),.1);value.navigation({'b0'},.2);self.assertEqual(value.page,'')
        value.toggle();value.activate(3);self.assertFalse(value.leave)
        self.assertEqual(value.page,'confirm-leave');self.assertEqual(value.selection,0)
        value.navigation({'b0'},.3);self.assertFalse(value.leave)
        value.navigation(set(),.4);value.navigation({'b0'},.5)
        self.assertEqual(value.page,'options');self.assertFalse(value.leave)
        value.activate(3);value.toggle();self.assertFalse(value.leave)
        value.activate(3);value.navigation(set(),.6);value.navigation({'b12'},.7)
        value.navigation(set(),.8);value.navigation({'b0'},.9);self.assertTrue(value.leave)

    def test_wizard_neutral_then_fresh_press_each_step(self):
        value=self.model();value.controls();value.activate(1)
        first=value.capture
        value.capture_sources(DEVICE,{'b0'});self.assertEqual(value.capture,first)
        for index,(_,action) in enumerate(ACTIONS):
            value.capture_sources(DEVICE,set());value.capture_sources(DEVICE,{'b'+str(index if index!=5 else 9)})
            self.assertEqual(value.draft[str(action)],[('b'+str(index if index!=5 else 9))])
        self.assertIsNone(value.capture);self.assertFalse(value.nav_armed)

    def test_add_binding_and_draft_back_preservation(self):
        value=self.model();value.controls();value.mode='add';value.activate(6)
        value.capture_sources(DEVICE,set());value.capture_sources(DEVICE,{'b9'})
        self.assertIn('b9',value.draft['8']);self.assertIn('b0',value.draft['8'])
        draft=json.dumps(value.draft,sort_keys=True);value.toggle();self.assertEqual(value.page,'options')
        value.controls();self.assertEqual(json.dumps(value.draft,sort_keys=True),draft)
        self.assertEqual(value.bindings(DEVICE),defaults())

    def test_scopes_game_controller_session_are_local(self):
        with tempfile.TemporaryDirectory() as directory:
            value=self.model(directory);value.controls();value.draft['8']=['b10'];value.scope='game';value.activate(12)
            self.assertEqual(value.bindings(DEVICE)['8'],['b10'])
            value.set_session('player2','sha256:'+'c'*64,'Different game')
            self.assertEqual(value.bindings(DEVICE)['8'],defaults()['8'])
            value.controls();value.draft['8']=['b9'];value.scope='device';value.activate(12)
            again=self.model(directory);again.set_session('player2','sha256:'+'d'*64,'Other game')
            self.assertEqual(again.bindings(DEVICE)['8'],['b9'])
            again.controls();again.draft['8']=['b7'];again.scope='session';again.activate(12)
            self.assertEqual(again.bindings(DEVICE)['8'],['b7'])
            self.assertEqual(self.model(directory).bindings(DEVICE)['8'],['b10'])
            override=self.model(directory);override.controls();override.draft['8']=['b6'];override.scope='device';override.activate(12)
            self.assertEqual(override.bindings(DEVICE)['8'],['b10'])
            self.assertTrue(all(p.stat().st_mode&0o077==0 for p in Path(directory).rglob('*.json')))

    def test_host_invite_authority_dedup_rate_and_draft_preservation(self):
        value=self.model();cap=InputCapability('player2');cap.approve('player2',1)
        cap.grant({'t':'grant','role':'player2','port':1,'nonce':'e'*32,'gameKey':GAME})
        message={'t':'mapping-setup','nonce':'e'*32,'requestId':'f'*32,'role':'player2','port':1,'gameKey':GAME}
        for key,bad in (('nonce','d'*32),('role','player'),('port',True),('gameKey','sha256:'+'c'*64),('requestId','g'*32)):
            self.assertFalse(value.request_mapping(dict(message,**{key:bad}),cap,1))
        self.assertTrue(value.request_mapping(message,cap,1));value.draft['8']=['b9']
        self.assertFalse(value.request_mapping(message,cap,5))
        self.assertFalse(value.request_mapping(dict(message,requestId='1'*32),cap,1.5))
        self.assertFalse(value.request_mapping(dict(message,requestId='2'*32),cap,5))
        self.assertEqual(value.draft['8'],['b9'])
        self.assertEqual(cap.port,1)
        for index in range(40):value.request_mapping(dict(message,requestId=format(index,'032x')),cap,10+index*3)
        self.assertLessEqual(len(value.invites),32)

    def test_spectator_cannot_open_editor_or_accept_invites(self):
        value=self.model();value.set_session('spectator',GAME,'Watching');value.toggle()
        self.assertEqual(value.rows(),['Resume watching','Appearance','Leave session']);self.assertFalse(value.controls())
        cap=InputCapability('spectator');cap.approve('spectator',None)
        self.assertFalse(value.request_mapping({},cap))

    def test_game_change_and_disconnect_do_not_overwrite_draft(self):
        value=self.model();value.controls();value.draft['8']=['b9']
        value.set_session('player2','sha256:'+'c'*64,'Another title');value.set_devices([])
        self.assertEqual(value.draft_game,GAME);self.assertEqual(value.draft['8'],['b9'])
        self.assertEqual(value.selected_device,DEVICE)


class NativeSDLTests(unittest.TestCase):
    def test_persistent_options_and_role_pixels_survive_repeated_menu_frames(self):
        os.environ.setdefault('SDL_VIDEODRIVER','dummy');os.environ.setdefault('SDL_AUDIODRIVER','dummy')
        from boogie_sdl import Sink
        sink=Sink()
        read=sink.lib.SDL_RenderReadPixels;read.restype=C.c_void_p;read.argtypes=[C.c_void_p,C.c_void_p]
        pixel=sink.lib.SDL_ReadSurfacePixel;pixel.restype=C.c_bool
        pixel.argtypes=[C.c_void_p,C.c_int,C.c_int]+[C.POINTER(C.c_uint8)]*4
        destroy=sink.lib.SDL_DestroySurface;destroy.argtypes=[C.c_void_p]
        original=sink.present
        def checked_present(renderer):
            surface=read(renderer,None);self.assertTrue(surface)
            try:
                for left,right in ((72,212),(900,1060)):
                    bright=0
                    for y in range(29,49,2):
                        for x in range(left,right,2):
                            channels=[C.c_uint8() for _ in range(4)]
                            self.assertTrue(pixel(surface,x,y,*(C.byref(c) for c in channels)))
                            if max(c.value for c in channels[:3])>150:bright+=1
                    self.assertGreater(bright,20,'Persistent options/role text disappeared')
            finally:destroy(surface)
            return original(renderer)
        try:
            sink.session('player2',GAME,'No game artwork')
            sink.present=checked_present;sink.ui.toggle();sink.repaint()
            sink.ui.set_devices([{'key':DEVICE,'label':'Controller'}]);sink.ui.controls()
            sink.repaint();sink.repaint();sink.repaint()
        finally:sink.close()

    def test_controller_options_chord_releases_and_quarantines_game_input(self):
        os.environ.setdefault('SDL_VIDEODRIVER','dummy');os.environ.setdefault('SDL_AUDIODRIVER','dummy')
        from boogie_sdl import Sink
        sink=Sink();held=[0]
        try:
            sink.window_flags=lambda _:0x200
            def pads(count):
                C.cast(count,C.POINTER(C.c_int))[0]=1
                return (C.c_uint32*1)(123)
            sink.get_pads=pads;sink.free=lambda _:None;sink.open_pad=lambda _:123
            sink.close_pad=lambda _:None;sink.pad_connected=lambda _:True
            sink.pad_vendor=lambda _:1;sink.pad_product=lambda _:2;sink.pad_serial=lambda _:b''
            sink.pad_name=lambda _:b'Test controller';sink.pad_axis=lambda *_:0
            sink.pad_button=lambda _,index:bool(held[0]&(1<<index))
            sink.sample();held[0]=1;self.assertEqual(sink.sample()[8],1)
            held[0]=(1<<7)|(1<<8);self.assertEqual(sink.sample(),[0]*16)
            self.assertEqual(sink.ui.page,'options')
            held[0]=1;sink.sample();self.assertEqual(sink.ui.page,'options')
            held[0]=0;sink.sample();held[0]=1;self.assertEqual(sink.sample(),[0]*16)
            self.assertEqual(sink.ui.page,'')
            self.assertEqual(sink.sample(),[0]*16)
            held[0]=0;sink.sample();held[0]=1;self.assertEqual(sink.sample()[8],1)
            # Short View and Menu stay Select/Start during gameplay.
            held[0]=1<<4;self.assertEqual(sink.sample()[2],1)
            held[0]=1<<6;self.assertEqual(sink.sample()[3],1)
        finally:sink.close()

    def test_actual_sdl_keyboard_edges_click_options_render_and_neutral(self):
        os.environ.setdefault('SDL_VIDEODRIVER','dummy');os.environ.setdefault('SDL_AUDIODRIVER','dummy')
        from boogie_sdl import Sink,KeyboardEvent
        sink=Sink()
        try:
            sink.window_flags=lambda _:0x200
            sink.session('player2',GAME,'Native menu - no game artwork')
            push=sink.lib.SDL_PushEvent;push.restype=C.c_bool;push.argtypes=[C.c_void_p]
            def tap(code,repeat=False):
                for kind,down in ((0x300,True),(0x301,False)):
                    event=KeyboardEvent();event.type=kind;event.scancode=code;event.down=down;event.repeat=repeat
                    self.assertTrue(push(C.byref(event)))
            tap(41);self.assertEqual(sink.sample(),[0]*16)
            self.assertEqual(sink.ui.page,'options')
            tap(41,True);sink.sample();self.assertEqual(sink.ui.page,'options')
            tap(81);tap(40);sink.sample();self.assertEqual(sink.ui.page,'controls')
            self.assertEqual(sink.ui.heading,'PLAYER 2')
            sink.ui.activate(13);sink.ui.activate(0);sink.repaint()
            sink.click(60,40);self.assertEqual(sink.ui.page,'options')
            self.assertEqual(sink.sample(),[0]*16)
            sink.ui.activate(3);sink.sample();self.assertFalse(sink.quit_requested)
            self.assertEqual(sink.ui.page,'confirm-leave')
            sink.ui.activate(1);sink.sample();self.assertTrue(sink.quit_requested)
            self.assertEqual(sink.quit_reason,'leave-menu')
        finally:sink.close()


if __name__=='__main__':unittest.main()
