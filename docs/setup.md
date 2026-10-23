# Setup and troubleshooting

## Host and guests

Keep the broker computer and player devices on the same LAN. Disable guest-network/client isolation for the participating devices if your network intentionally blocks device-to-device traffic. The computer must be reachable at the exact IPv4 chosen with `--bind`; a phone cannot use the computer's `127.0.0.1` address.

Run `./setup.sh --bind YOUR_LAN_IP` from the project. The printed private directory holds:

| File | Recipient |
| --- | --- |
| `host.json` | Host only; includes host authority |
| `guest.json` | Trusted guests; invitation, HTTPS origin and certificate pin |
| `session.json` | Operator's complete room record; keep private |
| `certificate.pem`, `private-key.pem` | Broker computer only |

Files are created with mode 0600 inside a fresh mode-0700 directory. Do not upload them to the website, attach them to bug reports, or copy the host credential into a browser. RomM authentication is kept within the main app's native session and is never supplied through these imported pairing files.

On Android use **Import pairing file**, then choose a local `.nes` file on a host through **Import NES**. Approve a guest's requested role after starting multiplayer. For a browser guest, open the broker's HTTPS URL, use the invitation from the privately transferred guest pairing file, enter a display name and request a role. Browser controls are documented [here](../web/README.md).

The native Steam Deck guest uses the same protocol and pairing fields. The standalone Android packaging does not install or update the private Deck prototype automatically. A public native installer must be tested independently before being advertised.

## Common problems

| Symptom | Check |
| --- | --- |
| Phone cannot reach the page | Correct LAN IP, port and device network; explicit bind; firewall permits that port |
| Native TLS error | Exact certificate SHA-256 from current trusted pairing; correct IP SAN; certificate not expired |
| Browser privacy warning | Certificate is locally self-signed; review/accept it explicitly or use a trusted certificate via the advanced broker launcher |
| Join rejected | Invitation expired or belongs to another process; request current guest pairing and host approval |
| Player 2 unavailable | One dedicated Player 2 slot is already occupied; host can revoke it or reset multiplayer |
| No response to input | Approved player role, compatible game, correct controller mapping; spectators cannot send input |
| Picture stalls | Adjust Video quality; check Wi-Fi signal/congestion; an FPS counter alone does not verify correct decoded picture/audio |
| Another instance is already running | Choose `--port 9444`; do not silently restart a live test session |

Stop with Ctrl+C. A stopped room cannot resume using its old credentials. Remove an old private session directory only after its room is stopped and it is no longer needed; setup never deletes another session's files.

Advanced operators can supply an existing matching certificate using `broker/start-broker.sh --bind IP --port PORT --cert /private/cert.pem --key /private/key.pem --config /private/new-session.json`. That launcher creates one private config, not the convenient host/guest split supplied by `setup.sh`.
