package com.emulatormayo.boogie;

import android.app.*;
import android.os.*;
import android.graphics.*;
import android.graphics.drawable.*;
import android.text.TextWatcher;
import android.text.Editable;
import android.text.InputFilter;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;

/** Native host-only chooser, usable before a WebView or multiplayer room exists. */
public final class NativeGameLibrary implements AutoCloseable {
 public interface Callback {void selected(Selection selection);}
 public static final class Selection {
  public final int romId;public final String title,gameKey,accountKey,mode,slotId;public final File cachedGame;
  private final HostRommLibrary.Prepared prepared;
  Selection(HostRommLibrary.Prepared p,String mode,String slot){prepared=p;romId=p.game.romId;title=p.game.title;gameKey=p.gameKey;accountKey=p.accountKey;cachedGame=p.cachedGame;this.mode=mode;slotId=slot;}
  Selection with(String mode,String slot){return new Selection(prepared,mode,slot);}
 }
 private final Activity activity;private final File files;private final Handler main=new Handler(Looper.getMainLooper());
 private final ExecutorService executor=Executors.newSingleThreadExecutor();private final Object lifecycle=new Object();
 private int generation;private boolean closed;private Future<?> task;private AlertDialog dialog;
 private boolean recent=true;private int offset;private String query="";private Callback selected;
 private LinearLayout rows;private TextView status;private Button previous,next,platformButton,recentButton,allButton,viewButton;private EditText search;
 private boolean cardView;private List<HostRommLibrary.Game> shownGames=new ArrayList<>();private String shownAccount="";private int shownRevision;
 private HostRommLibrary.Platform platform;private List<HostRommLibrary.Platform> platforms=new ArrayList<>();private AlertDialog platformDialog;private ScrollView results;
 private final ThreadPoolExecutor previews=(ThreadPoolExecutor)Executors.newFixedThreadPool(2);private final List<Future<?>> previewTasks=new ArrayList<>();
 private final android.util.LruCache<String,Bitmap> covers=new android.util.LruCache<String,Bitmap>(4*1024*1024){protected int sizeOf(String key,Bitmap image){return image.getAllocationByteCount();}};
 public NativeGameLibrary(Activity activity,File files){this.activity=activity;this.files=files;cardView=activity.getPreferences(0).getBoolean("gamePickerCards",false);}
 public Selection current(){HostRommLibrary.Prepared p=HostRommLibrary.current(files);return p==null?null:new Selection(p,"resume",null);}
 private boolean live(int revision){synchronized(lifecycle){return !closed&&generation==revision;}}
 private boolean usable(){return !activity.isFinishing()&&!activity.isDestroyed();}
 private int begin(){synchronized(lifecycle){if(closed)return -1;generation++;if(task!=null)task.cancel(true);cancelPreviews();return generation;}}
 private void post(int revision,Runnable run){main.post(()->{if(live(revision)&&usable())run.run();});}
 // Each operation gets a fresh cancellation predicate; it also re-verifies /me.
 private HostRommLibrary connection(int revision)throws Exception {return new HostRommLibrary(files,()->!live(revision));}
 private void dismiss(){if(platformDialog!=null){platformDialog.dismiss();platformDialog=null;}if(dialog!=null){dialog.setOnDismissListener(null);dialog.dismiss();dialog=null;}}
 /** Lobby shortcuts: one click selects Resume; Start multiplayer remains the caller's action. */
 public void showRecentRows(LinearLayout parent,Callback callback){
  if(closed||!usable())return;cancelOperations();int revision=begin();if(revision<0)return;
  parent.removeAllViews();inlineStatus(parent,"Loading recent games from your library…");
  task=executor.submit(()->{try{
   HostRommLibrary.Page page=connection(revision).list("",true,0);List<HostRommLibrary.Game> available=new ArrayList<>();
   for(HostRommLibrary.Game game:page.games)if(game.supported){available.add(game);if(available.size()==5)break;}
   post(revision,()->{if(!parent.isAttachedToWindow())return;parent.removeAllViews();
    if(available.isEmpty()){inlineStatus(parent,"No recent NES games yet. Use Choose game to search your game library.");return;}
    inlineStatus(parent,"Recent games · select to resume the latest save");
    for(HostRommLibrary.Game game:available){Button row=button(game.title+"\nResume latest save",()->prepareInline(parent,game,callback));row.setTextColor(0xffeffff4);row.setBackgroundTintList(new android.content.res.ColorStateList(new int[][]{new int[]{android.R.attr.state_focused},new int[]{android.R.attr.state_pressed},new int[]{}},new int[]{0xff2c7950,0xff2c7950,0xff174a34}));row.setMinHeight(dp(52));LinearLayout.LayoutParams rowLayout=new LinearLayout.LayoutParams(Math.min(dp(460),activity.getResources().getDisplayMetrics().widthPixels-dp(48)),-2);rowLayout.gravity=Gravity.CENTER_HORIZONTAL;rowLayout.topMargin=dp(4);rowLayout.bottomMargin=dp(4);parent.addView(row,rowLayout);}
   });
  }catch(Exception error){post(revision,()->{if(!parent.isAttachedToWindow())return;parent.removeAllViews();inlineStatus(parent,"Recent games unavailable. Check the host's game source and connection.");parent.addView(button("Retry recent games",()->showRecentRows(parent,callback)));});}});
 }
 private void prepareInline(LinearLayout parent,HostRommLibrary.Game game,Callback callback){
  if(!parent.isAttachedToWindow())return;int revision=begin();if(revision<0)return;parent.removeAllViews();inlineStatus(parent,"Preparing "+game.title+"…");
  task=executor.submit(()->{try{HostRommLibrary.Prepared prepared=connection(revision).download(game);post(revision,()->{if(parent.isAttachedToWindow())callback.selected(new Selection(prepared,"resume",null));});}
   catch(Exception error){post(revision,()->{if(!parent.isAttachedToWindow())return;parent.removeAllViews();inlineStatus(parent,"Could not prepare this NES game. Check RomM access and available storage.");parent.addView(button("Back to recent games",()->showRecentRows(parent,callback)));});}});
 }
 private void inlineStatus(LinearLayout parent,String message){TextView label=new TextView(activity);label.setText(message);label.setTextColor(0xffa6c9b4);label.setPadding(dp(8),dp(6),dp(8),dp(6));parent.addView(label,new LinearLayout.LayoutParams(-1,-2));}
 public void show(Callback callback){
  if(closed||!usable())return;cancelOperations();selected=callback;recent=true;offset=0;query="";platform=null;platforms=new ArrayList<>();
  LinearLayout content=new LinearLayout(activity);content.setOrientation(android.widget.LinearLayout.VERTICAL);content.setPadding(dp(16),dp(8),dp(16),dp(6));
  LinearLayout filters=new LinearLayout(activity);filters.setGravity(Gravity.CENTER_VERTICAL);
  recentButton=button("Recent",()->{recent=true;offset=0;query="";search.setText("");load();});allButton=button("All games",()->{recent=false;offset=0;query=search.getText().toString();load();});
  filters.addView(recentButton,new LinearLayout.LayoutParams(dp(108),dp(44)));LinearLayout.LayoutParams tab=new LinearLayout.LayoutParams(dp(108),dp(44));tab.leftMargin=dp(8);filters.addView(allButton,tab);
  platformButton=button("All platforms ▾",this::choosePlatform);platformButton.setEnabled(false);LinearLayout.LayoutParams platformLayout=new LinearLayout.LayoutParams(0,dp(44),1);platformLayout.leftMargin=dp(16);platformButton.setMaxLines(1);platformButton.setEllipsize(android.text.TextUtils.TruncateAt.END);filters.addView(platformButton,platformLayout);viewButton=button(cardView?"☷ Table":"▦ Cards",()->{cardView=!cardView;activity.getPreferences(0).edit().putBoolean("gamePickerCards",cardView).apply();viewButton.setText(cardView?"☷ Table":"▦ Cards");renderGames();});LinearLayout.LayoutParams viewLayout=new LinearLayout.LayoutParams(dp(100),dp(44));viewLayout.leftMargin=dp(8);filters.addView(viewButton,viewLayout);content.addView(filters);
  LinearLayout searchRow=new LinearLayout(activity);searchRow.setPadding(0,dp(6),0,dp(4));search=new EditText(activity);search.setSingleLine();search.setTextColor(0xffeffff4);search.setHintTextColor(0xffa6c9b4);search.setHint("Search game titles…");search.setContentDescription("Search game titles");search.setTextSize(16);search.setFilters(new InputFilter[]{new InputFilter.LengthFilter(200)});search.setImeOptions(android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH);searchRow.addView(search,new LinearLayout.LayoutParams(0,dp(44),1));Button find=button("Search",()->{recent=false;offset=0;query=search.getText().toString();hideKeyboard();load();});LinearLayout.LayoutParams findLayout=new LinearLayout.LayoutParams(dp(100),dp(44));findLayout.leftMargin=dp(8);searchRow.addView(find,findLayout);search.setOnEditorActionListener((v,action,event)->{if(action==android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH){find.performClick();return true;}return false;});content.addView(searchRow);
  status=label("Loading your library…",12,0xffb2d3c0);status.setPadding(0,0,0,dp(5));status.setMaxLines(1);status.setEllipsize(android.text.TextUtils.TruncateAt.END);content.addView(status);
  results=new ScrollView(activity);results.setClipToPadding(false);rows=new LinearLayout(activity);rows.setOrientation(android.widget.LinearLayout.VERTICAL);results.addView(rows);content.addView(results,new LinearLayout.LayoutParams(-1,0,1));
  LinearLayout pages=new LinearLayout(activity);pages.setGravity(Gravity.CENTER);pages.setPadding(0,dp(6),0,0);previous=button("‹ Previous",()->{offset=Math.max(0,offset-HostRommLibrary.PAGE_SIZE);load();});next=button("Next ›",()->{offset+=HostRommLibrary.PAGE_SIZE;load();});pages.addView(previous,new LinearLayout.LayoutParams(dp(130),dp(44)));LinearLayout.LayoutParams nextLayout=new LinearLayout.LayoutParams(dp(130),dp(44));nextLayout.leftMargin=dp(12);pages.addView(next,nextLayout);content.addView(pages);
  dialog=new AlertDialog.Builder(activity).setTitle("Choose your next game").setView(content).setNegativeButton("Cancel",null).create();dialog.setOnDismissListener(d->cancelOperations());bindController(dialog);dialog.show();style(dialog);dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN|WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);dialog.getWindow().setLayout(Math.min(dp(1000),Math.round(activity.getResources().getDisplayMetrics().widthPixels*.94f)),Math.round(activity.getResources().getDisplayMetrics().heightPixels*.95f));load();
 }
 private void load(){
  int revision=begin();if(revision<0)return;String q=query;boolean r=recent;int page=offset;HostRommLibrary.Platform filter=platform;shownGames=new ArrayList<>();shownAccount="";viewButton.setEnabled(false);rows.removeAllViews();results.scrollTo(0,0);status.setText("Loading your game library…");previous.setEnabled(false);next.setEnabled(false);recentButton.setSelected(r);allButton.setSelected(!r);
  task=executor.submit(()->{try{HostRommLibrary service=connection(revision);List<HostRommLibrary.Platform> choices=platforms;if(choices.isEmpty())try{choices=service.platforms();}catch(Exception ignored){}HostRommLibrary.Page result=service.list(q,r,page,filter);String account=service.verify();List<HostRommLibrary.Platform> loaded=choices;
   post(revision,()->{shownGames=new ArrayList<>(result.games);shownAccount=account;shownRevision=revision;viewButton.setEnabled(true);platforms=loaded;platformButton.setEnabled(true);platformButton.setText(filter==null?"All platforms ▾":filter.name+" ▾");status.setText((r?"RECENT":"LIBRARY")+"  ·  "+(filter==null?"All platforms":filter.name)+"  ·  "+result.games.size()+" games · NES gameplay preview");previous.setEnabled(page>0);next.setEnabled(result.hasNext);if(result.games.isEmpty()){TextView empty=label("No games found. Try another title or platform.",17,0xffd6f8e3);empty.setPadding(dp(12),dp(20),dp(12),dp(20));rows.addView(empty);}if(!result.games.isEmpty())renderGames();});
  }catch(Exception e){post(revision,()->{status.setText("Could not load RomM. Check the host connection, then retry Search.");previous.setEnabled(page>0);platformButton.setEnabled(true);});}});
 }
 private void renderGames(){
  cancelPreviews();rows.removeAllViews();results.scrollTo(0,0);if(shownGames.isEmpty()){TextView empty=label("No games found. Try another title or platform.",17,0xffd6f8e3);empty.setPadding(dp(12),dp(20),dp(12),dp(20));rows.addView(empty);return;}
  int columns=cardView?2:1;
  for(int start=0;start<shownGames.size();start+=columns){LinearLayout line=new LinearLayout(activity);line.setOrientation(android.widget.LinearLayout.HORIZONTAL);rows.addView(line,new LinearLayout.LayoutParams(-1,-2));for(int col=0;col<columns;col++){int index=start+col;LinearLayout.LayoutParams cell=new LinearLayout.LayoutParams(0,-2,1);cell.bottomMargin=dp(6);if(col>0)cell.leftMargin=dp(8);if(index<shownGames.size())line.addView(gameCard(shownGames.get(index),shownAccount,shownRevision),cell);else line.addView(new View(activity),cell);}}
 }
 private View gameCard(HostRommLibrary.Game game,String account,int revision){
  LinearLayout card=new LinearLayout(activity);card.setOrientation(cardView?LinearLayout.VERTICAL:LinearLayout.HORIZONTAL);card.setGravity(Gravity.CENTER_VERTICAL);card.setPadding(dp(8),dp(6),dp(10),dp(6));card.setBackground(surface());card.setFocusable(true);card.setClickable(true);card.setContentDescription(game.title+", "+game.platform+(game.supported?", resume latest save":", browse only, NES preview"));
  ImageView cover=new ImageView(activity);cover.setScaleType(cardView?ImageView.ScaleType.FIT_CENTER:ImageView.ScaleType.CENTER_CROP);cover.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);cover.setBackground(new NativeAppearance("brand",65,"emulatormayo",null));card.addView(cover,new LinearLayout.LayoutParams(cardView?-1:dp(44),(cardView?Math.max(dp(64),results.getHeight()-dp(84)):dp(58))));
  LinearLayout words=new LinearLayout(activity);words.setOrientation(android.widget.LinearLayout.VERTICAL);LinearLayout.LayoutParams wordsLayout=cardView?new LinearLayout.LayoutParams(-1,-2):new LinearLayout.LayoutParams(0,-2,1);wordsLayout.leftMargin=cardView?0:dp(14);wordsLayout.topMargin=cardView?dp(4):0;card.addView(words,wordsLayout);TextView title=label(game.title,cardView?14:16,0xffeffff4);title.setTypeface(null,Typeface.BOLD);title.setMaxLines(cardView?1:2);title.setEllipsize(android.text.TextUtils.TruncateAt.END);words.addView(title);TextView system=label(game.platform,12,0xff8ce5af);system.setPadding(0,dp(3),0,0);system.setMaxLines(1);system.setEllipsize(android.text.TextUtils.TruncateAt.END);words.addView(system);TextView hint=label(game.supported?"Resume latest save  ›":"Browse only · NES gameplay preview",11,0xffadc9bb);hint.setMaxLines(1);hint.setEllipsize(android.text.TextUtils.TruncateAt.END);words.addView(hint);
  card.setOnClickListener(v->{if(game.supported)prepare(game);else Toast.makeText(activity,"This platform is browse only. The LAN preview currently plays NES games.",Toast.LENGTH_SHORT).show();});
  String key=account+":"+game.romId;Bitmap cached=covers.get(key);if(cached!=null){cover.setImageBitmap(cached);return card;}
  synchronized(lifecycle){if(!live(revision))return card;previewTasks.add(previews.submit(()->{try{if(!live(revision))return;Bitmap image=HostArtwork.preview(files,game.romId,account,()->!live(revision));if(image==null)return;covers.put(key,image);post(revision,()->{if(cover.isAttachedToWindow())cover.setImageBitmap(image);});}catch(Exception|OutOfMemoryError ignored){}}));}
  return card;
 }
 private void choosePlatform(){
  if(platforms.isEmpty()){Toast.makeText(activity,"Reloading platform list…",Toast.LENGTH_SHORT).show();load();return;}hideKeyboard();
  LinearLayout box=new LinearLayout(activity);box.setOrientation(android.widget.LinearLayout.VERTICAL);box.setPadding(dp(16),dp(6),dp(16),dp(8));EditText filter=new EditText(activity);filter.setSingleLine();filter.setHint("Find a platform…");filter.setContentDescription("Find a platform");filter.setTextColor(0xffeffff4);filter.setHintTextColor(0xffa6c9b4);filter.setFilters(new InputFilter[]{new InputFilter.LengthFilter(100)});box.addView(filter,new LinearLayout.LayoutParams(-1,dp(48)));ListView list=new ListView(activity);list.setDividerHeight(dp(5));box.addView(list,new LinearLayout.LayoutParams(-1,0,1));List<HostRommLibrary.Platform> visible=new ArrayList<>();
  BaseAdapter adapter=new BaseAdapter(){public int getCount(){return visible.size()+1;}public Object getItem(int position){return position==0?null:visible.get(position-1);}public long getItemId(int position){return position==0?0:visible.get(position-1).id;}public View getView(int position,View old,ViewGroup parent){TextView item=label(position==0?"All platforms":visible.get(position-1).name,16,0xffeffff4);item.setGravity(Gravity.CENTER_VERTICAL);item.setPadding(dp(12),dp(8),dp(12),dp(8));item.setMinHeight(dp(48));item.setBackground(surface());return item;}};list.setAdapter(adapter);
  Runnable refresh=()->{String term=filter.getText().toString().trim().toLowerCase(Locale.ROOT);visible.clear();for(HostRommLibrary.Platform item:platforms)if((item.name+" "+item.slug).toLowerCase(Locale.ROOT).contains(term))visible.add(item);adapter.notifyDataSetChanged();};filter.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){refresh.run();}public void afterTextChanged(Editable e){}});refresh.run();
  platformDialog=new AlertDialog.Builder(activity).setTitle("Filter by platform").setView(box).setNegativeButton("Cancel",null).create();AlertDialog picker=platformDialog;list.setOnItemClickListener((parent,view,position,id)->{platform=position==0?null:visible.get(position-1);offset=0;picker.dismiss();platformDialog=null;load();});bindController(picker);picker.show();style(picker);picker.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN|WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);picker.getWindow().setLayout(Math.min(dp(560),Math.round(activity.getResources().getDisplayMetrics().widthPixels*.88f)),Math.round(activity.getResources().getDisplayMetrics().heightPixels*.86f));list.requestFocus();
 }
 private TextView label(String value,int size,int color){TextView text=new TextView(activity);text.setText(value);text.setTextSize(size);text.setTextColor(color);return text;}
 private StateListDrawable surface(){StateListDrawable states=new StateListDrawable();for(int[] state:new int[][]{new int[]{android.R.attr.state_focused},new int[]{android.R.attr.state_pressed},new int[]{android.R.attr.state_selected},new int[]{}}){GradientDrawable shape=new GradientDrawable();shape.setColor(state.length==0?0xf2183228:0xff285942);shape.setCornerRadius(dp(10));shape.setStroke(dp(state.length==0?1:2),state.length==0?0xff365c48:0xff8ce5af);states.addState(state,shape);}return states;}
 private void style(AlertDialog target){target.getWindow().setBackgroundDrawable(new NativeAppearance(NativeAppearance.readMode(activity.getPreferences(0)),NativeAppearance.readDim(activity.getPreferences(0)),"emulatormayo",null));target.getButton(AlertDialog.BUTTON_NEGATIVE).setTextColor(0xff9cf2bf);}
 private void hideKeyboard(){View focus=activity.getCurrentFocus();if(focus!=null)((android.view.inputmethod.InputMethodManager)activity.getSystemService(Activity.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(focus.getWindowToken(),0);}
 private void bindController(AlertDialog target){final boolean[] armed={false};target.setOnKeyListener((d,key,event)->{if(key!=KeyEvent.KEYCODE_BUTTON_A&&key!=KeyEvent.KEYCODE_BUTTON_B)return false;if(event.getAction()==KeyEvent.ACTION_DOWN){if(event.getRepeatCount()==0)armed[0]=true;return true;}if(event.getAction()==KeyEvent.ACTION_UP){boolean click=armed[0];armed[0]=false;if(click){if(key==KeyEvent.KEYCODE_BUTTON_B)target.cancel();else{View focus=target.getCurrentFocus();if(focus instanceof ListView){ListView list=(ListView)focus;int position=list.getSelectedItemPosition();if(position>=0)list.performItemClick(list.getSelectedView(),position,list.getItemIdAtPosition(position));}else if(focus!=null)focus.performClick();}}return true;}return true;});}
 private void cancelPreviews(){for(Future<?> preview:previewTasks)preview.cancel(true);previewTasks.clear();previews.getQueue().clear();}
 private void prepare(HostRommLibrary.Game game){
  int revision=begin();if(revision<0)return;rows.removeAllViews();status.setText("Preparing "+game.title+"…");previous.setEnabled(false);next.setEnabled(false);
  task=executor.submit(()->{try{HostRommLibrary.Prepared p=connection(revision).download(game);post(revision,()->{Callback callback=selected;dismiss();if(callback!=null)callback.selected(new Selection(p,"resume",null));});}catch(Exception e){post(revision,()->{status.setText("Could not prepare this NES game. Check RomM permissions, connection and available storage.");Button retry=button("Back to games",this::load);rows.addView(retry);});}});
 }
 public void chooseSave(Selection selection,Callback callback){
  if(selection==null||closed||!usable())return;cancelOperations();int revision=begin();if(revision<0)return;
  String[] actions={"Resume latest save (default)","Start new · keep existing saves","Choose a saved checkpoint"};
  dialog=new AlertDialog.Builder(activity).setTitle(selection.title).setItems(actions,(d,index)->{dismiss();if(!live(revision))return;if(index==0)callback.selected(selection.with("resume",null));else if(index==1)callback.selected(selection.with("new",null));else chooseSlot(selection,callback);}).setNegativeButton("Cancel",null).create();dialog.show();
 }
 private void chooseSlot(Selection selection,Callback callback){
  List<NativeStateStore.Entry> entries=NativeStateStore.listEntries(files,selection.gameKey);if(entries.isEmpty()){Toast.makeText(activity,"No compatible local saves yet. Resume will start a new game.",Toast.LENGTH_LONG).show();return;}
  int revision=begin();String[] labels=new String[entries.size()];for(int i=0;i<labels.length;i++)labels[i]=entries.get(i).label+" · "+android.text.format.DateFormat.format("MMM d, h:mm a",entries.get(i).savedAt);
  dialog=new AlertDialog.Builder(activity).setTitle("Choose save · "+selection.title).setItems(labels,(d,index)->{dismiss();if(live(revision))callback.selected(selection.with("slot",entries.get(index).id));}).setNegativeButton("Cancel",null).create();dialog.show();
 }
 /** Caller saves the outgoing game and stops its room first. Success is delivered on UI. */
 public void activate(Selection selection,Callback callback){
  activate(selection,callback,()->{});
 }
 public void activate(Selection selection,Callback callback,Runnable failure){
  if(selection==null||closed||!usable())return;cancelOperations();int revision=begin();if(revision<0)return;
  task=executor.submit(()->{try{
   HostRommLibrary service=connection(revision);
   try(HostRommLibrary.Activation staged=service.stage(selection.prepared)){
    // close/cancel and this commit share a lock. Copy/network work never holds it.
    synchronized(lifecycle){if(!live(revision))return;service.commit(staged);}
   }
   post(revision,()->callback.selected(selection));
  }catch(Exception e){post(revision,()->{Toast.makeText(activity,"Could not switch games. Check RomM connection and storage; previous saves were kept.",Toast.LENGTH_LONG).show();failure.run();});}});
 }
 public void cancelOperations(){synchronized(lifecycle){generation++;cancelPreviews();if(task!=null){task.cancel(true);task=null;}}dismiss();}
 public void close(){synchronized(lifecycle){if(closed)return;closed=true;generation++;if(task!=null)task.cancel(true);}dismiss();executor.shutdownNow();previews.shutdownNow();covers.evictAll();}
 private int dp(int value){return Math.round(value*activity.getResources().getDisplayMetrics().density);}
 private Button button(String label,Runnable action){Button b=new Button(activity);b.setAllCaps(false);b.setText(label);b.setTextColor(0xffeffff4);b.setTextSize(14);b.setMinHeight(dp(44));b.setPadding(dp(12),dp(4),dp(12),dp(4));b.setBackground(surface());b.setOnClickListener(v->action.run());return b;}
}
