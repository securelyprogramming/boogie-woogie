package com.emulatormayo.boogie;

import android.app.*;
import android.os.*;
import android.util.Base64;
import android.webkit.WebView;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Host-private checkpoints, committed only after a bounded complete transfer. */
public final class NativeStateStore {
 static final int MAX=8*1024*1024, CHUNK=32768, SLOTS=32;
 static final String CORE="ejs-4.2.3:fceumm-legacy-wasm:f1054b094e7149fd6278485bc1b2e51ff75c5259048ddb1134171e53d651f239";
 public static final class Entry { public String id,label; public long savedAt; boolean quick; int size; String sha; }
 final Activity activity; final WebView web; final String gameKey; final File directory;
 final Handler handler=new Handler(Looper.getMainLooper());
 boolean closed,ready; String request,slot,label,queuedSlot; int expected,index,written; boolean saving,quick; File temporary,uncommittedBinary,uncommittedMetadata; FileOutputStream output; byte[] loading; Runnable afterSave,afterFailure;
 final Runnable timeout=()->abort("Checkpoint timed out; previous saves are unchanged.");
 public NativeStateStore(Activity activity,WebView web,String gameKey){this.activity=activity;this.web=web;this.gameKey=gameKey;directory=folder(activity.getFilesDir(),gameKey);}
 static File folder(File files,String key){if(key==null||!key.matches("sha256:[a-f0-9]{64}"))throw new IllegalArgumentException("Invalid game identity");return new File(new File(files,"states"),key.substring(7));}
 static String digest(byte[] bytes)throws Exception{byte[] hash=MessageDigest.getInstance("SHA-256").digest(bytes);StringBuilder result=new StringBuilder();for(byte b:hash)result.append(String.format("%02x",b&255));return result.toString();}
 static boolean validBase64(String value){if(value==null||value.length()<4||value.length()>43692||value.length()%4!=0)return false;int padding=0;for(int i=0;i<value.length();i++){char c=value.charAt(i);if(c=='='){padding++;if(i<value.length()-2||padding>2)return false;}else if(padding!=0||!(c>='A'&&c<='Z'||c>='a'&&c<='z'||c>='0'&&c<='9'||c=='+'||c=='/'))return false;}return true;}
 static boolean id(String value){return value!=null&&value.matches("[a-f0-9]{32}");}
 public static List<Entry> listEntries(File files,String key){List<Entry> all=new ArrayList<>();try{File dir=folder(files,key);File[] paths=dir.listFiles((d,n)->n.matches("[a-f0-9]{32}\\.json"));if(paths==null)return all;Arrays.sort(paths,Comparator.comparing(File::getName));for(int i=0;i<Math.min(paths.length,128);i++){File path=paths[i];try{if(path.length()>4096)continue;JSONObject m=new JSONObject(new String(Files.readAllBytes(path.toPath()),java.nio.charset.StandardCharsets.UTF_8));Entry e=new Entry();e.id=m.getString("id");e.label=m.getString("label");e.savedAt=m.getLong("savedAt");e.quick=m.optBoolean("quick");e.size=m.getInt("size");e.sha=m.getString("sha256");if(!id(e.id)||!path.getName().equals(e.id+".json")||!CORE.equals(m.optString("core"))||!key.equals(m.optString("gameKey"))||m.optInt("schema")!=1||e.label.length()>64||e.savedAt<1||e.size<1||e.size>MAX||!e.sha.matches("[a-f0-9]{64}")||new File(dir,e.id+".bin").length()!=e.size)continue;all.add(e);}catch(Exception ignored){}}}catch(Exception ignored){}all.sort((a,b)->Long.compare(b.savedAt,a.savedAt));return all;}
 public static boolean hasState(File files,String gameKey){return !listEntries(files,gameKey).isEmpty();}
 public void showSave(boolean saveAs){if(!available())return;if(!saveAs){save("Quick save",true,null);return;}EditText input=new EditText(activity);input.setSingleLine();input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(64)});input.setHint("Save name");new AlertDialog.Builder(activity).setTitle("Save as · this game").setView(input).setNegativeButton("Cancel",null).setPositiveButton("Save",(d,w)->{String name=input.getText().toString().trim();if(name.isEmpty())notice("Enter a save name.");else save(name,false,null);}).show();}
 public void showLoad(){if(!available())return;List<Entry> entries=listEntries(activity.getFilesDir(),gameKey);if(entries.isEmpty()){notice("No compatible saves for this game yet.");return;}String[] labels=new String[entries.size()];for(int i=0;i<labels.length;i++)labels[i]=entries.get(i).label+" · "+android.text.format.DateFormat.format("MMM d, h:mm a",entries.get(i).savedAt);new AlertDialog.Builder(activity).setTitle("Load · this game").setItems(labels,(d,w)->loadSlot(entries.get(w).id)).setNegativeButton("Cancel",null).show();}
 public void saveBeforeSwitch(Runnable success){saveBeforeSwitch(success,()->{});}
 public void saveBeforeSwitch(Runnable success,Runnable failure){if(!available()){failure.run();return;}save("Quick save",true,success);if(request!=null)afterFailure=failure;else failure.run();}
 public void resumeLatest(){List<Entry> entries=listEntries(activity.getFilesDir(),gameKey);if(!entries.isEmpty())loadSlot(entries.get(0).id);}
 public void loadSlot(String value){if(closed||!id(value))return;if(!ready){queuedSlot=value;return;}if(request!=null){notice("A checkpoint operation is already running.");return;}try{Entry selected=null;for(Entry entry:listEntries(activity.getFilesDir(),gameKey))if(entry.id.equals(value))selected=entry;if(selected==null)throw new IOException();byte[] bytes=Files.readAllBytes(new File(directory,value+".bin").toPath());if(bytes.length!=selected.size||!digest(bytes).equals(selected.sha))throw new IOException();start(false);loading=bytes;send("load",MainActivity.obj("size",bytes.length));}catch(Exception e){abort("This save could not be verified. Your game was left running.");}}
 boolean available(){if(closed)return false;if(request!=null){notice("A checkpoint operation is already running.");return false;}if(!ready){notice("Start the game before saving.");return false;}return true;}
 void save(String name,boolean isQuick,Runnable success){if(!available())return;List<Entry> existing=listEntries(activity.getFilesDir(),gameKey);long total=0;int named=0;for(Entry e:existing){total+=e.size;if(!e.quick)named++;}if((!isQuick&&named>=SLOTS)||total>64L*1024*1024-MAX){notice("Save storage is full; existing saves were kept.");return;}try{directory.mkdirs();start(true);label=name;quick=isQuick;afterSave=success;slot=UUID.randomUUID().toString().replace("-","");temporary=new File(directory,slot+".tmp");output=new FileOutputStream(temporary);send("save",new JSONObject());}catch(Exception e){abort("Could not create a checkpoint. Previous saves were kept.");}}
 void start(boolean isSaving){request="s"+UUID.randomUUID().toString().replace("-","");saving=isSaving;expected=0;written=0;index=0;handler.postDelayed(timeout,30000);}
 void send(String op,JSONObject value){if(closed||request==null)return;try{value.put("op",op).put("id",request);web.evaluateJavascript("window.boogieState?.("+value+")",null);}catch(Exception e){abort("Checkpoint transport failed.");}}
 public boolean onMessage(JSONObject value){if(!"state-result".equals(value.optString("type")))return false;if(closed)return true;String phase=value.optString("phase");if("core-ready".equals(phase)){ready=true;String queued=queuedSlot;queuedSlot=null;if(queued!=null)loadSlot(queued);return true;}if(request==null||!request.equals(value.optString("id")))return true;try{switch(phase){
 case "begin": if(!saving||expected!=0)throw new IOException();expected=value.getInt("size");if(expected<1||expected>MAX)throw new IOException();send("next",MainActivity.obj("index",index));break;
 case "chunk": if(!saving||expected==0||value.getInt("index")!=index)throw new IOException();String encoded=value.getString("data");if(!validBase64(encoded))throw new IOException();byte[] bytes=Base64.decode(encoded,Base64.NO_WRAP);if(!Base64.encodeToString(bytes,Base64.NO_WRAP).equals(encoded))throw new IOException();if(bytes.length!=Math.min(CHUNK,expected-written))throw new IOException();output.write(bytes);written+=bytes.length;index++;send("next",MainActivity.obj("index",index));break;
 case "end": if(!saving||expected==0||written!=expected)throw new IOException();output.getFD().sync();output.close();output=null;byte[] saved=Files.readAllBytes(temporary.toPath());String hash=digest(saved);uncommittedBinary=new File(directory,slot+".bin");Files.move(temporary.toPath(),uncommittedBinary.toPath(),StandardCopyOption.ATOMIC_MOVE);temporary=null;JSONObject metadata=MainActivity.obj("schema",1,"core",CORE,"gameKey",gameKey,"id",slot,"label",label,"quick",quick,"savedAt",System.currentTimeMillis(),"size",written,"sha256",hash);File pending=new File(directory,slot+".pending");uncommittedMetadata=pending;try(FileOutputStream stream=new FileOutputStream(pending)){stream.write(metadata.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));stream.getFD().sync();}Files.move(pending.toPath(),new File(directory,slot+".json").toPath(),StandardCopyOption.ATOMIC_MOVE);uncommittedBinary=null;uncommittedMetadata=null;if(quick)for(Entry old:listEntries(activity.getFilesDir(),gameKey))if(old.quick&&!old.id.equals(slot)){new File(directory,old.id+".json").delete();new File(directory,old.id+".bin").delete();}Runnable done=afterSave;send("finish",new JSONObject());clear();notice("Saved · "+label);if(done!=null)done.run();break;
 case "ready": if(saving||loading==null)throw new IOException();sendLoadChunk();break;
 case "ack": if(saving||loading==null||value.getInt("index")!=index-1)throw new IOException();sendLoadChunk();break;
 case "loaded": if(saving||loading==null||written!=loading.length)throw new IOException();clear();notice("Save loaded.");break;
 case "error": abort("Checkpoint failed. Previous saves are unchanged.");break;
 default: throw new IOException();
 }}catch(Exception e){abort("Checkpoint failed verification. Previous saves are unchanged.");}return true;}
 void sendLoadChunk(){if(written==loading.length){send("commit",new JSONObject());return;}int end=Math.min(written+CHUNK,loading.length);String encoded=Base64.encodeToString(Arrays.copyOfRange(loading,written,end),Base64.NO_WRAP);written=end;send("append",MainActivity.obj("index",index++,"data",encoded));}
 void notice(String message){if(!closed)Toast.makeText(activity,message,Toast.LENGTH_LONG).show();}
 void abort(String message){Runnable failure=afterFailure;if(request!=null)send("cancel",new JSONObject());clear();notice(message);if(failure!=null)failure.run();}
 void clear(){handler.removeCallbacks(timeout);try{if(output!=null)output.close();}catch(Exception ignored){}output=null;if(temporary!=null)temporary.delete();temporary=null;if(uncommittedBinary!=null)uncommittedBinary.delete();if(uncommittedMetadata!=null)uncommittedMetadata.delete();uncommittedBinary=null;uncommittedMetadata=null;request=null;loading=null;afterSave=null;afterFailure=null;}
 public void close(){if(closed)return;if(request!=null)send("cancel",new JSONObject());clear();queuedSlot=null;closed=true;}
}
