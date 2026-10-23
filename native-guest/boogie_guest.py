#!/usr/bin/env python3
"""Native SDL3 / aiortc guest for the existing Boogie Woogie protocol 1.

Android remains authoritative host: no ROM/account credential is sent to guests.
The pairing file is private; stdout/trace contain aggregates and safe status only.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

from boogie_protocol import InputCapability, PEER, ROLES, TOKEN, config
from boogie_appearance import MAX_ART_MESSAGE



def emit(kind, **values):
    print(json.dumps(dict(type=kind, **values), separators=(",", ":")), flush=True)


def read_pairing(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4096 or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError("Pairing file must be owned by this user and readable only by this user")
        raw = os.read(descriptor, 4097)
        if len(raw) > 4096: raise ValueError("Pairing file too large")
        from controller_profiles import unique_object
        value = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(value, dict) or set(value) - {"baseUrl", "certificateSha256", "invitationSecret", "quality"}:
            raise ValueError("Invalid pairing fields")
        return value
    finally:
        os.close(descriptor)


class Guest:
    def __init__(self, settings, sink):
        self.settings, self.sink = settings, sink
        self.capability = InputCapability(settings["role"])
        self.credential = ""; self.peer_id = ""; self.cursor = 0
        self.http = None; self.pc = None; self.dc = None; self.closed = False
        self.pending_ice = []; self.tasks = set(); self.media_kinds = set()
        self.received_video = 0; self.received_audio = 0; self.sent_inputs = 0
        self.neutral_required = True; self.last_buttons = None; self.last_sent = 0
        self.reason = "left"; self.started = time.monotonic(); self.connected_at = None
        self.last_stage = "created"; self.error_class = ""; self.ended_kind = ""
        self.timeline = []; self.rtcp_byes = {"video": 0, "audio": 0}
        self.rtcp_byes_kept = {"video": 0, "audio": 0}
        self.initial_media_timeout = 10
        self.idle_media_timeout = 5
        self.art_attempts=0;self.art_request_at=0

    def stage(self, value):
        self.last_stage = value
        self.timeline.append({"stage":value,"ms":round((time.monotonic()-self.started)*1000)})
        self.timeline = self.timeline[-24:]

    def spawn(self, coroutine, stage="transport"):
        task = asyncio.create_task(coroutine); self.tasks.add(task)
        def done(value):
            self.tasks.discard(value)
            if not value.cancelled() and value.exception():
                name = type(value.exception()).__name__
                self.error_class = name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "Exception"
                self.stage(stage + "-error"); self.stop("transport-error")
        task.add_done_callback(done)
        return task

    def stop(self, reason):
        if self.closed: return
        self.reason = reason; self.closed = True

    async def api(self, route, body=None, auth=None):
        if not re.fullmatch(r"/(?:client-info|join|leave|signal|events\?after=\d+&wait=2)", route): raise ValueError("Invalid broker route")
        headers = {"Accept": "application/json"}
        credential = self.credential if auth is None else auth
        if credential: headers["Authorization"] = "Bearer " + credential
        raw = None
        if body is not None:
            raw = json.dumps(body, separators=(",", ":")).encode()
            if len(raw) > 73728: raise ValueError("Message too large")
            headers["Content-Type"] = "application/json"
        async with self.http.request("GET" if body is None else "POST", self.settings["baseUrl"] + route,
                                     headers=headers, data=raw, allow_redirects=False) as response:
            content = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                content.extend(chunk)
                if len(content) > 262144: raise ValueError("Broker response too large")
            if response.status != 200: raise ValueError("Broker rejected request")
            value = json.loads(content)
            if not isinstance(value, dict): raise ValueError("Invalid broker response")
            return value

    async def start(self):
        import aiohttp
        from aiortc import RTCConfiguration, RTCPeerConnection
        connector = aiohttp.TCPConnector(ssl=aiohttp.Fingerprint(bytes.fromhex(self.settings["certificateSha256"])), limit=4)
        self.http = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=10), trust_env=False,
                                          cookie_jar=aiohttp.DummyCookieJar(), headers={"Cache-Control": "no-store"})
        info = await self.api("/client-info", auth="")
        if info.get("protocolVersion") != 1 or self.settings["role"] not in info.get("roles", []): raise ValueError("Incompatible broker")
        if self.settings["role"] == "player2" and info.get("ports", {}).get("player2") != 1: raise ValueError("Broker does not support Player 2")
        joined = await self.api("/join", {"invite": self.settings["invitationSecret"], "displayName": self.settings["displayName"], "role": self.settings["role"]}, auth="")
        self.settings["invitationSecret"] = ""
        if not TOKEN.fullmatch(joined.get("peerCredential", "")) or not PEER.fullmatch(joined.get("peerId", "")): raise ValueError("Invalid broker capability")
        self.credential, self.peer_id = joined["peerCredential"], joined["peerId"]
        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.stage("joined")
        @self.pc.on("datachannel")
        def datachannel(channel):
            if self.dc is not None or channel.label != "boogie-input": channel.close(); return
            self.dc = channel
            @channel.on("message")
            def message(raw):
                if self.closed or not isinstance(raw,str):return
                length=len(raw.encode())
                if length>MAX_ART_MESSAGE:return
                try: value = json.loads(raw)
                except (ValueError, TypeError): return
                if not isinstance(value, dict): return
                if value.get('t')=='game-art':
                    try:
                        if hasattr(self.sink,'game_art') and self.sink.game_art(value,self.capability):self.art_attempts=3
                    except (ValueError,RuntimeError,OSError):pass
                    return
                if length>512:return
                previous_nonce=self.capability.nonce
                if value.get("t") == "grant" and self.capability.grant(value):
                    self.stage("input-grant")
                    self.neutral_required = True
                    self.send_input([0] * 16, force=True)
                    channel.send(json.dumps({"t": "quality", "nonce": self.capability.nonce, "profile": self.settings.get("quality", "sharp")}))
                    emit("status", state="connected", role=self.capability.role, port=self.capability.port,
                         gameKey=self.capability.game_key)
                    if hasattr(self.sink,'session'):
                        self.sink.session(self.capability.role,self.capability.game_key,value.get('gameTitle','Host game'),self.capability.nonce)
                    if previous_nonce!=self.capability.nonce:
                        self.art_attempts=0;self.art_request_at=0;self.request_art()
                elif value.get('t')=='mapping-setup' and hasattr(self.sink,'mapping_request'):
                    if self.sink.mapping_request(value,self.capability):
                        self.neutral_required=True;self.send_input([0]*16,force=True)
            @channel.on("close")
            def closed():
                self.capability.revoke(); self.stop("channel-closed")
        @self.pc.on("connectionstatechange")
        async def connection():
            if self.pc.connectionState == "connected":
                self.stage("peer-connected")
                self.connected_at = time.monotonic()
                self.sink.title("Connected - " + ("watching" if self.capability.port is None else "Player " + str(self.capability.port + 1)))
            elif self.pc.connectionState in ("failed", "closed"): self.stop("connection-lost")
        @self.pc.on("track")
        def track(value):
            if value.kind not in ("video", "audio") or value.kind in self.media_kinds: value.stop(); return
            self.media_kinds.add(value.kind); self.stage(value.kind + "-track")
            self.spawn(self.consume(value), value.kind)
        self.sink.title("Waiting for host approval")
        emit("status", state="waiting", role=self.capability.role)
        self.spawn(self.poll(), "broker-poll")

    async def consume(self, track):
        import av
        from aiortc.mediastreams import MediaStreamError
        resampler = av.AudioResampler(format="s16", layout="stereo", rate=48000) if track.kind == "audio" else None
        first_frame = True
        try:
            while not self.closed:
                frame = await asyncio.wait_for(track.recv(), self.initial_media_timeout if first_frame else self.idle_media_timeout)
                first_frame = False
                if track.kind == "video":
                    if not self.received_video: self.stage("first-video-frame")
                    self.received_video += 1; self.sink.video(frame)
                else:
                    if not self.received_audio: self.stage("first-audio-frame")
                    self.received_audio += 1
                    for output in resampler.resample(frame): self.sink.sound(output)
        except MediaStreamError:
            if not self.closed:
                self.ended_kind = track.kind; self.stage(track.kind + "-ended")
                self.stop("media-ended")
        except asyncio.TimeoutError:
            if not self.closed:
                self.ended_kind = track.kind; self.stage(track.kind + "-timeout")
                self.stop("media-timeout")

    def inspect_receivers(self):
        # Record only protocol state / codec names. No SDP, SSRC, ICE addresses,
        # peer IDs or capabilities.
        for receiver in self.pc.getReceivers():
            if getattr(receiver, "_boogie_rtcp_wrapped", False): continue
            original = receiver._handle_rtcp_packet
            async def wrapped(packet, original=original, receiver=receiver):
                from aiortc.rtp import RtcpByePacket
                if isinstance(packet, RtcpByePacket):
                    kind = receiver.track.kind
                    self.rtcp_byes[kind] += 1; self.stage(kind + "-rtcp-bye")
                    # Chrome retires an old RTP/RTX SSRC during negotiation.
                    # A BYE is scoped to those sources, not the SDP receiver.
                    # aiortc1.15 otherwise stops its only decoder permanently,
                    # ending the live track before replacement-source frames.
                    # Keep this owned receiver while its negotiated direction,
                    # authenticated session and DTLS transport remain active.
                    # Actual peer/room revocation still closes all receivers.
                    if (not self.closed and self.capability.approved and receiver.track.readyState == "live"
                            and getattr(receiver, "_enabled", False) and receiver.transport.state == "connected"
                            and self.pc.connectionState in ("connecting", "connected")):
                        self.rtcp_byes_kept[kind] += 1
                        self.stage(kind + "-source-turnover")
                        return
                await original(packet)
            receiver._handle_rtcp_packet = wrapped
            receiver._boogie_rtcp_wrapped = True

    async def event(self, value):
        if value.get("type") == "approved":
            if value.get("peerId") != self.peer_id: raise ValueError("Approval identity mismatch")
            assigned = value.get("port", 0 if value.get("role") == "player" else None)
            self.capability.approve(value.get("role"), assigned)
            if hasattr(self.sink,'session'):self.sink.session(self.capability.role,'','Waiting for host game')
            self.stage("approved")
            emit("status", state="approved", role=self.capability.role, port=self.capability.port)
        elif value.get("type") == "signal" and value.get("from") == "host" and self.capability.approved:
            from aiortc import RTCSessionDescription
            from aiortc.sdp import candidate_from_sdp
            message = value.get("signal")
            if not isinstance(message, dict): raise ValueError("Invalid host signal")
            if message.get("type") == "offer":
                sdp = message.get("sdp")
                if not isinstance(sdp, str) or len(sdp.encode()) > 65536: raise ValueError("Invalid offer")
                await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
                self.inspect_receivers(); self.stage("remote-offer")
                for candidate in self.pending_ice: await self.pc.addIceCandidate(candidate)
                self.pending_ice.clear()
                await self.pc.setLocalDescription(await self.pc.createAnswer())
                await self.api("/signal", {"target": "host", "type": "answer", "sdp": self.pc.localDescription.sdp})
                self.stage("answer-sent")
            elif message.get("type") == "candidate":
                data = message.get("candidate")
                if not isinstance(data, dict) or not isinstance(data.get("candidate"), str) or len(data["candidate"]) > 4096: raise ValueError("Invalid candidate")
                raw = data["candidate"]
                if not raw: return
                if not raw.startswith("candidate:"): raise ValueError("Invalid candidate format")
                candidate = candidate_from_sdp(raw[10:])
                candidate.sdpMid, candidate.sdpMLineIndex = data.get("sdpMid"), data.get("sdpMLineIndex")
                if candidate.sdpMid is not None and (not isinstance(candidate.sdpMid, str) or len(candidate.sdpMid) > 80): raise ValueError("Invalid candidate mid")
                if candidate.sdpMLineIndex is not None and (type(candidate.sdpMLineIndex) is not int or not 0 <= candidate.sdpMLineIndex <= 8): raise ValueError("Invalid candidate index")
                if self.pc.remoteDescription: await self.pc.addIceCandidate(candidate)
                elif len(self.pending_ice) < 64: self.pending_ice.append(candidate)
                else: raise ValueError("Too many candidates")
        elif value.get("type") == "resync_required": self.stop("fresh-approval-required")

    async def poll(self):
        errors = 0
        while not self.closed:
            try:
                result = await self.api("/events?after=" + str(self.cursor) + "&wait=2")
                events = result.get("events")
                if not isinstance(events, list) or len(events) > 64: raise ValueError("Invalid events")
                for value in events:
                    if not isinstance(value, dict) or type(value.get("id")) is not int or value["id"] <= self.cursor: raise ValueError("Invalid cursor")
                    self.cursor = value["id"]; await self.event(value)
                errors = 0
                if not events: await asyncio.sleep(.1)
            except (ValueError, OSError, asyncio.TimeoutError):
                errors += 1
                if errors >= 3: self.stop("broker-connection-lost")
                else: await asyncio.sleep(.5)

    def send_input(self, buttons, force=False):
        now = time.monotonic()
        if not self.dc or self.dc.readyState != "open" or self.dc.bufferedAmount > 4096: return
        if not force and now - self.last_sent < 1 / 60: return
        if not force and buttons == self.last_buttons and now - self.last_sent < .1: return
        packet = self.capability.packet(buttons)
        if packet:
            self.dc.send(packet); self.sent_inputs += 1; self.last_buttons = list(buttons); self.last_sent = now

    def request_art(self):
        now=time.monotonic()
        if (self.closed or not self.dc or self.dc.readyState!='open' or not self.capability.approved
                or not self.capability.nonce or not self.capability.game_key or self.art_attempts>=3 or now<self.art_request_at):return
        self.dc.send(json.dumps({'t':'art-request','nonce':self.capability.nonce,'gameKey':self.capability.game_key},separators=(',',':')))
        self.art_attempts+=1;self.art_request_at=now+2

    def sample(self):
        self.request_art()
        buttons = self.sink.sample()
        if self.neutral_required:
            if not any(buttons): self.neutral_required = False
            buttons = [0] * 16
        self.send_input(buttons)
        if self.sink.quit_requested:
            self.stage("sdl-" + getattr(self.sink, "quit_reason", "quit")); self.stop("left")

    def report(self):
        elapsed = max(.001, time.monotonic() - (self.connected_at or self.started))
        receivers = []
        if self.pc:
            for receiver in self.pc.getReceivers()[:8]:
                codecs = getattr(receiver, "_RTCRtpReceiver__codecs", {})
                receivers.append({"kind":receiver.track.kind,"trackState":receiver.track.readyState,
                                  "dtlsState":receiver.transport.state,
                                  "codecs":sorted({str(c.name)[:16] for c in codecs.values()})})
        appearance=getattr(getattr(self.sink,'ui',None),'appearance',None)
        artwork=getattr(self.sink,'art',None)
        return {"schema": 1, "transport": "aiortc-sdl3-native", "role": self.capability.role,
                "port": self.capability.port, "reason": self.reason, "connected": self.connected_at is not None,
                "videoFrames": self.received_video, "shownFrames": self.sink.frames,
                "audioFrames": self.received_audio, "audioSamples": self.sink.audio_frames,
                "audioQueueResets": self.sink.audio_dropped, "inputPackets": self.sent_inputs,
                "shownFps": round(self.sink.frames / elapsed, 2), "controllers": len(self.sink.pads),
                "gameKey": self.capability.game_key,"lastStage":self.last_stage,
                "errorClass":self.error_class,"endedKind":self.ended_kind,
                "peerState":self.pc.connectionState if self.pc else "new",
                "iceState":self.pc.iceConnectionState if self.pc else "new",
                "receivers":receivers,"timeline":list(self.timeline),"rtcpByes":dict(self.rtcp_byes),
                "rtcpSourceTurnovers":dict(self.rtcp_byes_kept),
                "backdropMode":appearance.mode if appearance else 'unknown',
                "backdropDim":appearance.dim if appearance else 0,
                "approvedArtReady":bool(artwork and artwork.jpeg),
                "approvedArtWidth":artwork.width if artwork else 0,"approvedArtHeight":artwork.height if artwork else 0,
                "artRequests":self.art_attempts}

    async def close(self):
        self.send_input([0] * 16, force=True)
        # Give the reliable local queue a turn before closing SCTP. Host also has
        # independent stale-input timeout and peer revocation release.
        await asyncio.sleep(.05)
        self.closed = True; self.capability.revoke()
        for task in list(self.tasks): task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)
        if self.http and self.credential:
            try: await asyncio.wait_for(self.api("/leave", {}), 2)
            except Exception: pass
        self.credential = ""
        if self.pc: await self.pc.close()
        if self.http: await self.http.close()


async def run(options):
    from boogie_sdl import Sink
    pairing = read_pairing(options.config)
    if options.quality: pairing["quality"] = options.quality
    settings = config(dict(pairing, role=options.role, displayName=options.name))
    mapping = None
    if options.controls_file:
        from controller_profiles import BUTTONS, validate, unique_object
        with options.controls_file.open("rb") as stream: raw = stream.read(4097)
        if len(raw) > 4096: raise ValueError("Controller profile too large")
        profile = validate(json.loads(raw, object_pairs_hook=unique_object))
        physical = ("south", "east", "west", "north", "back", "guide", "start", "left_stick", "right_stick", "left_shoulder", "right_shoulder", "dpad_up", "dpad_down", "dpad_left", "dpad_right")
        actions = {"a":8,"b":0,"select":2,"start":3,"up":4,"down":5,"left":6,"right":7,"none":-1}
        mapping = tuple(-1 if name == "guide" else actions[profile["buttons"][name]] for name in physical)
    sink = Sink(deck=options.fullscreen,library=options.sdl_library,mapping=mapping,brand=options.app_brand,volume=options.volume,muted=options.mute,show_fps=options.show_fps)
    guest = Guest(settings, sink)
    for signum in (signal.SIGINT, signal.SIGTERM):
        try: asyncio.get_running_loop().add_signal_handler(signum, guest.stop, "terminated")
        except NotImplementedError: signal.signal(signum, lambda *_: guest.stop("terminated"))
    try:
        await guest.start()
        last_report = time.monotonic()
        while not guest.closed:
            guest.sample()
            if options.seconds and time.monotonic() - guest.started >= options.seconds: guest.stop("test-deadline")
            if time.monotonic() - last_report > 2:
                emit("metrics", **guest.report()); last_report = time.monotonic()
            await asyncio.sleep(.008)
    finally:
        report = guest.report()
        await guest.close(); sink.close()
        if options.trace:
            options.trace.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(options.trace) + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w") as stream: json.dump(report, stream, indent=2)
            os.replace(str(options.trace) + ".tmp", options.trace)
        emit("status", state="disconnected", **report)


def percentage(value):
    try: result=int(value)
    except ValueError: raise argparse.ArgumentTypeError("Use an integer from 0 to 100") from None
    if not 0<=result<=100: raise argparse.ArgumentTypeError("Use an integer from 0 to 100")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--role", choices=tuple(ROLES), default="player2")
    parser.add_argument("--name", default="Native guest")
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--sdl-library", type=str, help="Absolute path to an SDL3 shared library; otherwise use the system SDL3 installation")
    parser.add_argument("--controls-file", type=Path, help="Existing validated native gameplay button profile")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--quality", choices=("smooth","balanced","sharp"), help="Override the pairing video profile")
    parser.add_argument("--volume", type=percentage, default=100, help="Local audio volume, 0-100")
    parser.add_argument("--mute", action="store_true")
    parser.add_argument("--show-fps", action="store_true", help="Display measured incoming video frame rate")
    parser.add_argument('--app-brand',choices=('rommayo','emulatormayo'),default='emulatormayo')
    parser.add_argument("--seconds", type=float, default=0, help="Bounded diagnostic run")
    parser.add_argument("--self-test", action="store_true")
    options = parser.parse_args()
    if options.self_test:
        from boogie_sdl import Sink
        import av
        from aiortc import RTCPeerConnection
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy"); os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        sink = Sink(library=options.sdl_library,brand=options.app_brand,volume=options.volume,muted=options.mute,show_fps=options.show_fps); sink.sample()
        frame = av.VideoFrame(256, 240, "yuv420p")
        for plane in frame.planes: plane.update(bytes(plane.buffer_size))
        sink.video(frame)
        sink.session('player2','sha256:'+'a'*64,'Native menu check - no game artwork')
        sink.repaint();sink.click(60,40)
        assert sink.ui.page=='options' and sink.ui.heading=='PLAYER 2'
        assert sink.sample()==[0]*16
        sink.repaint();sink.close()
        emit("self-test", passed=True, nativeSdl=True, nativeOptions=True, localMenuInputNeutral=True,
             aiortcImported=bool(RTCPeerConnection)); return
    if options.config is None: parser.error("--config is required")
    try: asyncio.run(run(options))
    except Exception:
        # Exceptions may contain SDP, invitation bodies or peer credentials.
        emit("status", state="error", message="Native co-op connection failed; check the trusted pairing and host approval.")
        raise SystemExit(1)


if __name__ == "__main__": main()
