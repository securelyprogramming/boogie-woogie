import base64
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE','Basic')
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')

from boogie_appearance import AppearanceStore,TrustedArtwork,jpeg_dimensions
from boogie_protocol import InputCapability

ROOT=Path(__file__).resolve().parent
FIXTURE=json.loads((ROOT/'fixtures/boogie-original-cover.json').read_text())
GAME='sha256:'+'a'*64


def capability():
    cap=InputCapability('spectator');cap.approve('spectator',None)
    cap.grant({'t':'grant','role':'spectator','port':None,'nonce':'b'*32,'gameKey':GAME})
    return cap


def packet():
    return dict((k,v) for k,v in dict(FIXTURE,t='game-art',nonce='b'*32,gameKey=GAME).items() if k!='provenance')


class AppearanceTests(unittest.TestCase):
    def test_preferences_are_per_brand_bounded_private_and_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            first=AppearanceStore('rommayo',directory);other=AppearanceStore('emulatormayo',directory)
            self.assertEqual((first.mode,first.dim),('game',82))
            first.save(mode='brand',dim=70)
            self.assertEqual((AppearanceStore('rommayo',directory).mode,AppearanceStore('rommayo',directory).dim),('brand',70))
            self.assertEqual(other.mode,'game');self.assertEqual(first.path.stat().st_mode&0o777,0o600)
            for values in ({'dim':0},{'dim':96},{'dim':True},{'mode':'url'}):
                with self.assertRaises(ValueError):first.save(**values)
            first.path.write_text('x'*4097);again=AppearanceStore('rommayo',directory)
            self.assertEqual((again.mode,again.dim),('game',82))

    def test_jpeg_sof_preflight_rejects_dimensions_truncation_and_other_formats(self):
        raw=base64.b64decode(FIXTURE['data']);self.assertEqual(jpeg_dimensions(raw),(40,24))
        position=raw.index(b'\xff\xc0')
        bomb=bytearray(raw);bomb[position+5:position+7]=(4096).to_bytes(2,'big')
        cases=[b'notjpeg',raw[:10],bytes(bomb),raw*100]
        precision=bytearray(raw);precision[position+4]=16;cases.append(bytes(precision))
        for data in cases:
            with self.assertRaises(ValueError):jpeg_dimensions(data)

    def test_art_binding_exact_fields_hash_base64_and_declared_size(self):
        cap=capability();art=TrustedArtwork();self.assertTrue(art.accept(packet(),cap))
        self.assertEqual((art.width,art.height),(40,24));self.assertFalse(art.accept(packet(),cap))
        for field,bad in [('nonce','c'*32),('gameKey','sha256:'+'d'*64),('width',True),('width',41),('mime','image/svg+xml'),('sha256','0'*64),('data','!')]:
            self.assertFalse(TrustedArtwork().accept(dict(packet(),**{field:bad}),cap))
        self.assertFalse(TrustedArtwork().accept(dict(packet(),url='https://example.invalid'),cap))
        cap.revoke();self.assertFalse(TrustedArtwork().accept(packet(),cap))

    def test_native_background_changes_only_game_margins_and_clears_on_grant(self):
        import av
        from boogie_sdl import Sink
        sink=Sink();cap=capability()
        try:
            with tempfile.TemporaryDirectory() as directory:
                sink.ui.appearance=AppearanceStore('rommayo',directory)
                sink.session('spectator',GAME,'Synthetic image only',cap.nonce)
                self.assertTrue(sink.game_art(packet(),cap));self.assertFalse(sink.game_art(packet(),cap))
                read=sink.lib.SDL_RenderReadPixels;read.restype=C.c_void_p;read.argtypes=[C.c_void_p,C.c_void_p]
                pixel=sink.lib.SDL_ReadSurfacePixel;pixel.restype=C.c_bool
                pixel.argtypes=[C.c_void_p,C.c_int,C.c_int]+[C.POINTER(C.c_uint8)]*4
                destroy=sink.lib.SDL_DestroySurface;destroy.argtypes=[C.c_void_p]
                results=[];original=sink.present
                def capture(renderer):
                    surface=read(renderer,None);values=[]
                    try:
                        for x,y in ((640,400),(40,400)):
                            channels=[C.c_uint8() for _ in range(4)]
                            self.assertTrue(pixel(surface,x,y,*(C.byref(v) for v in channels)))
                            values.append(tuple(v.value for v in channels[:3]))
                    finally:destroy(surface)
                    results.append(values);return original(renderer)
                sink.present=capture
                frame=av.VideoFrame(256,240,'rgba');frame.planes[0].update(bytes([30,90,170,255])*256*240)
                for mode,dim in [('off',82),('brand',82),('game',40),('game',95)]:
                    sink.ui.appearance.save(mode=mode,dim=dim);sink.video(frame)
                self.assertTrue(all(center==(30,90,170) for center,_ in results))
                self.assertEqual(results[0][1],(0,0,0))
                self.assertTrue(any(results[1][1]));self.assertNotEqual(results[2][1],results[3][1])
                sink.session('spectator',GAME,'Same game new grant','c'*32)
                self.assertFalse(sink.art.jpeg);self.assertIsNone(sink.art_texture)
        finally:sink.close()

    def test_native_menu_panel_excludes_underlying_game_pixels_across_repaints(self):
        import av
        from boogie_sdl import Sink
        sink=Sink()
        try:
            read=sink.lib.SDL_RenderReadPixels;read.restype=C.c_void_p;read.argtypes=[C.c_void_p,C.c_void_p]
            pixel=sink.lib.SDL_ReadSurfacePixel;pixel.restype=C.c_bool
            pixel.argtypes=[C.c_void_p,C.c_int,C.c_int]+[C.POINTER(C.c_uint8)]*4
            destroy=sink.lib.SDL_DestroySurface;destroy.argtypes=[C.c_void_p]
            results=[];original=sink.present
            def capture(renderer):
                surface=read(renderer,None)
                try:
                    channels=[C.c_uint8() for _ in range(4)]
                    self.assertTrue(pixel(surface,110,200,*(C.byref(v) for v in channels)))
                    results.append(tuple(v.value for v in channels[:3]))
                finally:destroy(surface)
                return original(renderer)
            sink.present=capture
            for page in ('options','appearance','controls'):
                if page=='controls':sink.ui.controls()
                else:sink.ui.page=page
                for color in ((255,0,0,255),(0,0,255,255)):
                    frame=av.VideoFrame(256,240,'rgba');frame.planes[0].update(bytes(color)*256*240)
                    sink.video(frame)
            self.assertEqual(results,[(13,28,25)]*6)
        finally:sink.close()


if __name__=='__main__':unittest.main()
