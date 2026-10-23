"""Standalone entrypoint boundaries without network or device pairing."""
import ctypes as C
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from boogie_protocol import config
from boogie_sdl import find_sdl_library
ROOT=Path(__file__).resolve().parent
class StandaloneTests(unittest.TestCase):
    def settings(self,origin):
        return dict(baseUrl=origin,certificateSha256='a'*64,invitationSecret='synthetic-invitation',displayName='Test guest',role='player2')
    def test_loopback_unspecified_public_and_hostnames_rejected(self):
        for origin in ('https://127.0.0.1:9443','https://[::1]:9443','https://0.0.0.0:9443','https://[::]:9443','https://localhost:9443','https://8.8.8.8','https://[::ffff:127.0.0.1]:9443'):
            with self.subTest(origin=origin),self.assertRaises(ValueError):config(self.settings(origin))
        self.assertEqual(config(self.settings('https://192.168.0.2:9443'))['role'],'player2')
    def test_help_requires_no_media_dependencies_or_pairing(self):
        result=subprocess.run([sys.executable,str(ROOT/'boogie_guest.py'),'--help'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0);self.assertIn('--sdl-library',result.stdout);self.assertNotIn('mayo-native-prototype',result.stdout)
    def test_loopback_cli_rejected_before_media_and_sdl_start(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pairing.private.json';p=self.settings('https://127.0.0.1:9443');p.pop('displayName');p.pop('role')
            path.write_text(json.dumps(p));path.chmod(0o600)
            result=subprocess.run([sys.executable,str(ROOT/'boogie_guest.py'),'--config',str(path)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,1);self.assertNotIn(p['invitationSecret'],result.stdout+result.stderr)
            self.assertEqual(json.loads(result.stdout)['state'],'error')
    def test_explicit_library_is_absolute_existing_file(self):
        for name in ('SDL3.dll','missing/libSDL3.so'):
            with self.assertRaises(ValueError):find_sdl_library(name)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'library';path.write_bytes(b'synthetic path fixture')
            self.assertEqual(find_sdl_library(str(path)),str(path))
            with patch.dict(os.environ,{'BOOGIE_SDL3_LIBRARY':str(path)}):self.assertEqual(find_sdl_library(),str(path))
    def test_local_audio_gain_and_optional_fps_use_sdl_frontend_only(self):
        os.environ.setdefault('SDL_VIDEODRIVER','dummy');os.environ.setdefault('SDL_AUDIODRIVER','dummy')
        from boogie_sdl import Sink
        for muted,expected in ((False,.35),(True,0.0)):
            sink=Sink(volume=35,muted=muted,show_fps=True)
            try:
                self.assertTrue(sink.audio)
                gain=sink.lib.SDL_GetAudioStreamGain;gain.restype=C.c_float;gain.argtypes=[C.c_void_p]
                self.assertAlmostEqual(gain(sink.audio),expected,places=3)
                self.assertTrue(sink.show_fps);sink.repaint()
            finally:sink.close()
    def test_invalid_volume_cli_is_rejected(self):
        result=subprocess.run([sys.executable,str(ROOT/'boogie_guest.py'),'--volume','101'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2);self.assertIn('0 to 100',result.stderr)
if __name__=='__main__':unittest.main()
