# HTTPS signaling broker

Use the one-command [setup](../README.md#start-a-lan-room) to generate a fresh local certificate and private host/guest pairing files. `start-broker.sh` is the advanced launcher for a caller-supplied certificate and new private config filename.

This process admits guests and forwards bounded WebRTC signaling. It does not transport or store game video, audio, ROMs, saves, RomM cookies or controller packets. There is one room per explicitly started process, with a host approval gate and fixed grants: shared Player 1, one dedicated Player 2, or spectator. Native clients validate the trusted pairing certificate fingerprint. Browser clients use their normal certificate validation.

See the [complete protocol](../docs/protocol.md) for endpoint schemas, limits, revocation, reset semantics and input-authority responsibilities. Setup guidance and certificate troubleshooting are in [docs/setup.md](../docs/setup.md).

The HTTPS root serves only the browser guest's explicit static allowlist. No directory listing, CORS relaxation, credential download or ROM route exists. Public capability metadata is at `/client-info`. No network listener starts when importing the module or running its unit tests.

```sh
python3 -m unittest discover -s broker -p 'test*.py'
```
