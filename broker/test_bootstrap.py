"""Local setup tests use generated certificates, never real pairing/device data."""
import contextlib
import io
import json
from pathlib import Path
import ssl
import stat
import subprocess
import tempfile
import unittest

import bootstrap
from broker import Room


class BootstrapTests(unittest.TestCase):
    def test_pairing_files_are_private_and_guest_has_no_host_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                folder, context, pin = bootstrap.prepare_certificate(root, "127.0.0.1")
                room = Room()
                bootstrap.pairing_files(folder, room, "https://127.0.0.1:9443", pin)
            self.assertEqual(capture.getvalue(), "")
            self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
            self.assertEqual(len(pin), 64)
            host = json.loads((folder / "host.json").read_text())
            guest = json.loads((folder / "guest.json").read_text())
            self.assertEqual(host["hostCredential"], room.host_key)
            self.assertIs(host["host"], True)
            self.assertEqual(set(guest), {"baseUrl", "certificateSha256", "invitationSecret", "host"})
            self.assertIs(guest["host"], False)
            self.assertNotIn(room.host_key, json.dumps(guest))
            for file in folder.iterdir():
                self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
            # Read certificate metadata only, never key/pairing output.
            decoded = ssl._ssl._test_decode_cert(str(folder / "certificate.pem"))
            self.assertIn(("IP Address", "127.0.0.1"), decoded["subjectAltName"])
            verify = subprocess.run(["openssl", "verify", "-CAfile",
                                     str(folder / "certificate.pem"),
                                     str(folder / "certificate.pem")],
                                    capture_output=True, timeout=10)
            self.assertEqual(verify.returncode, 0,
                             "Generated certificate must work as the native receiver's explicit trust anchor")

    def test_refuses_checkout_symlink_and_readable_data_directories(self):
        with self.assertRaises(ValueError):
            bootstrap.private_directory(bootstrap.ROOT / "private-pairing")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            target = root / "target"
            target.mkdir(mode=0o700)
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                bootstrap.private_directory(link / "session")
            target.chmod(0o755)
            with self.assertRaises(ValueError):
                bootstrap.private_directory(target)


if __name__ == "__main__":
    unittest.main()
