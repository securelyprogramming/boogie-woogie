package com.emulatormayo.boogie;

import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.function.BooleanSupplier;

/** Private preview RomM provider. Credentials never leave this native transport. */
public final class HostRommLibrary {
 public static final int PAGE_SIZE=30, MAX_ROM=64*1024*1024;
 private final File files; private final String base,cookie; private final BooleanSupplier cancelled;
 private String accountKey; private boolean localOnly;
 public static HostRommLibrary local(File files,BooleanSupplier cancelled)throws Exception{return new HostRommLibrary(files,cancelled,true);}
 private HostRommLibrary(File files,BooleanSupplier cancelled,boolean local)throws Exception{this.files=files.getCanonicalFile();this.cancelled=cancelled;this.localOnly=local;this.base="";this.cookie="";this.accountKey=BoogieIntegration.LOCAL_ACCOUNT;}
 public static final class Game {
  public final int romId,platformId; public final String title,filename,platform,slug; public final boolean supported; public final long size;
  Game(JSONObject j)throws Exception {
   romId=j.getInt("id"); if(romId<1)throw new IOException("Invalid library entry.");
   platformId=Math.max(0,j.optInt("platform_id",0));filename=j.optString("fs_name",""); title=text(j.optString("name",filename),300,"Untitled");
   platform=text(j.optString("platform_display_name",j.optString("platform_slug")),100,"Unknown platform"); slug=j.optString("platform_slug",""); size=j.optLong("fs_size_bytes",0);
   supported="nes".equals(slug)&&filename.toLowerCase(Locale.ROOT).endsWith(".nes")&&safeFilename(filename)&&!j.optBoolean("missing_from_fs",false)&&j.optBoolean("has_file_on_disk",true)&&size>=0&&size<=MAX_ROM;
  }
  JSONObject json()throws Exception{return new JSONObject().put("id",romId).put("platform_id",platformId).put("name",title).put("fs_name",filename).put("platform_display_name",platform).put("platform_slug",slug).put("fs_size_bytes",size);}
 }
 public static final class Platform {
  public final int id;public final String name,slug;
  Platform(JSONObject value)throws Exception{id=value.getInt("id");if(id<1)throw new IOException("Invalid platform.");name=text(value.optString("display_name",value.optString("name")),100,"Unknown platform");slug=text(value.optString("slug"),100,"");}
  boolean matches(Game game){return game.platformId==id||game.platformId==0&&!slug.isEmpty()&&slug.equals(game.slug);}
 }
 public List<Platform> platforms()throws Exception {
  if(localOnly)return Collections.singletonList(new Platform(new JSONObject().put("id",1).put("display_name","NES").put("slug","nes")));
  verify();ByteArrayOutputStream bytes=new ByteArrayOutputStream();transfer("/api/platforms",bytes,2*1024*1024);JSONArray items=new JSONArray(bytes.toString("UTF-8"));List<Platform> result=new ArrayList<>();Set<Integer> ids=new HashSet<>();
  for(int i=0;i<Math.min(items.length(),512);i++){check();try{Platform platform=new Platform(items.getJSONObject(i));if(ids.add(platform.id))result.add(platform);}catch(JSONException|IOException ignored){}}
  result.sort(Comparator.comparing(p->p.name,String.CASE_INSENSITIVE_ORDER));return Collections.unmodifiableList(result);
 }
 public static final class Page {public final List<Game> games;public final boolean hasNext;Page(List<Game> g,boolean n){games=Collections.unmodifiableList(g);hasNext=n;}}
 public static final class Prepared {
  public final Game game;public final String accountKey,gameKey;public final File cachedGame;
  Prepared(Game g,String a,String k,File f){game=g;accountKey=a;gameKey=k;cachedGame=f;}
 }
 public static final class Activation implements AutoCloseable {
  final File game,metadata;final Prepared prepared;
  Activation(File g,File m,Prepared p){game=g;metadata=m;prepared=p;}
  public void close(){game.delete();metadata.delete();}
 }
 public HostRommLibrary(File files,BooleanSupplier cancelled)throws Exception {
  this.files=files.getCanonicalFile();this.cancelled=cancelled;
  JSONObject config=BoogieIntegration.rommSession();
  if(config==null){base="";cookie="";localOnly=true;accountKey=BoogieIntegration.LOCAL_ACCOUNT;return;}
  String raw=config.optString("rommServer","").trim();cookie=config.optString("rommCookie","");
  URI uri=new URI(raw);String path=uri.getRawPath();
  if(!Arrays.asList("http","https").contains(uri.getScheme())||uri.getHost()==null||uri.getRawUserInfo()!=null||uri.getRawQuery()!=null||uri.getRawFragment()!=null||uri.getPort()<-1||uri.getPort()>65535||raw.length()>2048||raw.chars().anyMatch(c->c<32||c==127)||path!=null&&(path.contains("%")||path.contains("\\")||Arrays.asList(path.split("/",-1)).contains("..")))throw new IOException("Configure a valid RomM server for this host.");
  if(cookie.isEmpty()||cookie.length()>16384||cookie.chars().anyMatch(c->c<32||c==127))throw new IOException("Connect this host to RomM before browsing its library.");
  base=raw.replaceAll("/+$","");
 }
 static String text(String value,int max,String fallback){String t=value==null?"":value.replaceAll("[\\p{Cntrl}]","").trim();return t.isEmpty()?fallback:t.substring(0,Math.min(t.length(),max));}
 static boolean safeFilename(String value){return value!=null&&!value.isEmpty()&&value.length()<=512&&!value.contains("/")&&!value.contains("\\")&&!value.equals(".")&&!value.equals("..")&&value.chars().noneMatch(c->c<32||c==127);}
 void check()throws InterruptedIOException{if(Thread.currentThread().isInterrupted()||cancelled.getAsBoolean())throw new InterruptedIOException("Library operation cancelled.");}
 public String verify()throws Exception {
  if(localOnly){check();return accountKey;}
  JSONObject user=json("/api/users/me",65536);int id=user.getInt("id");if(id<1)throw new IOException("RomM account could not be verified.");
  String next=hex(MessageDigest.getInstance("SHA-256").digest((base+"/"+id).getBytes(StandardCharsets.UTF_8)));
  if(accountKey!=null&&!accountKey.equals(next))throw new IOException("The RomM account changed. Reopen the game chooser.");accountKey=next;return next;
 }
 public Page list(String query,boolean recent,int offset)throws Exception {
  return list(query,recent,offset,null);
 }
 public Page list(String query,boolean recent,int offset,Platform platform)throws Exception {
  if(localOnly)return localList(query,recent,offset);
  verify();check();String q=query==null?"":query.trim();if(q.length()>200)q=q.substring(0,200);
  String route="/api/roms?limit="+PAGE_SIZE+"&offset="+Math.max(0,offset)+"&missing=false&with_char_index=false&with_filter_values=false&with_rom_id_index=false";
  if(!q.isEmpty())route+="&search_term="+URLEncoder.encode(q,"UTF-8");
  if(platform!=null)route+="&platform_ids="+platform.id;
  if(recent)route+="&last_played=true&order_by=last_played&order_dir=desc";
  JSONObject response=json(route,2*1024*1024);JSONArray items=response.getJSONArray("items");List<Game> games=new ArrayList<>();
  for(int i=0;i<Math.min(items.length(),PAGE_SIZE);i++){check();try{games.add(new Game(items.getJSONObject(i)));}catch(Exception ignored){}}
  boolean more=offset+items.length()<response.optLong("total",offset+items.length());
  if(recent&&offset==0){List<Game> local=localRecent();Set<Integer> ids=new HashSet<>();List<Game> merged=new ArrayList<>();String term=q.toLowerCase(Locale.ROOT);for(Game g:local)if((platform==null||platform.matches(g))&&(term.isEmpty()||(g.title+" "+g.filename).toLowerCase(Locale.ROOT).contains(term))&&ids.add(g.romId))merged.add(g);for(Game g:games)if(ids.add(g.romId))merged.add(g);games=merged;}
  return new Page(games,more);
 }
 private List<Game> localGames()throws Exception {List<Game> all=new ArrayList<>();for(int offset=0;offset<500;offset+=PAGE_SIZE){Page page=localList("",false,offset);all.addAll(page.games);if(!page.hasNext)break;}return all;}
 private Page localList(String query,boolean recent,int offset)throws Exception {
  verify();List<Game> games=new ArrayList<>();File folder=new File(accountFolder(),"games");File[] records=folder.listFiles((d,n)->n.matches("[a-f0-9]{64}\\.json"));
  if(records!=null){Arrays.sort(records,Comparator.comparingLong(File::lastModified).reversed());for(File record:records){check();if(games.size()>=500)break;try{Game game=new Game(new JSONObject(new String(readBounded(record,8192),StandardCharsets.UTF_8)));String term=query==null?"":query.toLowerCase(Locale.ROOT);if(game.title.toLowerCase(Locale.ROOT).contains(term))games.add(game);}catch(Exception ignored){}}}
  if(recent){List<Game> all=games;games=new ArrayList<>();Set<Integer> ids=new HashSet<>();for(Game old:localRecent())for(Game game:all)if(old.romId==game.romId&&ids.add(game.romId))games.add(game);}
  int start=Math.min(Math.max(0,offset),games.size()),end=Math.min(start+PAGE_SIZE,games.size());return new Page(new ArrayList<>(games.subList(start,end)),end<games.size());
 }
 private File accountFolder()throws IOException{if(accountKey==null)throw new IOException("Account not verified.");File dir=new File(new File(files,"romm-library"),accountKey);if(!dir.isDirectory()&&!dir.mkdirs())throw new IOException("Could not open private game cache.");return dir;}
 private List<Game> localRecent(){List<Game> rows=new ArrayList<>();try{JSONArray a=new JSONArray(new String(readBounded(new File(accountFolder(),"recent.json"),65536),StandardCharsets.UTF_8));for(int i=0;i<Math.min(a.length(),20);i++)try{rows.add(new Game(a.getJSONObject(i)));}catch(Exception ignored){}}catch(Exception ignored){}return rows;}
 public Prepared download(Game selected)throws Exception {
  if(localOnly){verify();for(Game game:localGames())if(game.romId==selected.romId){String digest=game.filename.substring(0,64);File file=new File(new File(accountFolder(),"games"),digest+".nes");if(!verifyGame(file).equals(digest))throw new IOException("Local game changed");return new Prepared(game,accountKey,"sha256:"+digest,file);}throw new IOException("Local game not found");}
  verify();Game game=new Game(json("/api/roms/"+selected.romId,2*1024*1024));if(!game.supported)throw new IOException("This native LAN preview currently supports NES .nes games only.");
  File dir=new File(accountFolder(),"games");if(!dir.isDirectory()&&!dir.mkdirs())throw new IOException("Could not open game storage.");
  File pending=File.createTempFile("download-",".tmp",dir);privateFile(pending);
  try{
   String name=URLEncoder.encode(game.filename,"UTF-8").replace("+","%20");
   try(FileOutputStream out=new FileOutputStream(pending)){transfer("/api/roms/"+game.romId+"/content/"+name+"?purpose=play",out,MAX_ROM);out.getFD().sync();}
   String hash=verifyGame(pending);File cached=new File(dir,hash+".nes");check();atomicMove(pending,cached);
   return new Prepared(game,accountKey,"sha256:"+hash,cached);
  }finally{pending.delete();}
 }
 public Activation stage(Prepared prepared)throws Exception {
  verify();if(!accountKey.equals(prepared.accountKey)||!prepared.gameKey.matches("sha256:[a-f0-9]{64}"))throw new IOException("This game belongs to a different RomM account.");
  File expected=new File(new File(accountFolder(),"games"),prepared.gameKey.substring(7)+".nes").getCanonicalFile();
  if(!expected.equals(prepared.cachedGame.getCanonicalFile())||!verifyGame(expected).equals(prepared.gameKey.substring(7)))throw new IOException("Cached game verification failed. Select it again.");
  File game=File.createTempFile("game-",".pending",files),metadata=File.createTempFile("current-",".pending",files);privateFile(game);privateFile(metadata);
  try{
   try(InputStream in=new FileInputStream(expected);FileOutputStream out=new FileOutputStream(game)){byte[] bytes=new byte[65536];int n;while((n=in.read(bytes))!=-1){check();out.write(bytes,0,n);}out.getFD().sync();}
   // Keys here identify an account cache and ROM content; neither authorizes access.
   // Game.json() builds a fresh allowlist and cannot serialize the native session cookie.
   JSONObject record=prepared.game.json().put("schema",1).put("accountKey",accountKey).put("gameKey",prepared.gameKey).put("savedAt",System.currentTimeMillis());
   try(FileOutputStream out=new FileOutputStream(metadata)){out.write(record.toString().getBytes(StandardCharsets.UTF_8));out.getFD().sync();}check();return new Activation(game,metadata,prepared);
  }catch(Exception e){game.delete();metadata.delete();throw e;}
 }
 /** Caller must hold its lifecycle lock and check cancellation immediately before calling. */
 public void commit(Activation staged)throws Exception {
  check();File active=new File(files,"game.nes"),record=new File(files,"current-game.json");
  String transaction=UUID.randomUUID().toString();File previousGame=new File(files,"game-"+transaction+".rollback"),previousRecord=new File(files,"current-"+transaction+".rollback");
  boolean gameBacked=false,recordBacked=false,gameInstalled=false,recordInstalled=false;
  try{
   if(active.exists()){atomicMove(active,previousGame);gameBacked=true;}
   if(record.exists()){atomicMove(record,previousRecord);recordBacked=true;}
   atomicMove(staged.game,active);gameInstalled=true;
   atomicMove(staged.metadata,record);recordInstalled=true;
  }catch(Exception failure){
   // Keep caller's existing game identity valid if either installation move fails.
   try{if(gameInstalled)Files.deleteIfExists(active.toPath());if(gameBacked)atomicMove(previousGame,active);}catch(Exception rollback){failure.addSuppressed(rollback);}
   try{if(recordInstalled)Files.deleteIfExists(record.toPath());if(recordBacked)atomicMove(previousRecord,record);}catch(Exception rollback){failure.addSuppressed(rollback);}
   throw failure;
  }
  previousGame.delete();previousRecord.delete();
  try{List<Game> history=localRecent();history.removeIf(g->g.romId==staged.prepared.game.romId);history.add(0,staged.prepared.game);JSONArray array=new JSONArray();for(int i=0;i<Math.min(20,history.size());i++)array.put(history.get(i).json());atomicBytes(new File(accountFolder(),"recent.json"),array.toString().getBytes(StandardCharsets.UTF_8));}catch(Exception ignored){}
 }
 public static Prepared current(File files){
  try{JSONObject j=new JSONObject(new String(readBounded(new File(files,"current-game.json"),8192),StandardCharsets.UTF_8));String account=j.getString("accountKey"),key=j.getString("gameKey");if(j.optInt("schema")!=1||!account.matches("[a-f0-9]{64}")||!key.matches("sha256:[a-f0-9]{64}")||!verifyGame(new File(files,"game.nes")).equals(key.substring(7)))return null;Game game=new Game(j);if(!game.supported)return null;File cached=new File(new File(new File(files,"romm-library"),account),"games/"+key.substring(7)+".nes");return new Prepared(game,account,key,cached);}catch(Exception e){return null;}
 }
 /** Native-only cover fetch. No resource URL or account cookie is handed to the player. */
 public byte[] artwork(int romId,String expectedAccount)throws Exception {
  if(localOnly)return null;
  if(romId<1||expectedAccount==null||!expectedAccount.matches("[a-f0-9]{64}")||!verify().equals(expectedAccount))throw new IOException("Artwork account changed.");
  JSONObject game=json("/api/roms/"+romId,2*1024*1024);if(game.optInt("id")!=romId)throw new IOException("Artwork game changed.");String source=game.optString("path_cover_small","");if(source.isEmpty())source=game.optString("path_cover","");if(source.isEmpty())return null;String route=ArtworkPolicy.route(base,source);
  check();HttpURLConnection connection=(HttpURLConnection)new URL(base+route).openConnection();connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(3000);connection.setReadTimeout(3000);connection.setRequestProperty("Cookie",cookie);connection.setRequestProperty("Accept","image/jpeg,image/png,image/webp");connection.setRequestProperty("Accept-Encoding","identity");long end=System.nanoTime()+8_000_000_000L;
  try{if(connection.getResponseCode()!=200||connection.getContentLengthLong()>ArtworkPolicy.MAX_SOURCE)throw new IOException("Artwork unavailable.");String type=connection.getContentType();if(type==null||!Arrays.asList("image/jpeg","image/png","image/webp").contains(type.split(";",2)[0].trim().toLowerCase(Locale.ROOT)))throw new IOException("Unsupported artwork type.");ByteArrayOutputStream out=new ByteArrayOutputStream();try(InputStream in=connection.getInputStream()){byte[] chunk=new byte[16384];int count;while((count=in.read(chunk))!=-1){check();if(System.nanoTime()>end||count>ArtworkPolicy.MAX_SOURCE-out.size())throw new IOException("Artwork exceeds its limit.");out.write(chunk,0,count);}}check();return out.toByteArray();}finally{connection.disconnect();}
 }
 JSONObject json(String route,int max)throws Exception{ByteArrayOutputStream bytes=new ByteArrayOutputStream();transfer(route,bytes,max);try{return new JSONObject(bytes.toString("UTF-8"));}catch(JSONException e){throw new IOException("RomM returned an invalid response.");}}
 void transfer(String route,OutputStream output,int max)throws Exception {
  check();if(!route.startsWith("/api/")||route.contains("\r")||route.contains("\n"))throw new IOException("Invalid library request.");
  HttpURLConnection connection=(HttpURLConnection)new URL(base+route).openConnection();connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(5000);connection.setReadTimeout(5000);connection.setRequestProperty("Cookie",cookie);connection.setRequestProperty("Accept","application/json, application/octet-stream");connection.setRequestProperty("Accept-Encoding","identity");long end=System.nanoTime()+30_000_000_000L;
  try{int code=connection.getResponseCode();if(code==401||code==403)throw new IOException("RomM login expired or does not allow this action. Reconnect the host.");if(code>=300&&code<400)throw new IOException("RomM redirected the request. Configure its final server address.");if(code!=200)throw new IOException("RomM could not complete this request (HTTP "+code+").");if(connection.getContentLengthLong()>max)throw new IOException("This response exceeds the preview's size limit.");int total=0;try(InputStream in=connection.getInputStream()){byte[] chunk=new byte[65536];int n;while((n=in.read(chunk))!=-1){check();if(System.nanoTime()>end)throw new IOException("RomM request timed out.");if(n>max-total)throw new IOException("This response exceeds the preview's size limit.");output.write(chunk,0,n);total+=n;}}}catch(InterruptedIOException e){throw e;}catch(IOException e){throw new IOException("RomM request failed. Check the host connection and login.");}finally{connection.disconnect();}
 }
 static byte[] readBounded(File file,int max)throws IOException{if(file.length()>max)throw new IOException("Private metadata exceeds its size limit.");try(InputStream in=new FileInputStream(file);ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1){if(out.size()+n>max)throw new IOException("Private metadata exceeds its size limit.");out.write(b,0,n);}return out.toByteArray();}}
 static String verifyGame(File file)throws Exception {if(file.length()<16||file.length()>MAX_ROM)throw new IOException("Invalid NES game size.");MessageDigest hash=MessageDigest.getInstance("SHA-256");try(InputStream in=new FileInputStream(file)){byte[] b=new byte[65536];int n=in.read(b);if(n<16||b[0]!='N'||b[1]!='E'||b[2]!='S'||b[3]!=0x1a)throw new IOException("This file is not a supported NES game.");hash.update(b,0,n);while((n=in.read(b))!=-1)hash.update(b,0,n);}return hex(hash.digest());}
 static String hex(byte[] bytes){StringBuilder s=new StringBuilder();for(byte b:bytes)s.append(String.format(Locale.ROOT,"%02x",b&255));return s.toString();}
 static void privateFile(File f){f.setReadable(false,false);f.setWritable(false,false);f.setReadable(true,true);f.setWritable(true,true);}
 static void atomicMove(File from,File to)throws IOException{Files.move(from.toPath(),to.toPath(),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}
 static void atomicBytes(File dest,byte[] bytes)throws Exception{File temp=File.createTempFile("recent-",".tmp",dest.getParentFile());privateFile(temp);try{try(FileOutputStream out=new FileOutputStream(temp)){out.write(bytes);out.getFD().sync();}atomicMove(temp,dest);}finally{temp.delete();}}
}
