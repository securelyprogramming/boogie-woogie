package com.emulatormayo.boogie;
import android.content.Context;
import org.json.*;
import java.net.URI;
import java.io.*;

/** Local metadata only. Pairing credentials and ROM content never enter this store. */
final class RecentHistory {
 final Context context; JSONArray devices=new JSONArray(),games=new JSONArray();
 RecentHistory(Context c){context=c;try{File f=new File(c.getFilesDir(),"recent-history.json");if(f.length()>16384)return;JSONObject j=new JSONObject(MainActivity.read(new FileInputStream(f),16384));if(j.optInt("schema")!=1)return;devices=clean(j.optJSONArray("devices"),false,8);games=clean(j.optJSONArray("games"),true,12);}catch(Exception ignored){}}
 static String label(String s,int max){if(s==null)return "";StringBuilder b=new StringBuilder();for(int i=0;i<s.length()&&b.length()<max;i++){char c=s.charAt(i);if(!Character.isISOControl(c)&&c!='\u202e'&&c!='\u202d')b.append(c);}return b.toString().trim();}
 static String address(String value){try{URI u=new URI(value);if(!"https".equals(u.getScheme())||u.getHost()==null||u.getUserInfo()!=null||u.getQuery()!=null||u.getFragment()!=null||!(u.getPath().isEmpty()||u.getPath().equals("/"))||u.getPort()<1||u.getPort()>65535)return null;String[] parts=u.getHost().split("\\.");if(parts.length!=4)return null;int[] ip=new int[4];for(int i=0;i<4;i++){if(!parts[i].matches("0|[1-9][0-9]{0,2}"))return null;ip[i]=Integer.parseInt(parts[i]);if(ip[i]>255)return null;}if(!(ip[0]==10||ip[0]==192&&ip[1]==168||ip[0]==172&&ip[1]>=16&&ip[1]<=31))return null;return "https://"+u.getHost()+":"+u.getPort();}catch(Exception e){return null;}}
 static JSONArray clean(JSONArray source,boolean game,int max){JSONArray out=new JSONArray();if(source==null)return out;java.util.HashSet<String> seen=new java.util.HashSet<>();for(int i=0;i<source.length()&&out.length()<max;i++){JSONObject v=source.optJSONObject(i);if(v==null)continue;String url=address(v.optString("address")),key=v.optString("gameKey");long time=v.optLong("lastUsed");if(url==null||time<=0||time>System.currentTimeMillis()+86400000L||game&&!key.matches("sha256:[a-f0-9]{64}"))continue;String id=url+(game?key:"");if(!seen.add(id))continue;JSONObject item=MainActivity.obj("address",url,"device",label(v.optString("device"),48),"lastUsed",time);if(game){try{item.put("gameKey",key).put("title",label(v.optString("title"),80));}catch(Exception ignored){}}out.put(item);}return out;}
 void record(String address,String device,String game,String title){String url=address(address);if(url==null||!game.matches("sha256:[a-f0-9]{64}"))return;JSONObject item=MainActivity.obj("address",url,"device",label(device,48),"gameKey",game,"title",label(title,80),"lastUsed",System.currentTimeMillis());JSONArray d=new JSONArray().put(item),g=new JSONArray().put(item);for(int i=0;i<devices.length();i++)d.put(devices.opt(i));for(int i=0;i<games.length();i++)g.put(games.opt(i));devices=clean(d,false,8);games=clean(g,true,12);write();}
 void forget(boolean game,int index){JSONArray list=game?games:devices;list.remove(index);write();}
 void clear(){devices=new JSONArray();games=new JSONArray();write();}
 void write(){try{HostRommLibrary.atomicBytes(new File(context.getFilesDir(),"recent-history.json"),MainActivity.obj("schema",1,"devices",devices,"games",games).toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));}catch(Exception ignored){}}
}
