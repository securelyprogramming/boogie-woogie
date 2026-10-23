package com.emulatormayo.boogie;

/** Bounded digital/analog direction mapping, independent of Android UI and emulator ports. */
final class ControllerMapping {
 static final int COUNT=25;
 static final String[] NAMES={"A","B","X","Y","Left shoulder","Right shoulder","Left trigger","Right trigger","Select / View","Start / Menu","Left stick click","Right stick click","D-pad up","D-pad down","D-pad left","D-pad right","Guide","Left stick left","Left stick right","Left stick up","Left stick down","Right stick left","Right stick right","Right stick up","Right stick down"};
 final int[] sources;
 ControllerMapping(int[] values){if(values==null||values.length!=COUNT)throw new IllegalArgumentException("Mapping size");sources=values.clone();for(int value:sources)if(value< -1||value>=COUNT)throw new IllegalArgumentException("Mapping source");}
 static ControllerMapping defaults(){int[] s=new int[COUNT];for(int i=0;i<COUNT;i++)s[i]=i;return new ControllerMapping(s);}
 ControllerMapping copy(){return new ControllerMapping(sources);}
 void bind(int target,int source){if(target<0||target>=COUNT||source< -1||source>=COUNT)throw new IllegalArgumentException();sources[target]=source;}
 void invert(int axis){if(axis<0||axis>3)throw new IllegalArgumentException();int a=17+axis*2,t=sources[a];sources[a]=sources[a+1];sources[a+1]=t;}
 static float[] flatten(float[] buttons,float[] axes){float[] out=new float[COUNT];for(int i=0;i<17;i++)out[i]=bound(buttons[i]);for(int i=0;i<4;i++){out[17+i*2]=bound(-axes[i]);out[18+i*2]=bound(axes[i]);}return out;}
 float[] apply(float[] raw){if(raw==null||raw.length!=COUNT)throw new IllegalArgumentException();float[] out=new float[COUNT];for(int i=0;i<COUNT;i++)out[i]=sources[i]<0?0:bound(raw[sources[i]]);return out;}
 static boolean neutral(float[] values){for(float value:values)if(bound(value)>.2f)return false;return true;}
 static int capture(float[] values){int found=-1;float best=.6f;for(int i=0;i<COUNT;i++)if(bound(values[i])>best){found=i;best=bound(values[i]);}return found;}
 static float bound(float f){return Float.isFinite(f)?Math.max(0,Math.min(1,f)):0;}
}
