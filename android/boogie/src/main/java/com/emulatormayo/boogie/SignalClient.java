package com.emulatormayo.boogie;

import org.json.*;
import javax.net.ssl.*;
import java.security.*;
import java.security.cert.*;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;

/** Prototype-only HTTPS transport. Trust is bound to the paired certificate, not global Android TLS. */
final class SignalClient {
 final String base; final SSLSocketFactory sockets;
 volatile String credential;
 SignalClient(JSONObject config, boolean host) throws Exception {
  base=config.getString("baseUrl"); URI uri=new URI(base);
  if(!"https".equals(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null||uri.getQuery()!=null||uri.getFragment()!=null||!(uri.getPath().isEmpty()||uri.getPath().equals("/")))throw new IOException("Invalid paired broker address");
  final String expected=config.getString("certificateSha256");
  if(!expected.matches("[a-f0-9]{64}"))throw new IOException("Invalid certificate pin");
  TrustManager[] trust={new X509TrustManager(){
   public X509Certificate[] getAcceptedIssuers(){return new X509Certificate[0];}
   public void checkClientTrusted(X509Certificate[] chain,String auth)throws CertificateException{throw new CertificateException("Client trust unsupported");}
   public void checkServerTrusted(X509Certificate[] chain,String auth)throws CertificateException{
    try{if(chain==null||chain.length!=1)throw new CertificateException("Unexpected paired chain");chain[0].checkValidity();StringBuilder hash=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded()))hash.append(String.format("%02x",b&255));if(!MessageDigest.isEqual(hash.toString().getBytes(StandardCharsets.US_ASCII),expected.getBytes(StandardCharsets.US_ASCII)))throw new CertificateException("Paired certificate changed");}
    catch(CertificateException e){throw e;}catch(Exception e){throw new CertificateException("Could not validate paired certificate");}
   }}};
  SSLContext context=SSLContext.getInstance("TLS");context.init(null,trust,new SecureRandom());sockets=context.getSocketFactory();
  credential=host?config.getString("hostCredential"):"";
 }
 JSONObject call(String route,JSONObject data)throws Exception{return call(route,data,credential);}
 JSONObject call(String route,JSONObject data,String authCredential)throws Exception{
  if(!route.matches("/(join|approve|signal|leave|stop|reset|events)(\\?[a-zA-Z0-9=&.]+)?"))throw new IOException("Unsupported broker route");
  HttpsURLConnection c=(HttpsURLConnection)new URL(base+route).openConnection();c.setSSLSocketFactory(sockets);c.setInstanceFollowRedirects(false);c.setConnectTimeout(5000);c.setReadTimeout(8000);
  // Certificate pin is the explicit pairing identity. This verifier is scoped
  // to this one connection; SAN is checked normally and never globally bypassed.
  if(!authCredential.isEmpty())c.setRequestProperty("Authorization","Bearer "+authCredential);
  if(data!=null){byte[] body=data.toString().getBytes(StandardCharsets.UTF_8);if(body.length>73728)throw new IOException("Signal too large");c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");c.setFixedLengthStreamingMode(body.length);try(OutputStream out=c.getOutputStream()){out.write(body);}}
  try{int status=c.getResponseCode();InputStream stream=status==200?c.getInputStream():c.getErrorStream();ByteArrayOutputStream out=new ByteArrayOutputStream();if(stream!=null)try(InputStream in=stream){byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1){out.write(b,0,n);if(out.size()>262144)throw new IOException("Broker response too large");}}
   JSONObject result=new JSONObject(out.toString("UTF-8"));if(status!=200)throw new IOException("Broker "+status+": "+result.optString("error","request failed"));return result;
  }finally{c.disconnect();}
 }
}
