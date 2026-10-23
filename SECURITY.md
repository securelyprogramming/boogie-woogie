# Security

Boogie Woogie is a development preview for trusted local networks. Pairing provides ephemeral room authorization; it is not an account system or proof of a player's real-world identity.

Host approval and the broker's authenticated grant determine who may send input and to which virtual port. The host must bind the WebRTC data channel to the approved peer, validate bounded input packets, release controls on revocation/disconnect and enforce its input watchdog. Local mapping settings cannot grant another player's port. Spectators never receive input authority.

The broker uses HTTPS, fixed public asset routes, bounded body/event/candidate limits, short-lived invitations and private configuration files. Browser invitations and native certificate pins must arrive through a trusted pairing channel. Secrets are never intended for logs, screenshots, source control, URL queries or browser storage. Never give a guest the host pairing file. RomM cookies remain in the main app's native session.

The pinned centralized organization security workflow and CodeQL run on proposed changes. Passing scans is one check, not a guarantee. Report a suspected vulnerability privately to the repository maintainers through GitHub's private vulnerability reporting when available. Do not open a public issue containing credentials, pairing files, private IP inventories, game files or saved states.

The active-game record is a fresh allowlist of seven game fields plus schema, timestamp and two cache identifiers. `accountKey` is a pseudonymous SHA-256 identity digest (or a fixed local-library identifier); `gameKey` is a ROM content digest. Neither grants access or encrypts data. A focused Android regression checks that arbitrary cookie, password and token fields cannot enter this serialization. The record stays in owner-private internal storage with Android backup disabled. RomM's co-op session handoff is memory-only; returning to the main app clears it. These identifiers should not be interpreted as credential keys by static analysis; the credential-storage query remains enabled.
