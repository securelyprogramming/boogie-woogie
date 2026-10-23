package com.emulatormayo.boogie;

import java.util.LinkedHashSet;

/** Native defence in depth after the authenticated data-channel validation. */
final class MappingSetupGate {
 private final LinkedHashSet<String> seen=new LinkedHashSet<>();
 private long last=-1;
 boolean accept(String requestId,String role,int port,String game,String expectedRole,int expectedPort,String expectedGame,long now){
  if(requestId==null||!requestId.matches("[a-f0-9]{32}")||game==null||!game.matches("sha256:[a-f0-9]{64}")||!game.equals(expectedGame)||role==null||!role.equals(expectedRole)||port!=expectedPort||!(role.equals("player")&&port==0||role.equals("player2")&&port==1)||now<0||seen.contains(requestId)||last>=0&&now-last<2000)return false;
  seen.add(requestId);while(seen.size()>32)seen.remove(seen.iterator().next());last=now;return true;
 }
 void clear(){seen.clear();last=-1;}
}
