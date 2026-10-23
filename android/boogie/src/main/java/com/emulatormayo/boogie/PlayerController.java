package com.emulatormayo.boogie;

import android.content.Context;
import android.hardware.input.InputManager;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.webkit.WebView;
import org.json.JSONArray;
import org.json.JSONObject;

/** One native gameplay controller, exposed to the bundled local player only. */
final class PlayerController implements InputManager.InputDeviceListener {
    private final WebView view;
    private final InputManager manager;
    private final GamepadState state = new GamepadState();
    private int deviceId = Integer.MIN_VALUE;
    private boolean ready;
    private String deviceName;
    private String gameKey;
    private final ControllerProfiles profiles;
    private ControllerMapping mapping=ControllerMapping.defaults();
    private final ControllerInputGate gate=new ControllerInputGate();
    interface Capture { void sample(float[] values); }
    private Capture capture;
    void setGame(String key){gameKey=ControllerProfiles.game(key)?key:null;reload();release();}
    String deviceKey(){try{InputDevice d=InputDevice.getDevice(deviceId);String id=d==null?"none":d.getVendorId()+":"+d.getProductId()+":"+d.getName();byte[] hash=java.security.MessageDigest.getInstance("SHA-256").digest(id.getBytes(java.nio.charset.StandardCharsets.UTF_8));StringBuilder out=new StringBuilder();for(byte part:hash)out.append(String.format("%02x",part&255));return out.toString();}catch(Exception e){throw new IllegalStateException(e);}}
    boolean neutral(){float[] b=new float[17];for(int i=0;i<17;i++)b[i]=state.button(i);return ControllerMapping.neutral(ControllerMapping.flatten(b,state.axes));}
    boolean hasDevice(){return deviceName!=null;}
    String deviceLabel(){String label=deviceName==null?"No physical controller":deviceName.replaceAll("[\\p{Cntrl}]", " ").trim();return label.length()>60?label.substring(0,60):label;}
    int deviceCount(){int count=0;for(int id:InputDevice.getDeviceIds())if(controller(InputDevice.getDevice(id)))count++;return count;}
    ControllerMapping profile(){return mapping.copy();}
    boolean save(ControllerMapping value,boolean game){boolean ok=profiles.save(deviceKey(),game?gameKey:null,value);if(ok)reload();return ok;}
    void reload(){mapping=profiles.load(deviceKey(),gameKey);}
    void editing(boolean active,Capture listener){gate.editing(active);capture=listener;if(trustedView())view.evaluateJavascript("window.boogieSetEditing?.("+active+")",null);send(false);}
    private boolean trustedView(){if(!ready||view.getUrl()==null)return false;android.net.Uri uri=android.net.Uri.parse(view.getUrl());return "https".equals(uri.getScheme())&&"appassets.androidplatform.net".equals(uri.getHost())&&"/boogie/player.html".equals(uri.getPath())&&uri.getUserInfo()==null&&(uri.getPort()==-1||uri.getPort()==443);}

    PlayerController(WebView view) {
        this.view = view;
        profiles=new ControllerProfiles(view.getContext());
        manager = (InputManager)view.getContext().getSystemService(Context.INPUT_SERVICE);
        manager.registerInputDeviceListener(this, null);
    }
    void loaded() { ready = true; select(); send(false); }
    void loading() { ready = false; state.clear(); }
    private static boolean controller(InputDevice device) {
        return device != null && (device.supportsSource(InputDevice.SOURCE_GAMEPAD) || device.supportsSource(InputDevice.SOURCE_JOYSTICK));
    }
    private void select() {
        if (controller(InputDevice.getDevice(deviceId))) return;
        deviceId = Integer.MIN_VALUE;
        deviceName = null;
        state.clear();
        for (int id : InputDevice.getDeviceIds()) if (controller(InputDevice.getDevice(id))) { deviceId = id; deviceName = InputDevice.getDevice(id).getName(); break; }
        reload();gate.release();
    }
    boolean key(KeyEvent event) {
        if (!ready || event.getDeviceId() != deviceId) return false;
        int button = button(event.getKeyCode());
        if (button < 0 || (event.getAction() != KeyEvent.ACTION_DOWN && event.getAction() != KeyEvent.ACTION_UP)) return false;
        if (event.getAction() == KeyEvent.ACTION_DOWN && event.getRepeatCount() != 0) return true;
        state.key(button, event.getAction() == KeyEvent.ACTION_DOWN);
        send();
        return true;
    }
    boolean motion(MotionEvent event) {
        if (!ready || event.getDevice() == null || event.getDeviceId() != deviceId || !event.isFromSource(InputDevice.SOURCE_JOYSTICK) || event.getAction() != MotionEvent.ACTION_MOVE) return false;
        state.motion(axis(event, MotionEvent.AXIS_X), axis(event, MotionEvent.AXIS_Y), axis(event, supportedAxis(event, MotionEvent.AXIS_Z, MotionEvent.AXIS_RX)), axis(event, supportedAxis(event, MotionEvent.AXIS_RZ, MotionEvent.AXIS_RY)),
            event.getAxisValue(MotionEvent.AXIS_HAT_X), event.getAxisValue(MotionEvent.AXIS_HAT_Y),
            Math.max(event.getAxisValue(MotionEvent.AXIS_LTRIGGER), event.getAxisValue(MotionEvent.AXIS_BRAKE)),
            Math.max(event.getAxisValue(MotionEvent.AXIS_RTRIGGER), event.getAxisValue(MotionEvent.AXIS_GAS)));
        send();
        return true;
    }
    private int supportedAxis(MotionEvent event, int preferred, int fallback) {
        return event.getDevice().getMotionRange(preferred, event.getSource()) == null ? fallback : preferred;
    }
    private float axis(MotionEvent event, int axis) {
        InputDevice.MotionRange range = event.getDevice().getMotionRange(axis, event.getSource());
        float value = event.getAxisValue(axis);
        return Math.abs(value) <= Math.max(.15f, range == null ? 0 : range.getFlat()) ? 0 : value;
    }
    static int button(int key) {
        switch (key) {
            case KeyEvent.KEYCODE_BUTTON_A: return 0;
            case KeyEvent.KEYCODE_BUTTON_B: return 1;
            case KeyEvent.KEYCODE_BUTTON_X: return 2;
            case KeyEvent.KEYCODE_BUTTON_Y: return 3;
            case KeyEvent.KEYCODE_BUTTON_L1: return 4;
            case KeyEvent.KEYCODE_BUTTON_R1: return 5;
            case KeyEvent.KEYCODE_BUTTON_L2: return 6;
            case KeyEvent.KEYCODE_BUTTON_R2: return 7;
            case KeyEvent.KEYCODE_BUTTON_SELECT: return 8;
            case KeyEvent.KEYCODE_BUTTON_START: return 9;
            case KeyEvent.KEYCODE_BUTTON_THUMBL: return 10;
            case KeyEvent.KEYCODE_BUTTON_THUMBR: return 11;
            case KeyEvent.KEYCODE_BUTTON_MODE: return 16;
            case KeyEvent.KEYCODE_DPAD_UP: return 12;
            case KeyEvent.KEYCODE_DPAD_DOWN: return 13;
            case KeyEvent.KEYCODE_DPAD_LEFT: return 14;
            case KeyEvent.KEYCODE_DPAD_RIGHT: return 15;
            default: return -1;
        }
    }
    void release() { state.clear(); gate.release(); send(false); }
    private void send() {send(true);}
    private void send(boolean physicalSample) {
        // Never execute this callback in another page, including after navigation.
        if (!ready || view.getUrl() == null) return;
        android.net.Uri uri = android.net.Uri.parse(view.getUrl());
        if (!"https".equals(uri.getScheme()) || !"appassets.androidplatform.net".equals(uri.getHost()) || !"/boogie/player.html".equals(uri.getPath()) || uri.getUserInfo() != null || (uri.getPort() != -1 && uri.getPort() != 443)) return;
        try {
            float[] rawButtons=new float[17];for(int i=0;i<17;i++)rawButtons[i]=state.button(i);
            float[] raw=ControllerMapping.flatten(rawButtons,state.axes);
            if(physicalSample&&capture!=null)capture.sample(raw.clone());
            float[] mapped=mapping.apply(gate.filter(raw,physicalSample));
            JSONArray pads = new JSONArray();
            if (deviceName == null) pads.put(JSONObject.NULL);
            else {
                JSONObject pad = new JSONObject();
                pad.put("id", "Android: " + deviceName);
                JSONArray buttons = new JSONArray(), axes = new JSONArray();
                for (int i = 0; i < 17; i++) buttons.put(mapped[i]);
                for(int i=0;i<4;i++)axes.put(mapped[18+i*2]-mapped[17+i*2]);
                pad.put("buttons", buttons); pad.put("axes", axes); pads.put(pad);
            }
            for (int i = 1; i < 4; i++) pads.put(JSONObject.NULL);
            view.evaluateJavascript("window.boogieNativePads?.(" + pads + ")", null);
        } catch (org.json.JSONException ignored) { /* Finite, bounded input only. */ }
    }
    void close() { release(); ready = false; manager.unregisterInputDeviceListener(this); }
    @Override public void onInputDeviceAdded(int id) { select(); send(false); }
    @Override public void onInputDeviceChanged(int id) { release(); select(); send(false); }
    @Override public void onInputDeviceRemoved(int id) { if (id == deviceId) { release(); deviceId = Integer.MIN_VALUE; deviceName = null; send(false); select(); send(false); } }
}
