package com.emulatormayo.boogie;

import android.app.*;
import android.graphics.Color;
import android.view.View;
import android.widget.*;

/** Guided capture is native; edits cannot inject emulator gameplay or alter app menu controls. */
final class ControllerEditor {
 static AlertDialog show(Activity activity,PlayerController controls,boolean gameKnown){return show(activity,controls,gameKnown,"This player",false,null,()->{});}
 static AlertDialog show(Activity activity,PlayerController controls,boolean gameKnown,String playerLabel,boolean hostRequested,Runnable setupAll,Runnable dismissed){
  if(controls==null)return null;
  if(!controls.hasDevice()){AlertDialog.Builder builder=new AlertDialog.Builder(activity).setTitle("Edit joystick · "+playerLabel+" · "+android.os.Build.MODEL).setMessage((hostRequested?"Host requested setup for "+playerLabel+".\n\n":"")+"Connect a physical controller to map its inputs. Touch controls can still be arranged with Edit layout. Each device keeps its own bindings.").setNegativeButton("Cancel",null);if(setupAll!=null)builder.setNeutralButton("Set up all players",(d,w)->setupAll.run());AlertDialog empty=builder.create();controls.editing(true,null);empty.setOnDismissListener(d->{controls.editing(false,null);dismissed.run();});empty.show();return empty;}

  ControllerMapping draft=controls.profile();final String editingDevice=controls.deviceKey();
  LinearLayout box=new LinearLayout(activity);box.setOrientation(android.widget.LinearLayout.VERTICAL);box.setPadding(24,12,24,12);
  TextView device=new TextView(activity);device.setText(playerLabel+" · "+controls.deviceLabel()+"\n"+controls.deviceCount()+" physical controller"+(controls.deviceCount()==1?"":"s")+" connected · editing this device only");device.setTextSize(16);device.setTextColor(0xffc5ffdc);device.setPadding(0,0,0,12);box.addView(device);
  TextView status=new TextView(activity);status.setText((hostRequested?"Host requested setup. ":"")+"Choose an action, release all controls, then press a button or move a direction. Changes affect only this controller's gameplay. Cancel keeps your current bindings. Existing game overrides take priority over defaults.");box.addView(status);
  if(setupAll!=null){Button players=new Button(activity);players.setAllCaps(false);players.setText("Set up all players · ask each device to map its own controller");players.setOnClickListener(v->setupAll.run());box.addView(players);}

  final int[] target={-1};final boolean[] neutral={false};
  ScrollView scroll=new ScrollView(activity);LinearLayout rows=new LinearLayout(activity);rows.setOrientation(android.widget.LinearLayout.VERTICAL);scroll.addView(rows);box.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
  Button[] actions=new Button[ControllerMapping.COUNT];
  Runnable refresh=()->{for(int i=0;i<actions.length;i++)if(actions[i]!=null)actions[i].setText(ControllerMapping.NAMES[i]+"  ←  "+(draft.sources[i]<0?"Unassigned":ControllerMapping.NAMES[draft.sources[i]]));};
  for(int i=0;i<actions.length;i++){final int index=i;Button b=new Button(activity);b.setAllCaps(false);b.setOnClickListener(v->{target[0]=index;neutral[0]=controls.neutral();status.setText("Binding "+ControllerMapping.NAMES[index]+": release all controls, then press/move the desired control.");});rows.addView(b);actions[i]=b;}
  LinearLayout inversions=new LinearLayout(activity);for(int i=0;i<4;i++){final int axis=i;Button b=new Button(activity);b.setAllCaps(false);b.setText("Invert "+new String[]{"L X","L Y","R X","R Y"}[i]);b.setOnClickListener(v->{target[0]=-1;draft.invert(axis);refresh.run();status.setText("Axis inverted in preview. Save to apply.");});inversions.addView(b,new LinearLayout.LayoutParams(0,-2,1));}box.addView(inversions);
  LinearLayout save=new LinearLayout(activity);Button game=new Button(activity),all=new Button(activity);game.setText("This device + game");all.setText("Device default · all games");game.setAllCaps(false);all.setAllCaps(false);game.setEnabled(gameKnown);save.addView(game,new LinearLayout.LayoutParams(0,-2,1));save.addView(all,new LinearLayout.LayoutParams(0,-2,1));box.addView(save);
  AlertDialog dialog=new AlertDialog.Builder(activity).setTitle((hostRequested?"Host requested setup · ":"Edit joystick · ")+playerLabel).setView(box).setNegativeButton("Cancel",null).setNeutralButton("Reset preview",null).create();
  game.setOnClickListener(v->{target[0]=-1;if(!editingDevice.equals(controls.deviceKey())){status.setText("Controller changed. Cancel and reopen Edit joystick.");return;}if(controls.save(draft,true))dialog.dismiss();else status.setText("Unable to save. No bindings changed.");});
  all.setOnClickListener(v->{target[0]=-1;if(!editingDevice.equals(controls.deviceKey())){status.setText("Controller changed. Cancel and reopen Edit joystick.");return;}if(controls.save(draft,false)){Toast.makeText(activity,"Default saved. Existing game overrides still take priority.",Toast.LENGTH_LONG).show();dialog.dismiss();}else status.setText("Unable to save. No bindings changed.");});
  controls.editing(true,values->{if(target[0]<0)return;if(ControllerMapping.neutral(values)){neutral[0]=true;return;}if(!neutral[0])return;int source=ControllerMapping.capture(values);if(source>=0){draft.bind(target[0],source);target[0]=-1;neutral[0]=false;refresh.run();status.setText("Binding captured. Choose another action, or save. Release controls before closing.");}});
  dialog.setOnDismissListener(d->{controls.editing(false,null);dismissed.run();});dialog.show();dialog.getWindow().setLayout(-1,(int)(activity.getResources().getDisplayMetrics().heightPixels*.9));dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v->{target[0]=-1;System.arraycopy(ControllerMapping.defaults().sources,0,draft.sources,0,ControllerMapping.COUNT);refresh.run();status.setText("Factory bindings in preview. Save to apply, or Cancel to keep existing bindings.");});refresh.run();return dialog;
 }
}
