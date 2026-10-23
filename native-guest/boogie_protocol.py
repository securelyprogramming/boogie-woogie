"""Protocol 1 native guest boundaries. This module has no network or UI imports."""
import ipaddress
import json
import re
from urllib.parse import urlsplit

ROLES = {"player": 0, "player2": 1, "spectator": None}
TOKEN = re.compile(r"[A-Za-z0-9_-]{20,128}\Z")
PEER = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
GAME = re.compile(r"sha256:[a-f0-9]{64}\Z")
DEFAULT_BUTTONS = (8, 0, 0, 8, 2, -1, 3, -1, -1, 10, 11, 4, 5, 6, 7)


def config(value):
    if not isinstance(value, dict) or set(value) - {"baseUrl", "certificateSha256", "invitationSecret", "displayName", "role", "quality"}:
        raise ValueError("Invalid connection fields")
    url = urlsplit(value.get("baseUrl", ""))
    if url.scheme != "https" or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
        raise ValueError("Use the HTTPS LAN broker origin")
    try:
        address = ipaddress.ip_address(url.hostname)
        if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast or address.is_reserved or getattr(address, "scope_id", None): raise ValueError()
        if not 1 <= (url.port or 443) <= 65535: raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("Use a LAN IP address") from None
    if not re.fullmatch(r"[a-fA-F0-9]{64}", value.get("certificateSha256", "")):
        raise ValueError("A trusted broker certificate fingerprint is required")
    if not re.fullmatch(r"[\x21-\x7e]{1,128}", value.get("invitationSecret", "")):
        raise ValueError("Invalid invitation")
    name = value.get("displayName", "")
    if not isinstance(name, str) or not name.strip() or len(name) > 40 or re.search(r"[\x00-\x1f\x7f]", name):
        raise ValueError("Invalid device name")
    if value.get("role") not in ROLES or value.get("quality", "sharp") not in ("smooth", "balanced", "sharp"):
        raise ValueError("Invalid role or video quality")
    return dict(value, baseUrl=value["baseUrl"].rstrip("/"), displayName=name.strip())


class InputCapability:
    """Host-approved role plus DC nonce. A guest never chooses an output port."""
    def __init__(self, role):
        if role not in ROLES: raise ValueError("Invalid role")
        self.role, self.port = role, ROLES[role]
        self.approved = False
        self.nonce = ""
        self.sequence = 0
        self.game_key = ""

    def approve(self, role, port):
        if role not in ROLES or (port is not None and type(port) is not int) or port != ROLES[role] or (role != self.role and role != "spectator"):
            raise ValueError("Invalid host approval")
        self.role, self.port, self.approved = role, port, True

    def grant(self, message):
        if not self.approved or not isinstance(message, dict) or message.get("t") != "grant" or message.get("role") != self.role or (message.get("port") is not None and type(message["port"]) is not int) or message.get("port") != self.port:
            return False
        nonce = message.get("nonce", "")
        if not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32}", nonce): return False
        if nonce != self.nonce: self.sequence = 0
        self.nonce = nonce
        game = message.get("gameKey", "")
        self.game_key = game if isinstance(game, str) and GAME.fullmatch(game) else ""
        return True

    def packet(self, buttons):
        if not self.approved or not self.nonce or self.port is None: return None
        if len(buttons) != 16 or any(type(v) is not int or v not in (0, 1) for v in buttons): raise ValueError("Invalid input snapshot")
        result = {"t": "input", "nonce": self.nonce, "seq": self.sequence, "buttons": list(buttons)}
        self.sequence += 1
        return json.dumps(result, separators=(",", ":"))

    def revoke(self):
        self.nonce, self.approved = "", False


def map_pad(buttons, axes, focused=True, mapping=DEFAULT_BUTTONS):
    result = [0] * 16
    if not focused: return result
    for index, action in enumerate(mapping):
        if 0 <= action < 16 and buttons & (1 << index): result[action] = 1
    if len(axes) >= 2:
        result[6] |= int(axes[0] < -.45); result[7] |= int(axes[0] > .45)
        result[4] |= int(axes[1] < -.45); result[5] |= int(axes[1] > .45)
    if len(axes) >= 6:
        result[12] |= int(axes[4] > .45); result[13] |= int(axes[5] > .45)
    # Opposite directions always become neutral, including stick + D-pad.
    for first, second in ((4, 5), (6, 7)):
        if result[first] and result[second]: result[first] = result[second] = 0
    return result
