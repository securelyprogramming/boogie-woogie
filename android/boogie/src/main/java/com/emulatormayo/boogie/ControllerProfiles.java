package com.emulatormayo.boogie;

import android.content.Context;
import org.json.*;

/** Local numeric bindings only: no device names, game content or session credentials. */
final class ControllerProfiles {
 private final android.content.SharedPreferences prefs;
 ControllerProfiles(Context c){prefs=c.getSharedPreferences("controller-bindings-v1",0);}
 static boolean game(String key){return key!=null&&key.matches("sha256:[a-f0-9]{64}");}
 private JSONObject read(){try{String s=prefs.getString("profiles","{}");if(s.length()>32768)return new JSONObject();JSONObject o=new JSONObject(s),clean=new JSONObject();if(!(o.opt("schema") instanceof Integer)||o.optInt("schema")!=1||o.length()>33)return clean;clean.put("schema",1);java.util.Iterator<String> keys=o.keys();while(keys.hasNext()){String key=keys.next();if(key.matches("[a-f0-9]{64}(:sha256:[a-f0-9]{64})?")){ControllerMapping value=parse(o.optJSONArray(key));if(value!=null){JSONArray a=new JSONArray();for(int n:value.sources)a.put(n);clean.put(key,a);}}}return clean;}catch(Exception ignored){return new JSONObject();}}
 private ControllerMapping parse(JSONArray a){try{if(a==null||a.length()!=ControllerMapping.COUNT)return null;int[] values=new int[a.length()];for(int i=0;i<values.length;i++){Object value=a.get(i);if(!(value instanceof Integer))return null;values[i]=(Integer)value;}return new ControllerMapping(values);}catch(Exception ignored){return null;}}
 ControllerMapping load(String device,String game){JSONObject o=read();ControllerMapping m=game(game)?parse(o.optJSONArray(device+":"+game)):null;if(m==null)m=parse(o.optJSONArray(device));return m==null?ControllerMapping.defaults():m;}
 boolean save(String device,String game,ControllerMapping value){if(device==null||!device.matches("[a-f0-9]{64}")||game!=null&&!game(game))return false;try{JSONObject o=read();String key=device+(game==null?"":":"+game);if(o.length()>32&&!o.has(key))return false;o.put("schema",1);JSONArray a=new JSONArray();for(int s:value.sources)a.put(s);o.put(key,a);return prefs.edit().putString("profiles",o.toString()).commit();}catch(Exception ignored){return false;}}
}
