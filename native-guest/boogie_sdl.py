"""Native SDL3 window, decoded media sink and physical controller sampling.

All SDL calls run on the main asyncio thread. Uses a system or explicitly selected SDL3 shared library. No virtual gamepad/system key injection.
"""
import ctypes as C
import ctypes.util
import os
import hashlib
from pathlib import Path
import sys
import time

from boogie_ui import NativeUI, mapped, sources
from boogie_appearance import TrustedArtwork


def find_sdl_library(explicit=None):
    """Locate user-provided or system SDL3 without a bundled emulator core."""
    requested = explicit or os.environ.get('BOOGIE_SDL3_LIBRARY')
    if requested:
        path=Path(requested).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise ValueError('SDL3 library must be an existing absolute path')
        return str(path)
    root=Path(__file__).resolve().parent
    candidates=[root/'.sdl3/lib/libSDL3.so.0', root/'.sdl3/lib/libSDL3.dylib',
                Path('/opt/homebrew/lib/libSDL3.dylib'),Path('/usr/local/lib/libSDL3.dylib')]
    for path in candidates:
        if path.is_file():return str(path)
    found=ctypes.util.find_library('SDL3')
    if found:return found
    raise RuntimeError('Install SDL3 or use --sdl-library with its absolute shared-library path')


class AudioSpec(C.Structure):
    _fields_ = [("format", C.c_uint32), ("channels", C.c_int), ("freq", C.c_int)]


class Rect(C.Structure):
    _fields_=[('x',C.c_float),('y',C.c_float),('w',C.c_float),('h',C.c_float)]


class KeyboardEvent(C.Structure):
    _fields_=[('type',C.c_uint32),('reserved',C.c_uint32),('timestamp',C.c_uint64),
              ('windowID',C.c_uint32),('which',C.c_uint32),('scancode',C.c_int),
              ('key',C.c_uint32),('mod',C.c_uint16),('raw',C.c_uint16),('down',C.c_bool),('repeat',C.c_bool)]


class MouseButtonEvent(C.Structure):
    _fields_=[('type',C.c_uint32),('reserved',C.c_uint32),('timestamp',C.c_uint64),
              ('windowID',C.c_uint32),('which',C.c_uint32),('button',C.c_uint8),('down',C.c_bool),
              ('clicks',C.c_uint8),('padding',C.c_uint8),('x',C.c_float),('y',C.c_float)]


class Sink:
    def __init__(self, deck=False, library=None, mapping=None, brand='rommayo', volume=100, muted=False, show_fps=False):
        if type(volume) is not int or not 0<=volume<=100 or type(muted) is not bool or type(show_fps) is not bool: raise ValueError('Invalid local audio/display options')
        self.volume=volume;self.muted=muted;self.show_fps=show_fps
        self.fps_at=time.monotonic();self.fps_frames=0;self.displayed_fps=0.0
        self.lib = C.CDLL(find_sdl_library(library))
        version = self.lib.SDL_GetVersion; version.restype = C.c_int; version.argtypes = []
        if version() < 3002000: raise RuntimeError("SDL 3.2.0 or newer is required")
        def fn(name, result, *args):
            value = getattr(self.lib, "SDL_" + name); value.restype = result; value.argtypes = list(args); return value
        P, I, U, B = C.c_void_p, C.c_int, C.c_uint32, C.c_bool
        self.init = fn("Init", B, U)
        self.error = fn("GetError", C.c_char_p)
        self.quit = fn("Quit", None)
        self.create_window = fn("CreateWindow", P, C.c_char_p, I, I, C.c_uint64)
        self.destroy_window = fn("DestroyWindow", None, P)
        self.create_renderer = fn("CreateRenderer", P, P, C.c_char_p)
        self.destroy_renderer = fn("DestroyRenderer", None, P)
        self.set_title = fn("SetWindowTitle", B, P, C.c_char_p)
        self.window_flags = fn("GetWindowFlags", C.c_uint64, P)
        self.poll_event = fn("PollEvent", B, P)
        self.key_state = fn("GetKeyboardState", C.POINTER(C.c_bool), C.POINTER(I))
        self.get_pads = fn("GetGamepads", C.POINTER(U), C.POINTER(I))
        self.free = fn("free", None, P)
        self.open_pad = fn("OpenGamepad", P, U)
        self.close_pad = fn("CloseGamepad", None, P)
        self.pad_connected = fn("GamepadConnected", B, P)
        self.pad_button = fn("GetGamepadButton", B, P, I)
        self.pad_axis = fn("GetGamepadAxis", C.c_short, P, I)
        self.pad_name = fn("GetGamepadName", C.c_char_p, P)
        self.pad_vendor = fn('GetGamepadVendor',C.c_uint16,P)
        self.pad_product = fn('GetGamepadProduct',C.c_uint16,P)
        self.pad_serial = fn('GetGamepadSerial',C.c_char_p,P)
        self.update_pads = fn("UpdateGamepads", None)
        self.create_texture = fn("CreateTexture", P, P, U, I, I, I)
        self.destroy_texture = fn("DestroyTexture", None, P)
        self.update_texture = fn("UpdateTexture", B, P, P, P, I)
        self.logical_size = fn("SetRenderLogicalPresentation", B, P, I, I, I)
        self.clear = fn("RenderClear", B, P)
        self.render = fn("RenderTexture", B, P, P, P, P)
        self.present = fn("RenderPresent", B, P)
        self.draw_color=fn('SetRenderDrawColor',B,P,C.c_uint8,C.c_uint8,C.c_uint8,C.c_uint8)
        self.draw_blend=fn('SetRenderDrawBlendMode',B,P,I)
        self.fill_rect=fn('RenderFillRect',B,P,C.POINTER(Rect))
        self.draw_rect=fn('RenderRect',B,P,C.POINTER(Rect))
        self.draw_text=fn('RenderDebugText',B,P,C.c_float,C.c_float,C.c_char_p)
        self.render_scale=fn('SetRenderScale',B,P,C.c_float,C.c_float)
        self.window_size=fn('GetWindowSize',B,P,C.POINTER(I),C.POINTER(I))
        self.open_audio = fn("OpenAudioDeviceStream", P, U, C.POINTER(AudioSpec), P, P)
        self.audio_gain = fn("SetAudioStreamGain", B, P, C.c_float)
        self.resume_audio = fn("ResumeAudioStreamDevice", B, P)
        self.audio_data = fn("PutAudioStreamData", B, P, P, I)
        self.audio_queued = fn("GetAudioStreamQueued", I, P)
        self.audio_clear = fn("ClearAudioStream", B, P)
        self.audio_destroy = fn("DestroyAudioStream", None, P)
        self.window = self.renderer = self.texture = self.audio = None
        self.pads = {}; self.size = None; self.event = (C.c_uint64 * 16)()
        self.quit_requested = False; self.combo_since = None; self.frames = 0
        self.quit_reason = ""
        self.focus_neutral = True
        self.audio_frames = 0; self.audio_dropped = 0
        self.mapping = mapping
        self.ui=NativeUI(mapping=mapping,brand=brand);self.ui_chord=False;self.ui_dirty=-1
        self.brand=brand;self.brand_texture=None;self.brand_size=None;self.brand_attempted=False
        self.art=TrustedArtwork();self.art_texture=None;self.art_size=None
        self.hit_boxes=[];self.keyboard_previous=set();self.keyboard_edges=set()
        self.local_neutral=True
        if not self.init(0x20 | 0x10 | 0x2000): raise RuntimeError("SDL initialization failed")
        self.window = self.create_window(b"Boogie Woogie - waiting for host approval", 1280, 800, 1 if deck else 0x20)
        if self.window: self.renderer = self.create_renderer(self.window, None)
        if not self.renderer:
            self.close(); raise RuntimeError("SDL window/renderer unavailable")
        self.audio = self.open_audio(0xFFFFFFFF, C.byref(AudioSpec(0x8010, 2, 48000)), None, None)
        if self.audio:
            if not self.audio_gain(self.audio,0.0 if muted else volume/100):
                self.close();raise RuntimeError("SDL audio volume could not be applied")
            self.resume_audio(self.audio)

    def title(self, text):
        self.set_title(self.window, ("Boogie Woogie | " + text + " | Hold View + Menu to leave").encode("utf-8")[:240])

    def session(self,role,game,title='',nonce=''):
        if self.art.game!=game or self.art.nonce!=nonce:
            if self.art_texture:self.destroy_texture(self.art_texture);self.art_texture=None
            self.art_size=None;self.art.clear(game,nonce)
        self.ui.set_session(role,game,title)

    def image_texture(self,image):
        from PySide6.QtGui import QImage
        rgba=image.convertToFormat(QImage.Format_RGBA8888)
        texture=self.create_texture(self.renderer,0x16762004,1,rgba.width(),rgba.height())
        if not texture:raise RuntimeError('Backdrop texture unavailable')
        pixels=bytes(rgba.constBits())
        if not self.update_texture(texture,None,pixels,rgba.bytesPerLine()):
            self.destroy_texture(texture);raise RuntimeError('Backdrop upload failed')
        return texture,(rgba.width(),rgba.height())

    def game_art(self,message,capability):
        if self.art.sha and message.get('sha256')==self.art.sha:return False
        candidate=TrustedArtwork()
        if not candidate.accept(message,capability):return False
        binding=(capability.nonce,capability.game_key)
        from PySide6.QtCore import QBuffer,QByteArray,QIODevice
        from PySide6.QtGui import QImageReader
        QImageReader.setAllocationLimit(16)
        buffer=QBuffer();buffer.setData(QByteArray(candidate.jpeg));buffer.open(QIODevice.ReadOnly)
        reader=QImageReader(buffer,b'jpeg');reader.setAutoTransform(False)
        size=reader.size()
        if (size.width(),size.height())!=(candidate.width,candidate.height):return False
        image=reader.read()
        if image.isNull() or (image.width(),image.height())!=(candidate.width,candidate.height):return False
        if not capability.approved or (capability.nonce,capability.game_key)!=binding:return False
        texture,dimensions=self.image_texture(image)
        if not capability.approved or (capability.nonce,capability.game_key)!=binding:
            self.destroy_texture(texture);return False
        if self.art_texture:self.destroy_texture(self.art_texture)
        self.art,self.art_texture,self.art_size=candidate,texture,dimensions
        self.ui.change();return True

    def mapping_request(self,message,capability):
        opened=self.ui.request_mapping(message,capability)
        if opened:self.local_neutral=True
        return opened

    def click(self,x,y):
        for left,top,width,height,index in self.hit_boxes:
            if left<=x<left+width and top<=y<top+height:
                if index==-1:self.ui.toggle()
                else:self.ui.selection=index;self.ui.activate(index)
                self.local_neutral=True;return

    def sample(self):
        key_edges=[];clicks=[]
        while self.poll_event(C.byref(self.event)):
            event_type = C.cast(C.byref(self.event), C.POINTER(C.c_uint32))[0]
            if event_type in (0x100, 0x210):
                self.quit_requested = True; self.quit_reason = "quit" if event_type == 0x100 else "window-close"
            elif event_type==0x300:
                key=C.cast(C.byref(self.event),C.POINTER(KeyboardEvent)).contents
                if not key.repeat:key_edges.append(key.scancode)
            elif event_type==0x401:
                pointer=C.cast(C.byref(self.event),C.POINTER(MouseButtonEvent)).contents
                if pointer.button==1:clicks.append((pointer.x,pointer.y))
        self.update_pads()
        for identity, pad in list(self.pads.items()):
            if not self.pad_connected(pad): self.close_pad(pad); del self.pads[identity]
        count = C.c_int(); identities = self.get_pads(C.byref(count))
        try:
            for index in range(min(count.value, 16)):
                identity = identities[index]
                if identity not in self.pads and len(self.pads) < 4:
                    pad = self.open_pad(identity)
                    if pad: self.pads[identity] = pad
        finally:
            self.free(identities)
        focused = bool(self.window_flags(self.window) & 0x200)
        output = [0] * 16; combo = False;options_chord=False;devices=[];snapshots=[]
        for pad in self.pads.values():
            bits = sum((1 << index) for index in range(15) if self.pad_button(pad, index))
            axes = [self.pad_axis(pad, i) / 32768 for i in range(6)]
            combo |= bool(bits & (1 << 4) and bits & (1 << 6))
            options_chord |= bool(bits & (1<<7) and bits & (1<<8))
            name=(self.pad_name(pad) or b'Controller').decode(errors='replace')[:48]
            identity=f'{self.pad_vendor(pad)}|{self.pad_product(pad)}|{name}|'.encode()+(self.pad_serial(pad) or b'')
            key=hashlib.sha256(identity).hexdigest()
            devices.append({'key':key,'label':''.join(c for c in name if 32<=ord(c)<127)[:40]})
            snapshots.append((key,sources(bits,axes)))
        self.ui.set_devices(devices)
        if focused and options_chord and not self.ui_chord:
            self.ui.toggle();self.local_neutral=True
        self.ui_chord=options_chord
        for key,active in snapshots:
            if focused:
                self.ui.capture_sources(key,active)
                if key==self.ui.selected_device:self.ui.navigation(active)
            value=mapped(active,self.ui.bindings(key)) if focused else [0]*16
            output=[a|b for a,b in zip(output,value)]
        keys = self.key_state(None)
        if focused:
            # Event edges retain short remote taps whose down+up both arrive
            # between samples. Repeats are ignored for dialog activation.
            for key in key_edges:
                if key in (41,58):self.ui.toggle();self.local_neutral=True
                elif self.ui.page:
                    if key in (82,81):
                        self.ui.selection=(self.ui.selection+(-1 if key==82 else 1))%max(1,len(self.ui.rows()));self.ui.change()
                    elif key in (40,44):self.ui.activate(self.ui.selection)
                    elif key==42 and self.ui.page=='options':self.ui.page='';self.ui.change()
            width=C.c_int();height=C.c_int();self.window_size(self.window,C.byref(width),C.byref(height))
            for x,y in clicks:self.click(x*1280/max(1,width.value),y*800/max(1,height.value))
        # Standard NES keyboard fallback, using SDL scancodes (layout independent).
        if focused:
            for key, action in ((82,4),(81,5),(80,6),(79,7),(29,8),(27,0),(40,3),(229,2)):
                if keys[key]: output[action] = 1
        for a, b in ((4,5),(6,7)):
            if output[a] and output[b]: output[a] = output[b] = 0
        if not focused:
            self.focus_neutral = True
        if self.ui.blocked or options_chord:
            self.local_neutral=True;output=[0]*16
        elif self.local_neutral:
            if focused and not any(output):self.local_neutral=False
            output=[0]*16
        if self.focus_neutral:
            if focused and not any(output): self.focus_neutral = False
            output = [0] * 16
        if focused and combo:
            if self.combo_since is None: self.combo_since = time.monotonic()
            if time.monotonic() - self.combo_since > 1: self.quit_requested = True; self.quit_reason = "exit-chord"
            return [0] * 16
        self.combo_since = None
        if self.ui.leave:self.quit_requested=True;self.quit_reason='leave-menu'
        if self.ui_dirty!=self.ui.generation:self.repaint();self.ui_dirty=self.ui.generation
        return output

    def video(self, frame):
        if frame.width < 1 or frame.height < 1 or frame.width > 1920 or frame.height > 1080: return
        rgba = frame.reformat(format="rgba")
        if self.size != (rgba.width, rgba.height):
            if self.texture: self.destroy_texture(self.texture)
            self.texture = self.create_texture(self.renderer, 0x16762004, 1, rgba.width, rgba.height)
            if not self.texture: raise RuntimeError("SDL video texture unavailable")
            self.size = (rgba.width, rgba.height)
        pixels = bytes(rgba.planes[0])
        if not self.update_texture(self.texture, None, pixels, rgba.planes[0].line_size): raise RuntimeError("SDL texture upload failed")
        self.repaint()
        self.frames += 1

    def box(self,x,y,w,h,color):
        self.draw_color(self.renderer,*color);self.fill_rect(self.renderer,C.byref(Rect(x,y,w,h)))

    def text(self,x,y,text,scale=2,color=(225,244,234,255)):
        self.draw_color(self.renderer,*color);self.render_scale(self.renderer,scale,scale)
        self.draw_text(self.renderer,x/scale,y/scale,str(text).encode('ascii','replace'))
        self.render_scale(self.renderer,1,1)

    def repaint(self):
        self.render_scale(self.renderer,1,1);self.logical_size(self.renderer,1280,800,1)
        self.draw_color(self.renderer,0,0,0,255);self.clear(self.renderer)
        self.draw_blend(self.renderer,1)
        if self.ui.appearance.mode!='off':self.backdrop()
        if self.texture:
            self.render(self.renderer,self.texture,None,C.byref(self.game_destination()))
        self.hit_boxes=[(18,16,210,48,-1)]
        if not self.ui.page:
            self.box(280,20,560,38,(0,0,0,150));self.text(299,31,'L3 + R3 / Esc: options',2)
        else:
            self.box(0,80,1280,720,(0,0,0,75));self.box(96,89,1088,675,(13,28,25,255))
            self.text(126,107,'YOUR CONTROLS' if self.ui.editing else 'LEAVE SESSION?' if self.ui.page=='confirm-leave' else 'APPEARANCE' if self.ui.page=='appearance' else 'SESSION OPTIONS',3)
            self.text(126,141,(self.ui.draft_title if self.ui.editing else self.ui.title)[:58],2,(160,191,174,255))
            rows=self.ui.rows()
            top=179 if self.ui.editing and self.ui.capture is None else 230
            row_height=35 if self.ui.editing and self.ui.capture is None else 72
            for index,label in enumerate(rows):
                y=top+index*row_height
                selected=index==self.ui.selection
                self.box(124,y,1032,row_height-3,(34,83,61,255) if selected else (22,44,35,255))
                if selected:self.box(124,y,4,row_height-3,(121,255,182,255))
                self.text(142,y+8,label[:62],2)
                self.hit_boxes.append((124,y,1032,row_height-3,index))
            self.text(126,717,self.ui.message[:64],1.8,(158,228,186,255))
            self.text(126,745,'A: select  B: back  L3+R3 / Esc: options',1.8)
            self.text(126,772,'Only your input is released. Other players keep playing.',1.6,(157,178,166,255))
        # Draw the persistent affordance/role last, above every menu/background.
        self.box(18,16,210,48,(12,38,30,255));self.box(18,16,4,48,(92,230,165,255))
        for y in (29,38,47):self.box(35,y,21,3,(132,247,190,255))
        self.text(72,29,'OPTIONS',2.5)
        self.text(900,30,self.ui.heading,2.5,(130,244,187,255))
        self.text(900,57,str(len(self.pads))+' controller(s) connected',1.5,(163,192,175,255))
        if self.show_fps:
            now=time.monotonic()
            if now-self.fps_at>=.5:
                self.displayed_fps=(self.frames-self.fps_frames)/(now-self.fps_at);self.fps_at=now;self.fps_frames=self.frames
            self.box(18,755,205,30,(0,0,0,185));self.text(28,762,f"{self.displayed_fps:.1f} video FPS",2)
        if not self.present(self.renderer):raise RuntimeError('SDL frame presentation failed')

    def game_destination(self):
        width=C.c_int();height=C.c_int();self.window_size(self.window,C.byref(width),C.byref(height))
        ww,wh=max(1,width.value),max(1,height.value)
        scale=min(ww/self.size[0],wh/self.size[1])
        w,h=self.size[0]*scale,self.size[1]*scale
        return Rect((ww-w)*640/ww,(wh-h)*400/wh,w*1280/ww,h*800/wh)

    def backdrop(self):
        self.box(0,0,1280,800,(8,21,37,255) if self.brand=='rommayo' else (7,27,20,255))
        if not self.brand_attempted:
            self.brand_attempted=True
            try:
                from PySide6.QtCore import QSize
                from PySide6.QtGui import QImageReader
                reader=QImageReader(str(Path(__file__).resolve().parent/'assets/backgrounds'/(self.brand+'.svg')))
                reader.setScaledSize(QSize(1280,800));image=reader.read()
                if not image.isNull():self.brand_texture,self.brand_size=self.image_texture(image)
            except (RuntimeError,OSError):pass
        texture=self.art_texture if self.ui.appearance.mode=='game' and self.art_texture else self.brand_texture
        dimensions=self.art_size if texture and texture==self.art_texture else self.brand_size
        if texture and dimensions:
            width=C.c_int();height=C.c_int();self.window_size(self.window,C.byref(width),C.byref(height))
            target=max(1,width.value)/max(1,height.value);ratio=dimensions[0]/dimensions[1]
            crop=Rect(0,0,*dimensions)
            if ratio>target:crop.w=dimensions[1]*target;crop.x=(dimensions[0]-crop.w)/2
            else:crop.h=dimensions[0]/target;crop.y=(dimensions[1]-crop.h)/2
            self.render(self.renderer,texture,C.byref(crop),None)
        else:
            # An original code-native brand fallback also works without the SVG
            # plugin; each app retains its palette and controller motif.
            blue=self.brand=='rommayo'
            self.box(0,0,1280,800,(12,36,70,255) if blue else (9,62,37,255))
            for x in range(-400,1500,120):
                self.box(x,0,36,800,(24,79,125,255) if blue else (22,111,65,255))
            self.box(790,230,310,200,(25,102,155,255) if blue else (33,137,75,255))
            self.box(827,260,230,120,(8,30,50,255) if blue else (7,42,27,255))
        self.box(0,0,1280,800,(0,0,0,round(self.ui.appearance.dim*255/100)))

    def sound(self, frame):
        if not self.audio: return
        # Fixed stereo S16/48kHz; no unbounded queue accumulation during stalls.
        if self.audio_queued(self.audio) > 48000 * 4 // 4:
            self.audio_clear(self.audio); self.audio_dropped += 1
        pcm = bytes(frame.planes[0])[:frame.samples * 4]
        self.audio_data(self.audio, pcm, len(pcm)); self.audio_frames += frame.samples

    def close(self):
        for pad in self.pads.values(): self.close_pad(pad)
        self.pads.clear()
        if self.audio: self.audio_destroy(self.audio); self.audio = None
        if self.texture: self.destroy_texture(self.texture); self.texture = None
        if self.brand_texture:self.destroy_texture(self.brand_texture);self.brand_texture=None
        if self.art_texture:self.destroy_texture(self.art_texture);self.art_texture=None
        self.art.clear()
        if self.renderer: self.destroy_renderer(self.renderer); self.renderer = None
        if self.window: self.destroy_window(self.window); self.window = None
        self.quit()
