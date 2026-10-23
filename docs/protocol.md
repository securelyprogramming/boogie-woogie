# LAN admission and signaling protocol

Protocol version 1 uses a single explicitly started HTTPS room. Browser and native clients share this contract; the host alone grants controller authority.

## HTTP contract

All bodies/responses are JSON. Send `Content-Type: application/json` and a single `Content-Length`. No chunked upload, CORS, browser cookies, query credentials or preflight support. Except `/join`, use one `Authorization: Bearer <credential>` header. No request, response, header or signaling logging. Responses use `Cache-Control: no-store`.

All successful responses are HTTP 200. Errors are `{"error":"stable_code"}` with HTTP 400/401/403/404/409/410/411/413/415/429; an unexpected server error is a redacted 500.

### Join and approval

`POST /join` (unauthenticated invitation exchange):

```json
{"invite":"<invitationSecret>","displayName":"Guest Deck","role":"player"}
```

Role is `player` (shared player 1), `player2` (dedicated player 2), or `spectator`; name is 1–40 characters, no control characters. Response:

```json
{"sessionId":"<room>","peerId":"<random-id>","peerCredential":"<guest-private-key>","status":"pending","pollIntervalMs":1000,"idleTimeoutSeconds":30}
```

Host sees a `join_request` event with `peerId`, `displayName`, `requestedRole`. Pending guests can poll/leave but cannot signal. Do not begin WebRTC negotiation before approval.

Host: `POST /approve` with `{"peerId":"<id>","role":"player"}`, `player2` or `spectator`. Approve the requested role or downgrade to spectator; do not silently switch shared/dedicated slots. Response and peer `approved` event carry authoritative zero-based `port`: 0 for `player`, 1 for `player2`, null for spectator. Legacy `playerPort` remains one-based 1/2/null. `mode` is `shared-controller`, `two-player`, or `spectator`. A second approved `player2` receives 409 `player_slot_occupied`; leaving, revocation, idle expiry or downgrade frees the slot. Clients never choose a port in join/input messages. Host receives `peer_approved` with the same grant. A spectator request cannot be escalated to player; that guest must rejoin explicitly requesting player. Host may approve an original player request as a spectator. Existing approval can be downgraded; host must immediately enforce the new grant.

### Events and signaling

`GET /events?after=0&wait=5` with host or peer Bearer secret. `after` is the last delivered integer cursor; `wait` is 0–5 seconds, default 0. Response:

```json
{"events":[{"id":1,"type":"join_request","peerId":"<id>","displayName":"Guest Deck","requestedRole":"player"}],"cursor":1,"sessionId":"<room>"}
```

Every event has global increasing `id` and string `type`. Save the returned cursor and send it next time. Events are retained until acknowledged; duplicate delivery is possible, so processing must be idempotent. Poll immediately after each long poll and at least once every 30 seconds. Only one poll loop per credential. Events are private per credential. An empty response retains the supplied cursor. Each reply is limited to 64 events. Queue overflow emits `resync_required`: close the affected peer connection and rejoin/reapprove; do not continue from partially lost signaling.

The fixed host ID is `host`. Approved guests may signal only the host, and the host only an approved guest. No guest-to-guest signaling, cross-room routing, arbitrary messages or credential forwarding.

`POST /signal`:

```json
{"target":"<peerId or host>","type":"offer","sdp":"v=0..."}
```

`type` is `offer` or `answer`, with only `sdp` (1–65536 UTF-8 bytes), or `candidate` with only the standard candidate object:

```json
{"target":"host","type":"candidate","candidate":{"candidate":"candidate:...","sdpMid":"0","sdpMLineIndex":0}}
```

Optional candidate field `usernameFragment` is supported. `sdpMid` and `usernameFragment` may be string or null; `sdpMLineIndex` may be integer or null. An empty candidate string supports end-of-candidates. Entire candidate JSON is at most 2048 UTF-8 bytes. Success: `{"accepted":true}`. Recipient sees:

```json
{"id":3,"type":"signal","from":"host","signal":{"type":"offer","sdp":"v=0..."}}
```

### Leave, revoke, stop

Peer: `POST /leave` with `{}` invalidates its credential immediately. Host: `POST /leave` with `{"peerId":"<id>"}` revokes that guest. Host receives `peer_left` with `peerId`, prior `role` and `reason` (`left`, `revoked`, `idle_timeout`). The host must close that peer's connection and release all held input. Revoked guests subsequently receive 401 and must close media/input connections. Host: `POST /stop` with `{}` clears credentials and queues, returns `{"stopped":true}`. All subsequent API calls return 410 `session_stopped`. The host must stop media/data channels itself before/while stopping the broker.

## Bounds and intentional simplifications

- One room per process; created only at startup. No remotely callable room-creation endpoint, creator secret or persistent database.
- Invite expires after 10 minutes. Existing guests remain while polling. Max 8 peers, including pending/spectators. Unauthenticated join attempts: 10/min per IP, 60/min total.
- Guest idle expiry: 30 seconds after last authenticated request; checked on API activity. There is no background timer. The host must treat missing/failed poll heartbeat as disconnected and release input even if all API traffic stops.
- Signaling: 240 requests/min per sender; total 256 ICE candidates across both directions per peer lifetime. Rejoin for repeated ICE restarts. Events: 240 requests/min per credential. Approvals: 60/min.
- Body max 72 KiB; queues max 256 events per recipient, bounded long poll; max 24 simultaneous TLS/request workers; 8-second socket/handshake timeout. Idle worker capacity exhaustion closes additional sockets.
- No host idle expiry: the local parent process controls room lifetime. There is no host migration, restart persistence or invitation rotation.
- LAN transport only. ICE SDP/candidates may contain private IPs in memory until delivered; no SDP rewriting, public STUN/TURN configuration, relay, analytics or storage.
- Admission alone is not input security. Parent's host input authority must bind the data channel to the approved WebRTC peer, check role/port, bound packet size/rate/sequence and release buttons on disconnect. Video/audio are peer-to-peer and their operation is outside these tests.

## Tests

```sh
python3 -m unittest discover -s . -v
```

Unit tests exercise admission/approval, spectator permission, host-star forwarding, bounds/rates, events, leave/revocation, expiry, stop, private configuration permissions and bind policy. They do not bind a network service, generate certificates, provision devices, test native TLS pinning or verify WebRTC media.


### Live room reset

Host-only `POST /reset` with `{}` revokes every pending/approved peer, clears queued events, and refreshes the existing invitation for ten minutes. Response is `{"reset":true,"inviteExpiresAt":...}`. Host credential, invitation secret and room ID stay unchanged; event IDs remain monotonic so a retained host cursor still works. A fresh player-two approval can claim the released slot. Peers' old credentials now receive 401, so they must join and obtain host approval again. The host must stop local media/input and invalidate queued UI/poll callbacks before resetting; signaling cannot close an already established WebRTC channel itself. `/reset` cannot revive a room permanently ended by `/stop`. Use live reset for restarting multiplayer or switching games while retaining trusted pairing.
