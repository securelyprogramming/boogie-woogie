#!/usr/bin/env python3
"""Private, single-room HTTPS admission and WebRTC signaling prototype.

No media, controller packets, ROMs or credentials are logged or persisted here.
Startup configuration contains secrets; keep it outside any public web root.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import ssl
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MAX_BODY = 72 * 1024
MAX_SDP = 64 * 1024
MAX_CANDIDATE = 2048
MAX_EVENTS = 256
MAX_PEERS = 8
INVITE_TTL = 600
PEER_IDLE = 30
PROTOCOL_VERSION = 1
ROLES = ("player", "player2", "spectator")
ROOT = Path(__file__).resolve().parent.parent
PUBLIC_ASSETS = {
    "/": (ROOT / "web/index.html", "text/html; charset=utf-8"),
    "/index.html": (ROOT / "web/index.html", "text/html; charset=utf-8"),
    "/web/guest.css": (ROOT / "web/guest.css", "text/css; charset=utf-8"),
    "/web/guest.js": (ROOT / "web/guest.js", "application/javascript; charset=utf-8"),
    "/web/controller-mapper.css": (ROOT / "web/controller-mapper.css", "text/css; charset=utf-8"),
    **{"/web/" + name: (ROOT / "web" / name, "application/javascript; charset=utf-8")
       for name in ("controller-mapper-model.js", "controller-mapper.js")},
    **{"/assets/" + name: (ROOT / "assets" / name, "application/javascript; charset=utf-8")
       for name in ("layout-model.js", "layout-editor.js", "video-model.js", "video-quality.js", "remote.js", "backdrop-model.js", "backdrop.js", "viewport-capture.js")},
}
PUBLIC_ASSETS.update({
    "/assets/backdrop.css": (ROOT / "assets/backdrop.css", "text/css; charset=utf-8"),
    **{"/assets/backgrounds/" + name + ".svg": (ROOT / "assets/backgrounds" / (name + ".svg"), "image/svg+xml") for name in ("rommayo", "emulatormayo")},
})
WEB_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
           "media-src 'self' blob:; img-src 'self' blob: data:; base-uri 'none'; "
           "frame-ancestors 'none'; form-action 'self'")


def role_port(role):
    return {"player": 0, "player2": 1, "spectator": None}.get(role)



class APIError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


@dataclass
class Peer:
    peer_id: str
    credential: str
    display_name: str
    requested_role: str
    last_seen: float
    role: str = "pending"
    events: deque = field(default_factory=deque)
    candidates: int = 0


class Room:
    def __init__(self, clock=time.monotonic, wall_clock=time.time):
        self.clock, self.wall_clock = clock, wall_clock
        self.session_id = secrets.token_urlsafe(18)
        self.host_key = secrets.token_urlsafe(32)
        self.invite_key = secrets.token_urlsafe(32)
        self.created = clock()
        self.invite_expires_at = int(wall_clock() + INVITE_TTL)
        self.peers: dict[str, Peer] = {}
        self.host_events = deque()
        self.sequence = 0
        self.stopped = False
        self.rate = defaultdict(deque)
        self.cv = threading.Condition(threading.RLock())

    def configuration(self, url: str, fingerprint: str):
        return {"sessionId": self.session_id, "baseUrl": url,
                "hostCredential": self.host_key, "invitationSecret": self.invite_key,
                "inviteExpiresAt": self.invite_expires_at,
                "certificateSha256": fingerprint,
                "mode": "shared-controller", "playerPort": 1}

    def _limit(self, key, maximum, interval=60):
        now = self.clock()
        q = self.rate[key]
        while q and now - q[0] >= interval:
            q.popleft()
        if len(q) >= maximum:
            raise APIError(429, "rate_limited")
        q.append(now)
        # Avoid indefinite growth from old anonymous IP buckets.
        if len(self.rate) > 4096:
            for old_key in list(self.rate):
                old = self.rate[old_key]
                if not old or now - old[-1] >= interval:
                    del self.rate[old_key]

    def _emit(self, recipient: str, kind: str, **payload):
        self.sequence += 1
        event = {"id": self.sequence, "type": kind, **payload}
        q = self.host_events if recipient == "host" else self.peers[recipient].events
        if len(q) >= MAX_EVENTS:
            # Never silently drop an ICE candidate or offer. Polling after this
            # overflow gives an explicit error and the client must rejoin.
            q.clear()
            q.append({"id": self.sequence, "type": "resync_required"})
        else:
            q.append(event)
        self.cv.notify_all()

    def _remove(self, peer_id, reason):
        peer = self.peers.pop(peer_id)
        self._emit("host", "peer_left", peerId=peer_id, reason=reason, role=peer.role, port=role_port(peer.role))
        self.cv.notify_all()

    def _expire(self):
        for peer_id, peer in list(self.peers.items()):
            if self.clock() - peer.last_seen >= PEER_IDLE:
                self._remove(peer_id, "idle_timeout")

    def _auth(self, credential, host_only=False):
        self._expire()
        if self.stopped:
            raise APIError(410, "session_stopped")
        if not isinstance(credential, str) or not credential or len(credential) > 128 or not credential.isascii():
            raise APIError(401, "unauthorized")
        if hmac.compare_digest(credential.encode("utf-8"), self.host_key.encode("ascii")):
            return "host"
        if not host_only:
            for peer in self.peers.values():
                if hmac.compare_digest(credential.encode("utf-8"), peer.credential.encode("ascii")):
                    peer.last_seen = self.clock()
                    return peer.peer_id
        raise APIError(401, "unauthorized")

    @staticmethod
    def _object(data, allowed, required):
        if not isinstance(data, dict) or set(data) - set(allowed) or not set(required) <= set(data):
            raise APIError(400, "invalid_fields")

    def join(self, data, address):
        with self.cv:
            self._expire()
            if self.stopped:
                raise APIError(410, "session_stopped")
            self._limit(("join", address), 10)
            self._limit(("join", "global"), 60)
            self._object(data, ("invite", "displayName", "role"), ("invite", "displayName", "role"))
            invite = data["invite"]
            if (not isinstance(invite, str) or len(invite) > 128 or not invite.isascii() or
                    not hmac.compare_digest(invite.encode("utf-8"), self.invite_key.encode("ascii"))):
                raise APIError(403, "invalid_invitation")
            if self.clock() - self.created >= INVITE_TTL:
                raise APIError(403, "invitation_expired")
            name, role = data["displayName"], data["role"]
            if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 40 or
                    any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in name)):
                raise APIError(400, "invalid_display_name")
            if role not in ROLES:
                raise APIError(400, "invalid_role")
            if len(self.peers) >= MAX_PEERS:
                raise APIError(409, "room_full")
            peer_id = secrets.token_urlsafe(18)
            peer = Peer(peer_id, secrets.token_urlsafe(32), name.strip(), role, self.clock())
            self.peers[peer_id] = peer
            self._emit("host", "join_request", peerId=peer_id, displayName=peer.display_name,
                       requestedRole=role)
            return {"sessionId": self.session_id, "peerId": peer_id,
                    "peerCredential": peer.credential, "status": "pending",
                    "pollIntervalMs": 1000, "idleTimeoutSeconds": PEER_IDLE}

    def approve(self, credential, data):
        with self.cv:
            self._auth(credential, True)
            self._limit(("approve", "host"), 60)
            self._object(data, ("peerId", "role"), ("peerId", "role"))
            peer_id, role = data["peerId"], data["role"]
            if not isinstance(peer_id, str) or peer_id not in self.peers:
                raise APIError(404, "peer_not_found")
            if role not in ROLES:
                raise APIError(400, "invalid_role")
            peer = self.peers[peer_id]
            # A request to watch must never become an input grant implicitly.
            if peer.requested_role == "spectator" and role != "spectator":
                raise APIError(403, "spectator_cannot_escalate")
            if role != "spectator" and role != peer.requested_role:
                raise APIError(403, "requested_role_mismatch")
            if role == "player2" and any(p.peer_id != peer_id and p.role == "player2" for p in self.peers.values()):
                raise APIError(409, "player_slot_occupied")
            peer.role = role
            port = role_port(role)
            grant = {"peerId": peer_id, "role": role, "port": port,
                     "mode": {"player": "shared-controller", "player2": "two-player", "spectator": "spectator"}[role],
                     "playerPort": None if port is None else port + 1}
            self._emit(peer_id, "approved", **grant)
            self._emit("host", "peer_approved", **grant)
            return grant

    def signal(self, credential, data):
        with self.cv:
            source = self._auth(credential)
            self._limit(("signal", source), 240)
            self._object(data, ("target", "type", "sdp", "candidate"), ("target", "type"))
            target, kind = data["target"], data["type"]
            if not isinstance(target, str) or target == source:
                raise APIError(400, "invalid_target")
            if source == "host":
                peer = self.peers.get(target)
            elif target == "host":
                peer = self.peers[source]
            else:
                raise APIError(403, "host_star_only")
            if peer is None:
                raise APIError(404, "peer_not_found")
            if peer.role not in ROLES:
                raise APIError(403, "approval_required")
            if kind in ("offer", "answer"):
                if "candidate" in data or not isinstance(data.get("sdp"), str):
                    raise APIError(400, "invalid_sdp")
                try:
                    encoded_sdp = data["sdp"].encode("utf-8")
                except UnicodeError:
                    raise APIError(400, "invalid_sdp")
                if not 1 <= len(encoded_sdp) <= MAX_SDP:
                    raise APIError(413, "sdp_too_large")
                value = {"type": kind, "sdp": data["sdp"]}
            elif kind == "candidate":
                candidate = data.get("candidate")
                if "sdp" in data or not isinstance(candidate, dict):
                    raise APIError(400, "invalid_candidate")
                if set(candidate) - {"candidate", "sdpMid", "sdpMLineIndex", "usernameFragment"}:
                    raise APIError(400, "invalid_candidate")
                if not isinstance(candidate.get("candidate"), str):
                    raise APIError(400, "invalid_candidate")
                for key in ("sdpMid", "usernameFragment"):
                    if key in candidate and candidate[key] is not None and (
                            not isinstance(candidate[key], str) or len(candidate[key]) > 256):
                        raise APIError(400, "invalid_candidate")
                index = candidate.get("sdpMLineIndex")
                if index is not None and (type(index) is not int or not 0 <= index <= 65535):
                    raise APIError(400, "invalid_candidate")
                try:
                    encoded_candidate = json.dumps(candidate, ensure_ascii=False).encode()
                except UnicodeError:
                    raise APIError(400, "invalid_candidate")
                if len(encoded_candidate) > MAX_CANDIDATE:
                    raise APIError(413, "candidate_too_large")
                if peer.candidates >= 256:
                    raise APIError(429, "candidate_limit")
                peer.candidates += 1
                value = {"type": kind, "candidate": candidate}
            else:
                raise APIError(400, "invalid_signal_type")
            self._emit(target, "signal", **{"from": source, "signal": value})
            return {"accepted": True}

    def events(self, credential, after=0, wait=0):
        if type(after) is not int or after < 0 or type(wait) not in (int, float) or not 0 <= wait <= 5:
            raise APIError(400, "invalid_cursor")
        with self.cv:
            who = self._auth(credential)
            self._limit(("events", who), 240)
            deadline = time.monotonic() + wait
            while True:
                self._auth(credential)
                q = self.host_events if who == "host" else self.peers[who].events
                # Acknowledge received events, keeping queues bounded and allowing
                # reconnect with the last cursor (at-least-once until ack).
                while q and q[0]["id"] <= after:
                    q.popleft()
                result = list(q)[:64]
                if result or time.monotonic() >= deadline:
                    return {"events": result, "cursor": result[-1]["id"] if result else after,
                            "sessionId": self.session_id}
                self.cv.wait(timeout=min(deadline - time.monotonic(), 1))

    def leave(self, credential, data):
        with self.cv:
            who = self._auth(credential)
            self._object(data, ("peerId",), ())
            peer_id = data.get("peerId") if who == "host" else who
            if who != "host" and data.get("peerId", who) != who:
                raise APIError(403, "cannot_remove_other_peer")
            if not isinstance(peer_id, str) or peer_id not in self.peers:
                raise APIError(404, "peer_not_found")
            self._remove(peer_id, "revoked" if who == "host" else "left")
            return {"left": True}

    def reset(self, credential, data):
        with self.cv:
            self._auth(credential, True)
            self._object(data, (), ())
            self._limit(("reset", "host"), 60)
            # This is a live room reset, not reviving a permanently stopped room.
            # Keep host identity and invitation; every old peer must join again.
            self.peers.clear()
            self.host_events.clear()
            self.created = self.clock()
            self.invite_expires_at = int(self.wall_clock() + INVITE_TTL)
            # Never rewind sequence: the host may retain its last events cursor.
            self.cv.notify_all()
            return {"reset": True, "inviteExpiresAt": self.invite_expires_at}

    def stop(self, credential, data):
        with self.cv:
            self._auth(credential, True)
            self._object(data, (), ())
            self.stopped = True
            self.peers.clear()
            self.host_events.clear()
            self.invite_key = ""
            self.cv.notify_all()
            return {"stopped": True}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MayoLAN/0.1"
    sys_version = ""

    def log_message(self, *_args):
        pass  # No URLs, headers, SDP, candidate addresses or credentials in logs.

    def setup(self):
        super().setup()
        self.connection.settimeout(8)

    def _reply(self, status, value):
        body = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", WEB_CSP)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command != "HEAD":
            self.wfile.write(body)

    def _public(self):
        if self.command not in ("GET", "HEAD"):
            return False
        if self.path == "/client-info":
            self._reply(200, {"protocolVersion": PROTOCOL_VERSION, "roles": list(ROLES),
                              "ports": {role: role_port(role) for role in ROLES}, "webGuest": True})
            return True
        entry = PUBLIC_ASSETS.get(self.path)
        if entry is None:
            return False
        path, mime = entry
        if path.is_symlink() or not path.is_file():
            raise APIError(404, "not_found")
        with path.open("rb") as source:
            body = source.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise APIError(404, "not_found")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", WEB_CSP)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command != "HEAD":
            self.wfile.write(body)
        return True

    def _credential(self):
        values = self.headers.get_all("Authorization", [])
        if len(values) != 1 or not values[0].startswith("Bearer "):
            raise APIError(401, "unauthorized")
        return values[0][7:]

    def _body(self):
        if self.headers.get("Transfer-Encoding"):
            raise APIError(400, "transfer_encoding_not_supported")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isdigit():
            raise APIError(411, "content_length_required")
        if len(lengths[0]) > 8:
            raise APIError(413, "body_too_large")
        size = int(lengths[0])
        if size > MAX_BODY:
            raise APIError(413, "body_too_large")
        if self.headers.get_content_type() != "application/json":
            raise APIError(415, "json_required")
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise APIError(400, "incomplete_body")
        try:
            return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (UnicodeError, ValueError, RecursionError):
            raise APIError(400, "invalid_json")

    def _dispatch(self):
        room = self.server.room
        url = urlsplit(self.path)
        if url.scheme or url.netloc or url.fragment:
            raise APIError(400, "invalid_path")
        if self.command == "GET" and url.path == "/events":
            query = parse_qs(url.query, keep_blank_values=True)
            if set(query) - {"after", "wait"} or any(len(v) != 1 for v in query.values()):
                raise APIError(400, "invalid_cursor")
            try:
                after = int(query.get("after", ["0"])[0])
                wait = float(query.get("wait", ["0"])[0])
            except ValueError:
                raise APIError(400, "invalid_cursor")
            return room.events(self._credential(), after, wait)
        if self.command != "POST" or url.query:
            raise APIError(404, "not_found")
        if url.path not in ("/join", "/approve", "/signal", "/leave", "/stop", "/reset"):
            raise APIError(404, "not_found")
        data = self._body()
        if url.path == "/join":
            return room.join(data, self.client_address[0])
        credential = self._credential()
        return {"/approve": room.approve, "/signal": room.signal,
                "/leave": room.leave, "/stop": room.stop, "/reset": room.reset}[url.path](credential, data)

    def _handle(self):
        try:
            if self._public():
                return
            self._reply(200, self._dispatch())
        except APIError as exc:
            self._reply(exc.status, {"error": exc.code})
        except (TimeoutError, ConnectionError, OSError):
            self.close_connection = True
        except Exception:
            # A malformed request must not leak an exception or credential data.
            self._reply(500, {"error": "internal_error"})

    do_GET = _handle
    do_HEAD = _handle
    do_POST = _handle


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, room, context):
        self.room = room
        self.slots = threading.BoundedSemaphore(24)
        self.context = context
        super().__init__(address, Handler)

    def handle_error(self, request, client_address):
        pass  # No traceback/request details on socket or malformed-client failures.

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(8)
            # Handshake inside the bounded worker, not the accept loop.
            request = self.context.wrap_socket(request, server_side=True)
            super().process_request_thread(request, client_address)
        except (ssl.SSLError, OSError):
            request.close()
        finally:
            self.slots.release()


def private_bind(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise argparse.ArgumentTypeError("bind must be a literal IPv4 loopback or RFC1918 address")
    ranges = ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    if address.version != 4 or not any(address in ipaddress.ip_network(r) for r in ranges):
        raise argparse.ArgumentTypeError("only explicit IPv4 loopback or RFC1918 binds are allowed")
    return value


def write_configuration(path, data):
    # Refuse overwrites/symlinks, never create a world-readable window.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1", type=private_bind)
    parser.add_argument("--port", default=9443, type=int)
    parser.add_argument("--cert", required=True, type=Path)
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.cert, args.key)
    cert_der = ssl.PEM_cert_to_DER_cert(args.cert.read_text())
    fingerprint = hashlib.sha256(cert_der).hexdigest()
    room = Room()
    with Server((args.bind, args.port), room, context) as server:
        port = server.server_address[1]
        write_configuration(args.config, room.configuration(f"https://{args.bind}:{port}", fingerprint))
        print(f"Private signaling broker ready on https://{args.bind}:{port}; configuration written securely.", flush=True)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
