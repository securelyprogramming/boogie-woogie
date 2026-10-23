package com.emulatormayo.boogie;

/** Editing/focus transitions require a real neutral report before admitting held input. */
final class ControllerInputGate {
 private boolean editing,neutralRequired=true,lastPhysicalNeutral;
 void editing(boolean value){editing=value;neutralRequired=value||!lastPhysicalNeutral;}
 void release(){neutralRequired=true;lastPhysicalNeutral=false;}
 float[] filter(float[] raw,boolean physicalSample){if(physicalSample){lastPhysicalNeutral=ControllerMapping.neutral(raw);if(!editing&&lastPhysicalNeutral)neutralRequired=false;}return editing||neutralRequired?new float[ControllerMapping.COUNT]:raw;}
}
