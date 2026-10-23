#!/usr/bin/env python3
"""Create an ephemeral LAN room with private pairing files, then serve HTTPS."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile

from broker import ROOT, Room, Server, private_bind, write_configuration


def private_directory(value: Path) -> Path:
    """Reject repository paths and symlinks before touching private state."""
    path = value.expanduser().absolute()
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError("Private data directories must not contain symlinks")
    if path == ROOT or ROOT in path.parents:
        raise ValueError("Pairing data must be outside the source checkout")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("Private data directory must be owned by the current user")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("Private data directory must have mode 0700")
    return path


def prepare_certificate(data_dir: Path, bind: str) -> tuple[Path, ssl.SSLContext, str]:
    private_bind(bind)
    openssl = shutil.which("openssl")
    if openssl is None:
        raise ValueError("OpenSSL is required to generate the local HTTPS certificate")
    root = private_directory(data_dir)
    session_dir = Path(tempfile.mkdtemp(prefix="session-", dir=root))
    cert, key = session_dir / "certificate.pem", session_dir / "private-key.pem"
    # Config-file SAN works with both OpenSSL and macOS LibreSSL.
    # A self-signed trust anchor supports the native receiver's explicit
    # per-session CA file. It is never installed in the system trust store.
    config = session_dir / "certificate.conf"
    config.write_text("[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=ext\n"
                      "[dn]\nCN=Boogie Woogie LAN\n[ext]\n"
                      f"subjectAltName=IP:{bind}\nbasicConstraints=critical,CA:TRUE,pathlen:0\n"
                      "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n"
                      "extendedKeyUsage=serverAuth\n")
    config.chmod(0o600)
    try:
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-sha256",
                        "-nodes", "-days", "2", "-config", str(config),
                        "-keyout", str(key), "-out", str(cert)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=60)
    except (subprocess.SubprocessError, OSError):
        shutil.rmtree(session_dir)
        raise ValueError("Local certificate generation failed") from None
    config.unlink()
    cert.chmod(0o600)
    key.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
    return session_dir, context, fingerprint


def pairing_files(session_dir: Path, room: Room, base_url: str, fingerprint: str):
    full = room.configuration(base_url, fingerprint)
    # Guest pairing never receives the host's authorization credential.
    public_pairing = {key: full[key] for key in
                      ("baseUrl", "certificateSha256", "invitationSecret")}
    write_configuration(session_dir / "session.json", full)
    write_configuration(session_dir / "host.json", {**full, "host": True})
    write_configuration(session_dir / "guest.json", {**public_pairing, "host": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", type=private_bind, default="127.0.0.1",
                        help="Explicit LAN IPv4 or loopback; default only reaches this computer")
    parser.add_argument("--port", type=int, default=9443)
    parser.add_argument("--data-dir", type=Path,
                        default=Path.home() / ".local/share/boogie-woogie",
                        help="Private 0700 directory outside the checkout")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    os.umask(0o077)
    try:
        session_dir, context, fingerprint = prepare_certificate(args.data_dir, args.bind)
        room = Room()
        with Server((args.bind, args.port), room, context) as server:
            pairing_files(session_dir, room, f"https://{args.bind}:{args.port}", fingerprint)
            print(f"Boogie Woogie ready at https://{args.bind}:{args.port}", flush=True)
            print(f"Private pairing files: {session_dir}", flush=True)
            print("Use host.json on the host; share only guest.json with trusted guests. "
                  "Stop with Ctrl+C. Invitations expire after 10 minutes.", flush=True)
            try:
                server.serve_forever(poll_interval=0.5)
            except KeyboardInterrupt:
                pass
    except (ValueError, OSError):
        print("Could not start the room. Check the address, available port, OpenSSL, "
              "and private directory permissions. No pairing secrets were printed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
