"""Local appearance preferences and bounded authenticated cover data."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from boogie_protocol import GAME

MAX_JPEG=49152
MAX_ART_MESSAGE=70000


def jpeg_dimensions(data):
    """Read baseline/progressive 8-bit JPEG SOF before allocating a decoder."""
    if not isinstance(data,bytes) or not 4<=len(data)<=MAX_JPEG or not data.startswith(b'\xff\xd8\xff'):
        raise ValueError('Invalid JPEG')
    offset=2
    for _ in range(1024):
        if offset>=len(data) or data[offset]!=255:raise ValueError('Invalid JPEG marker')
        while offset<len(data) and data[offset]==255:offset+=1
        if offset>=len(data):raise ValueError('Truncated JPEG')
        marker=data[offset];offset+=1
        if marker in (0,0xd8,0xd9,0xda) or 0xd0<=marker<=0xd7:raise ValueError('Missing JPEG frame')
        if marker==1:continue
        if offset+2>len(data):raise ValueError('Truncated JPEG segment')
        size=int.from_bytes(data[offset:offset+2],'big')
        if size<2 or offset+size>len(data):raise ValueError('Invalid JPEG segment')
        if marker in (0xc0,0xc2):
            if size<8 or data[offset+2]!=8:raise ValueError('Invalid JPEG frame')
            height=int.from_bytes(data[offset+3:offset+5],'big');width=int.from_bytes(data[offset+5:offset+7],'big')
            if not 0<width<=320 or not 0<height<=320:raise ValueError('Oversized JPEG frame')
            return width,height
        if marker in (0xc1,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
            raise ValueError('Unsupported JPEG frame')
        offset+=size
    raise ValueError('Too many JPEG segments')


class AppearanceStore:
    def __init__(self,brand='rommayo',root=None):
        if brand not in ('rommayo','emulatormayo'):raise ValueError('Invalid brand')
        self.brand=brand;self.path=Path(root or Path.home()/'.local/share/boogie-woogie/appearance')/(brand+'.json')
        self.mode='game';self.dim=82;self.reload()

    def reload(self):
        try:
            with self.path.open('rb') as stream:raw=stream.read(4097)
            if len(raw)>4096:return
            value=json.loads(raw)
            if (isinstance(value,dict) and set(value)=={'schema','mode','dim'} and type(value['schema']) is int and value['schema']==1
                    and value['mode'] in ('off','brand','game') and type(value['dim']) is int and 40<=value['dim']<=95):
                self.mode,self.dim=value['mode'],value['dim']
        except (OSError,ValueError,TypeError):pass

    def save(self,mode=None,dim=None):
        mode=self.mode if mode is None else mode;dim=self.dim if dim is None else dim
        if mode not in ('off','brand','game') or type(dim) is not int or not 40<=dim<=95:raise ValueError('Invalid appearance')
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,temporary=tempfile.mkstemp(prefix='.appearance-',dir=self.path.parent)
        try:
            with os.fdopen(fd,'w') as stream:json.dump({'schema':1,'mode':mode,'dim':dim},stream,separators=(',',':'))
            os.replace(temporary,self.path)
            self.mode,self.dim=mode,dim
        finally:Path(temporary).unlink(missing_ok=True)


class TrustedArtwork:
    def __init__(self):
        self.game='';self.nonce='';self.sha='';self.jpeg=b'';self.width=self.height=0

    def clear(self,game='',nonce=''):
        self.game=game;self.nonce=nonce;self.sha='';self.jpeg=b'';self.width=self.height=0

    def accept(self,message,capability):
        if (not capability.approved or not capability.nonce or not capability.game_key
                or not isinstance(message,dict) or set(message)!={'t','nonce','gameKey','mime','width','height','sha256','data'}
                or message.get('t')!='game-art' or message.get('nonce')!=capability.nonce
                or message.get('gameKey')!=capability.game_key or not GAME.fullmatch(capability.game_key)
                or message.get('mime')!='image/jpeg' or type(message.get('width')) is not int or type(message.get('height')) is not int
                or not 0<message['width']<=320 or not 0<message['height']<=320
                or not isinstance(message.get('sha256'),str) or not re.fullmatch(r'[a-f0-9]{64}',message['sha256'])
                or not isinstance(message.get('data'),str) or not 0<len(message['data'])<=65536):return False
        if self.game!=capability.game_key or self.nonce!=capability.nonce:self.clear(capability.game_key,capability.nonce)
        if self.sha==message['sha256']:return False
        try:
            data=base64.b64decode(message['data'],validate=True)
            if base64.b64encode(data).decode()!=message['data'] or len(data)>MAX_JPEG:return False
            if hashlib.sha256(data).hexdigest()!=message['sha256']:return False
            width,height=jpeg_dimensions(data)
            if (width,height)!=(message['width'],message['height']):return False
        except (ValueError,TypeError):return False
        # No await occurs above. The native decoder performs the same binding
        # check before committing pixels and has an independent allocation cap.
        self.sha,self.jpeg,self.width,self.height=message['sha256'],data,width,height
        return True
