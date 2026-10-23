package com.emulatormayo.boogie;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.Base64;
import java.io.*;
import java.util.*;
import java.util.function.BooleanSupplier;

/** Host-only authenticated cover loader. Only a small re-encoded JPEG reaches the player. */
final class HostArtwork {
 // Keep base64 + authenticated metadata below SCTP's common 65,536-byte message limit.
 static final int TARGET_JPEG=48000;
 /** Account-bound chooser thumbnail; its synthetic cache key is never a playable game identity. */
 static Bitmap preview(File files,int romId,String account,BooleanSupplier cancelled)throws Exception {
  String key=HostRommLibrary.hex(java.security.MessageDigest.getInstance("SHA-256").digest(("chooser-cover:"+romId).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
  Result result=load(files,romId,account,"sha256:"+key,cancelled);return result==null?null:result.bitmap;
 }
 static final class Result {
  final String gameKey;final byte[] jpeg;final Bitmap bitmap;
  Result(String key,byte[] bytes,Bitmap image){gameKey=key;jpeg=bytes;bitmap=image;}
  String dataUrl(){return "data:image/jpeg;base64,"+Base64.encodeToString(jpeg,Base64.NO_WRAP);}
 }
 static Result load(File files,int romId,String account,String gameKey,BooleanSupplier cancelled)throws Exception {
  if(romId<1||account==null||!account.matches("[a-f0-9]{64}")||!ControllerProfiles.game(gameKey))throw new IOException("Invalid artwork identity.");
  long deadline=System.nanoTime()+20_000_000_000L;BooleanSupplier stop=()->cancelled.getAsBoolean()||System.nanoTime()>deadline;
  HostRommLibrary service=new HostRommLibrary(files,stop);if(!service.verify().equals(account))throw new IOException("Artwork account changed.");
  File folder=new File(files,"artwork-thumbnails");if(!folder.isDirectory()&&!folder.mkdirs())throw new IOException("Artwork cache unavailable.");File cache=new File(folder,account+"-"+gameKey.substring(7)+".jpg");
  if(cache.isFile()&&System.currentTimeMillis()-cache.lastModified()<24*60*60*1000L){try{byte[] bytes=HostRommLibrary.readBounded(cache,TARGET_JPEG);return canonical(gameKey,bytes);}catch(Exception ignored){cache.delete();}}
  if(stop.getAsBoolean())return null;byte[] source=service.artwork(romId,account);if(source==null||stop.getAsBoolean())return null;
  BitmapFactory.Options bounds=new BitmapFactory.Options();bounds.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(source,0,source.length,bounds);
  if(bounds.outWidth<1||bounds.outHeight<1||bounds.outWidth>4096||bounds.outHeight>4096||(long)bounds.outWidth*bounds.outHeight>16_777_216L||!Arrays.asList("image/jpeg","image/png","image/webp").contains(bounds.outMimeType))throw new IOException("Artwork exceeds decode bounds.");
  BitmapFactory.Options options=new BitmapFactory.Options();options.inPreferredConfig=Bitmap.Config.ARGB_8888;options.inSampleSize=1;while(bounds.outWidth/options.inSampleSize>640||bounds.outHeight/options.inSampleSize>640)options.inSampleSize*=2;
  Bitmap decoded=BitmapFactory.decodeByteArray(source,0,source.length,options);if(decoded==null)throw new IOException("Artwork could not be decoded safely.");if(decoded.getWidth()>640||decoded.getHeight()>640){decoded.recycle();throw new IOException("Artwork could not be decoded safely.");}
  Bitmap scaled=null;byte[] jpeg=null;
  try{int edge=320;while(edge>=160&&jpeg==null){float ratio=Math.min(1f,edge/(float)Math.max(decoded.getWidth(),decoded.getHeight()));int width=Math.max(1,Math.round(decoded.getWidth()*ratio)),height=Math.max(1,Math.round(decoded.getHeight()*ratio));scaled=Bitmap.createScaledBitmap(decoded,width,height,true);for(int quality:new int[]{85,70,55,40,25}){ByteArrayOutputStream out=new ByteArrayOutputStream();if(!scaled.compress(Bitmap.CompressFormat.JPEG,quality,out))throw new IOException("Artwork compression failed.");if(out.size()<=TARGET_JPEG){jpeg=out.toByteArray();break;}}if(scaled!=decoded)scaled.recycle();scaled=null;edge-=64;}}
  finally{if(scaled!=null&&scaled!=decoded)scaled.recycle();decoded.recycle();}
  if(jpeg==null||stop.getAsBoolean())return null;Result result=canonical(gameKey,jpeg);HostRommLibrary.atomicBytes(cache,jpeg);trim(folder);return result;
 }
 private static Result canonical(String key,byte[] jpeg)throws IOException {int[] size=ArtworkPolicy.jpegDimensions(jpeg);BitmapFactory.Options bounds=new BitmapFactory.Options();bounds.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(jpeg,0,jpeg.length,bounds);if(!"image/jpeg".equals(bounds.outMimeType)||bounds.outWidth!=size[0]||bounds.outHeight!=size[1])throw new IOException("Invalid thumbnail.");Bitmap bitmap=BitmapFactory.decodeByteArray(jpeg,0,jpeg.length);if(bitmap==null)throw new IOException("Invalid thumbnail.");if(bitmap.getWidth()!=size[0]||bitmap.getHeight()!=size[1]){bitmap.recycle();throw new IOException("Invalid thumbnail.");}return new Result(key,jpeg,bitmap);}
 private static void trim(File folder){File[] images=folder.listFiles((dir,name)->name.matches("[a-f0-9]{64}-[a-f0-9]{64}\\.jpg"));if(images==null||images.length<=64)return;Arrays.sort(images,Comparator.comparingLong(File::lastModified));for(int i=0;i<images.length-64;i++)images[i].delete();}
}
