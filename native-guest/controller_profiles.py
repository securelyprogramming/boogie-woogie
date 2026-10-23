"""Local gameplay-only SDL→NES profiles. Menu controls and escape chord are fixed.

Game scope is account+RomM ROM id, deliberately independent of downloaded bytes.
"""
import hashlib
import json
import os
from pathlib import Path
import uuid

BUTTONS = ('south', 'east', 'west', 'north', 'back', 'start', 'left_stick', 'right_stick',
           'left_shoulder', 'right_shoulder', 'dpad_up', 'dpad_down', 'dpad_left', 'dpad_right')
ACTIONS = ('a', 'b', 'select', 'start', 'up', 'down', 'left', 'right', 'none')
DEFAULT_PROFILE = {'schema': 1, 'buttons': dict(zip(BUTTONS,
    ('a', 'b', 'b', 'a', 'select', 'start', 'none', 'none', 'none', 'none', 'up', 'down', 'left', 'right')))}
MAX_BYTES = 4096


def validate(profile):
    if (not isinstance(profile, dict) or set(profile) != {'schema', 'buttons'}
            or type(profile['schema']) is not int or profile['schema'] != 1
            or not isinstance(profile['buttons'], dict) or set(profile['buttons']) != set(BUTTONS)
            or any(type(value) is not str or value not in ACTIONS for value in profile['buttons'].values())):
        raise ValueError('Invalid gameplay controller profile. Menu controls and View + Menu exit cannot be remapped.')
    return {'schema': 1, 'buttons': {key: profile['buttons'][key] for key in BUTTONS}}


def game_identity(identity):
    if not isinstance(identity, dict):
        raise ValueError('A RomM account and game are required for a game profile.')
    account, rom = identity.get('account'), identity.get('romId')
    if (not isinstance(account, str) or len(account) != 64 or any(c not in '0123456789abcdef' for c in account)
            or type(rom) is not int or not 0 < rom <= 2**63 - 1):
        raise ValueError('Invalid controller profile account/game identity.')
    return {'account': account, 'romId': rom}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate controller profile field.')
        result[key] = value
    return result


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ProfileStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, identity=None):
        if identity is None:
            return self.root / 'default.json'
        identity = game_identity(identity)
        key = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return self.root / 'games' / (key + '.json')

    def load(self, identity=None):
        candidates = [(self.path(identity), 'game')] if identity is not None else []
        candidates.append((self.path(), 'default'))
        warnings = []
        for path, scope in candidates:
            try:
                with path.open('rb') as stream:
                    content = stream.read(MAX_BYTES + 1)
                if len(content) > MAX_BYTES:
                    raise ValueError('Controller profile exceeds size limit.')
                profile = validate(json.loads(content, object_pairs_hook=unique_object))
                return {'profile': profile, 'scope': scope, 'warning': ' '.join(warnings)}
            except FileNotFoundError:
                continue
            except (OSError, ValueError, TypeError, RecursionError):
                warnings.append('Invalid ' + scope + ' controller profile ignored; reset or save it again.')
        return {'profile': validate(DEFAULT_PROFILE), 'scope': 'factory', 'warning': ' '.join(warnings)}

    def save(self, profile, identity=None):
        profile = validate(profile)
        private_write(self.path(identity), (json.dumps(profile, separators=(',', ':')) + '\n').encode())
        return self.load(identity)

    def reset(self, identity=None):
        self.path(identity).unlink(missing_ok=True)
        return self.load(identity)

    def materialize(self, identity, path):
        result = self.load(identity)
        path = Path(path)
        private_write(path, (json.dumps(result['profile'], separators=(',', ':')) + '\n').encode())
        return {**result, 'path': str(path)}
