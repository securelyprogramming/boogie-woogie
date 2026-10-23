import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest

from boogie_guest import Guest, read_pairing
from boogie_protocol import InputCapability, config, map_pad


class ProtocolTests(unittest.TestCase):
    def settings(self, **kwargs):
        return dict(baseUrl="https://192.168.1.1:9443", certificateSha256="a"*64,
                    invitationSecret="test-invitation", displayName="Deck", role="player2", **kwargs)

    def test_configuration_requires_private_origin_and_pin(self):
        self.assertEqual(config(self.settings())["role"], "player2")
        for key, value in (("baseUrl","http://192.168.1.1"),("baseUrl","https://192.168.1.1/path"),
                           ("baseUrl","https://8.8.8.8"),("baseUrl","https://user:pass@192.168.1.1"),
                           ("baseUrl","https://192.168.1.1/#secret"),("certificateSha256",""),
                           ("invitationSecret","a\nb"),("displayName","\x00bad"),("role","player4")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                config(dict(self.settings(), **{key:value}))

    def test_pairing_file_permissions_bound_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"pairing.json"
            raw = self.settings(); raw.pop("role"); raw.pop("displayName")
            path.write_text(json.dumps(raw)); path.chmod(0o600)
            self.assertEqual(read_pairing(path), raw)
            path.chmod(0o644)
            with self.assertRaises(ValueError): read_pairing(path)
            path.chmod(0o600); path.write_text("x"*4097)
            with self.assertRaises(ValueError): read_pairing(path)
            link = Path(directory)/"link"; link.symlink_to(path)
            with self.assertRaises(OSError): read_pairing(link)

    def test_authority_and_immutable_port(self):
        cap = InputCapability("player2")
        self.assertIsNone(cap.packet([0]*16))
        for role, port in (("player",0),("player2",0),("player2",True),("player2",None)):
            with self.assertRaises(ValueError): cap.approve(role,port)
        cap.approve("player2",1)
        grant = {"t":"grant","role":"player2","port":1,"nonce":"a"*32}
        self.assertTrue(cap.grant(grant))
        packet = json.loads(cap.packet([0]*16))
        self.assertEqual(packet["seq"],0); self.assertNotIn("port",packet)
        self.assertEqual(json.loads(cap.packet([0]*16))["seq"],1)
        self.assertFalse(cap.grant(dict(grant,role="player")))
        cap.revoke(); self.assertIsNone(cap.packet([1]*16))

    def test_spectator_downgrade_no_inputs(self):
        cap = InputCapability("player2"); cap.approve("spectator",None)
        self.assertTrue(cap.grant({"t":"grant","role":"spectator","port":None,"nonce":"b"*32}))
        self.assertIsNone(cap.packet([1]*16))
        with self.assertRaises(ValueError): cap.approve("player2",1)

    def test_grant_bounds_and_packets(self):
        cap = InputCapability("player"); cap.approve("player",0)
        for nonce in ("", "a"*31, "g"*32, None):
            self.assertFalse(cap.grant({"t":"grant","role":"player","port":0,"nonce":nonce}))
        cap.grant({"t":"grant","role":"player","port":0,"nonce":"b"*32})
        for buttons in ([0]*15, [True]*16, [2]*16):
            with self.assertRaises(ValueError): cap.packet(buttons)

    def test_sdl_buttons_sticks_and_focus(self):
        self.assertEqual(map_pad(1,[0]*6)[8],1)
        self.assertEqual(map_pad(1<<2,[0]*6)[0],1)
        self.assertEqual(map_pad(1<<3,[0]*6)[8],1)
        self.assertEqual(map_pad(1<<13,[0]*6)[6],1)
        self.assertEqual(map_pad(0,[.8,-.8,0,0,1,0])[7],1)
        self.assertEqual(map_pad(0,[.8,-.8,0,0,1,0])[4],1)
        self.assertEqual(map_pad(0,[.8,-.8,0,0,1,0])[12],1)
        self.assertEqual(map_pad(1<<13,[.8,0]),[0]*16)
        self.assertEqual(map_pad(0xFFFF,[1]*6,False),[0]*16)


class FakeSink:
    def __init__(self):
        self.frames = 0; self.audio_frames=0; self.audio_dropped=0; self.pads={}; self.quit_requested=False
        self.buttons=[0]*16
        from boogie_appearance import TrustedArtwork
        self.art=TrustedArtwork()
    def title(self, text): pass
    def video(self, frame): self.frames += 1
    def sound(self, frame): self.audio_frames += frame.samples
    def sample(self): return self.buttons
    def session(self,role,game,title='',nonce=''):
        if (self.art.game,self.art.nonce)!=(game,nonce):self.art.clear(game,nonce)
    def game_art(self,message,capability):return self.art.accept(message,capability)


class WebRTCTests(unittest.IsolatedAsyncioTestCase):
    async def test_bye_without_replacement_media_has_bounded_teardown(self):
        from types import SimpleNamespace
        from aiortc.rtp import RtcpByePacket, RtcpRrPacket
        class NoFrames:
            kind='video';readyState='live'
            async def recv(self):await asyncio.sleep(60)
        original_calls=[]
        async def original(packet):original_calls.append(type(packet).__name__)
        receiver=SimpleNamespace(track=NoFrames(),transport=SimpleNamespace(state='connected'),
                                 _enabled=True,_handle_rtcp_packet=original)
        guest=Guest(dict(role='player2'),FakeSink())
        guest.pc=SimpleNamespace(connectionState='connected',getReceivers=lambda:[receiver])
        guest.capability.approve('player2',1)
        guest.initial_media_timeout=.05
        guest.inspect_receivers()
        await receiver._handle_rtcp_packet(RtcpByePacket(sources=[123]))
        self.assertEqual(guest.rtcp_byes_kept['video'],1)
        await receiver._handle_rtcp_packet(RtcpRrPacket(ssrc=1,reports=[]))
        self.assertEqual(original_calls,['RtcpRrPacket'])
        await asyncio.wait_for(guest.consume(receiver.track),.5)
        self.assertTrue(guest.closed)
        self.assertEqual(guest.reason,'media-timeout')
        self.assertEqual(guest.ended_kind,'video')
        # Closed/revoked receivers retain ordinary BYE teardown behavior.
        await receiver._handle_rtcp_packet(RtcpByePacket(sources=[123]))
        self.assertEqual(original_calls,['RtcpRrPacket','RtcpByePacket'])

    async def test_real_https_pinning_no_redirect_cookie_and_response_bound(self):
        import aiohttp
        from aiohttp import web
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        import datetime
        import hashlib
        import ssl
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"Private test broker")])
        now=datetime.datetime.now(datetime.timezone.utc)
        certificate=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                     .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
                     .not_valid_after(now+datetime.timedelta(days=1)).sign(key,hashes.SHA256()))
        seen=[]; mode=["normal"]
        async def endpoint(request):
            seen.append(dict(request.headers))
            if mode[0]=="redirect": return web.Response(status=302,headers={"Location":"https://127.0.0.1:1/"})
            if mode[0]=="oversize": return web.Response(body=b" "*262145)
            return web.json_response({"protocolVersion":1},headers={"Set-Cookie":"not-for-guests=value"})
        app=web.Application();app.router.add_get('/client-info',endpoint)
        runner=web.AppRunner(app);await runner.setup()
        with tempfile.TemporaryDirectory() as directory:
            cert=Path(directory)/'cert.pem';private=Path(directory)/'key.pem'
            cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
            private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,private)
            site=web.TCPSite(runner,'127.0.0.1',0,ssl_context=context);await site.start()
            port=site._server.sockets[0].getsockname()[1]
            fingerprint=hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).digest()
            guest=Guest(dict(role='spectator',baseUrl='https://127.0.0.1:'+str(port)),FakeSink())
            guest.http=aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=aiohttp.Fingerprint(fingerprint)),
                                              cookie_jar=aiohttp.DummyCookieJar(),trust_env=False)
            try:
                self.assertEqual(await guest.api('/client-info',auth=''),{'protocolVersion':1})
                await guest.api('/client-info',auth='')
                self.assertTrue(all('Cookie' not in headers and 'Authorization' not in headers for headers in seen))
                mode[0]='redirect'
                with self.assertRaises(ValueError):await guest.api('/client-info',auth='')
                mode[0]='oversize'
                with self.assertRaises(ValueError):await guest.api('/client-info',auth='')
            finally:await guest.http.close()
            guest.http=aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=aiohttp.Fingerprint(bytes(32))),trust_env=False)
            try:
                with self.assertRaises(aiohttp.ServerFingerprintMismatch):await guest.api('/client-info',auth='')
            finally:
                await guest.http.close();await runner.cleanup()

    async def test_real_dtls_sctp_vp8_opus_and_input(self):
        """Actual aiortc peers, codecs/DTLS/SCTP and native guest media path.

        Fixture transports offers through the actual guest event() / answer API
        and uses the same grant/immutable-port protocol as Android remote.js.
        Does not claim Android hardware or browser interoperability itself.
        """
        import av
        from fractions import Fraction
        from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, AudioStreamTrack
        class Video(VideoStreamTrack):
            async def recv(self):
                pts, base = await self.next_timestamp()
                frame = av.VideoFrame(64,48,"yuv420p"); frame.pts=pts; frame.time_base=base
                for plane in frame.planes: plane.update(bytes([100])*plane.buffer_size)
                return frame
        host = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        host.addTrack(Video()); host.addTrack(AudioStreamTrack())
        channel = host.createDataChannel("boogie-input",ordered=False,maxRetransmits=0)
        received=[]; granted=asyncio.Event()
        @channel.on("open")
        def opened():
            channel.send(json.dumps({"t":"grant","nonce":"a"*32,"role":"player2","port":1,"gameKey":"sha256:"+"b"*64}))
        @channel.on("message")
        def message(raw):
            value=json.loads(raw);received.append(value);granted.set()
            if value.get('t')=='art-request':
                fixture=json.loads((Path(__file__).resolve().parent/'fixtures/boogie-original-cover.json').read_text())
                fixture.pop('provenance')
                channel.send(json.dumps(dict(fixture,t='game-art',nonce=value['nonce'],gameKey=value['gameKey'])))
        sink=FakeSink(); settings=dict(role="player2",quality="sharp")
        guest=Guest(settings,sink)
        guest.capability.approve("player2",1)
        guest.pc=RTCPeerConnection(RTCConfiguration(iceServers=[]))
        # Reuse production callbacks by running start against a fixture broker.
        original_pc=guest.pc
        async def fake_api(route,body=None,auth=None):
            if route=="/client-info":return {"protocolVersion":1,"roles":["player2"],"ports":{"player2":1}}
            if route=="/join":return {"peerId":"fixture","peerCredential":"c"*32}
            if route.startswith("/events"):
                await asyncio.sleep(60);return {"events":[]}
            if route=="/signal":
                await host.setRemoteDescription(RTCSessionDescription(sdp=body["sdp"],type="answer"));return {}
            return {}
        settings.update(baseUrl="https://127.0.0.1:1",certificateSha256="a"*64,invitationSecret="test",displayName="fixture")
        guest.api=fake_api
        try:
            await original_pc.close()
            await guest.start()
            await guest.event({"type":"approved","peerId":"fixture","role":"player2","port":1})
            await host.setLocalDescription(await host.createOffer())
            await guest.event({"type":"signal","from":"host","signal":{"type":"offer","sdp":host.localDescription.sdp}})
            await asyncio.wait_for(granted.wait(),10)
            sink.buttons[8]=1
            guest.neutral_required=False; guest.sample()
            deadline=asyncio.get_running_loop().time()+4
            while sink.frames < 3 or sink.audio_frames < 960 or not sink.art.jpeg or not any(v.get("buttons",[0]*16)[8] for v in received):
                if asyncio.get_running_loop().time()>deadline: self.fail("Real media/input deadline exceeded")
                guest.sample()
                await asyncio.sleep(.01)
            self.assertGreaterEqual(sink.frames,3);self.assertGreaterEqual(sink.audio_frames,960)
            inputs=[v for v in received if v.get("t")=="input"]
            self.assertTrue(inputs);self.assertTrue(all("port" not in v for v in inputs))
            self.assertEqual(inputs[0]["buttons"],[0]*16)
            self.assertEqual(guest.capability.game_key,"sha256:"+"b"*64)
            self.assertTrue(any(v.get("t")=="quality" and v["profile"]=="sharp" for v in received))
            self.assertTrue(any(v.get('t')=='art-request' for v in received))
            self.assertEqual((sink.art.width,sink.art.height),(40,24))
            previous=guest.capability.nonce
            channel.send(json.dumps({'t':'grant','role':'player2','port':1,'nonce':'f'*32,'padding':'x'*600}))
            await asyncio.sleep(.05)
            self.assertEqual(guest.capability.nonce,previous)
            # Chrome's second offer retires a source with RTCP BYE while its
            # Unified Plan video receiver remains active. The receiver must
            # continue decoding the replacement source instead of ending.
            await host.setLocalDescription(await host.createOffer())
            await guest.event({"type":"signal","from":"host","signal":{"type":"offer","sdp":host.localDescription.sdp}})
            from aiortc.rtp import RtcpByePacket
            video_receiver=next(value for value in guest.pc.getReceivers() if value.track.kind=='video')
            before=sink.frames
            await video_receiver._handle_rtcp_packet(RtcpByePacket(sources=[123456]))
            deadline=asyncio.get_running_loop().time()+2
            while sink.frames <= before:
                if asyncio.get_running_loop().time()>deadline:self.fail("Video did not survive RTP source BYE")
                await asyncio.sleep(.01)
            self.assertFalse(guest.closed)
            self.assertEqual(video_receiver.track.readyState,'live')
            self.assertEqual(guest.rtcp_byes_kept['video'],1)
            # A deliberate local stop remains final; teardown closes SCTP/ICE.
            guest.stop('left');guest.stop('connection-lost')
            self.assertEqual(guest.reason,'left')
        finally:
            await guest.close(); await host.close()


if __name__ == "__main__": unittest.main()
