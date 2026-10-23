package com.emulatormayo.boogie;

import java.io.IOException;
import java.net.URI;
import java.net.URLDecoder;
import java.util.Locale;

/** Only same-origin RomM resource covers and bounded canonical JPEG derivatives. */
final class ArtworkPolicy {
 static final int MAX_JPEG=49152,MAX_EDGE=320,MAX_SOURCE=2*1024*1024;
 static String route(String base,String source)throws IOException {
  try {
   if(source==null||source.isEmpty()||source.length()>2048||source.chars().anyMatch(c->c<32||c==127))throw new IOException();
   URI origin=new URI(base),uri=new URI(source.replace(" ","%20"));
   if(uri.getRawUserInfo()!=null||uri.getRawFragment()!=null)throw new IOException();
   if(uri.isAbsolute()||uri.getRawAuthority()!=null){if(!origin.getScheme().equals(uri.getScheme())||!origin.getHost().equalsIgnoreCase(uri.getHost()==null?"":uri.getHost())||port(origin)!=port(uri))throw new IOException();}
   String path=uri.getRawPath(),query=uri.getRawQuery();
   if(path==null||!path.startsWith("/assets/romm/resources/roms/")&&!path.startsWith("/assets/romm/resources/platforms/"))throw new IOException();
   String decoded=URLDecoder.decode(path.replace("+","%2B"),"UTF-8");
   if(decoded.contains("%")||decoded.contains("\\")||decoded.chars().anyMatch(c->c<32||c==127))throw new IOException();
   for(String part:decoded.split("/",-1))if(part.equals(".")||part.equals(".."))throw new IOException();
   if(!decoded.toLowerCase(Locale.ROOT).matches(".*\\.(png|jpe?g|webp)$")||query!=null&&!query.matches("[A-Za-z0-9=&%:+,/_\\-.]*"))throw new IOException();
   return path+(query==null?"":"?"+query);
  }catch(Exception failure){throw new IOException("Artwork is not a supported resource on the configured RomM server.");}
 }
 private static int port(URI uri){return uri.getPort()!=-1?uri.getPort():"https".equals(uri.getScheme())?443:80;}
 static int[] jpegDimensions(byte[] bytes)throws IOException {
  if(bytes==null||bytes.length<12||bytes.length>MAX_JPEG||(bytes[0]&255)!=255||(bytes[1]&255)!=216||(bytes[bytes.length-2]&255)!=255||(bytes[bytes.length-1]&255)!=217)throw new IOException("Invalid thumbnail.");
  int at=2;
  while(at<bytes.length-2){if((bytes[at++]&255)!=255)throw new IOException("Invalid thumbnail.");while(at<bytes.length&&(bytes[at]&255)==255)at++;if(at>=bytes.length)break;int marker=bytes[at++]&255;if(marker==218||marker==217)break;if(marker==1||marker>=208&&marker<=215)continue;if(at+2>bytes.length)break;int length=(bytes[at]&255)*256+(bytes[at+1]&255);if(length<2||at+length>bytes.length)break;if(marker==192||marker==194){if(length<8||(bytes[at+2]&255)!=8)break;int height=(bytes[at+3]&255)*256+(bytes[at+4]&255),width=(bytes[at+5]&255)*256+(bytes[at+6]&255);if(width<1||height<1||width>MAX_EDGE||height>MAX_EDGE)break;return new int[]{width,height};}at+=length;}
  throw new IOException("Invalid thumbnail dimensions.");
 }
}
