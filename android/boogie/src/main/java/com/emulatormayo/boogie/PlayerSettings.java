package com.emulatormayo.boogie;

import android.app.*;
import android.content.SharedPreferences;
import android.view.View;
import android.widget.*;
import org.json.JSONObject;

/** Frontend preferences; no core/runtime options or incompatible state changes. */
final class PlayerSettings {
    interface Changed { void run(); }
    static SharedPreferences prefs(Activity a) { return a.getSharedPreferences("boogie-player-options", 0); }
    static JSONObject defaults() { return MainActivity.obj("scale", "fit", "filter", "nearest", "volume", 80, "muted", false); }
    static JSONObject current(Activity a, String game) {
        SharedPreferences p = prefs(a);
        String key = ControllerProfiles.game(game) && p.contains("game:" + game) ? "game:" + game : "defaults";
        try { JSONObject saved = new JSONObject(p.getString(key, "{}")), result = defaults();
            if (saved.optString("scale").matches("fit|stretch")) result.put("scale", saved.getString("scale"));
            if (saved.optString("filter").matches("nearest|linear")) result.put("filter", saved.getString("filter"));
            if (saved.opt("volume") instanceof Integer && saved.getInt("volume") >= 0 && saved.getInt("volume") <= 100) result.put("volume", saved.getInt("volume"));
            if (saved.opt("muted") instanceof Boolean) result.put("muted", saved.getBoolean("muted"));
            return result;
        } catch (Exception ignored) { return defaults(); }
    }
    static AlertDialog show(Activity a, String game, boolean hosting, Changed changed, Runnable dismissed) {
        JSONObject value = current(a, game);
        LinearLayout box = new LinearLayout(a); box.setOrientation(android.widget.LinearLayout.VERTICAL); int pad = Math.round(20 * a.getResources().getDisplayMetrics().density); box.setPadding(pad, pad/2, pad, pad/2);
        TextView context = new TextView(a); context.setText("Display and audio on this device. The emulator core and saved-state format stay unchanged. Host volume also affects the shared game audio. Stream quality and FPS are under Video quality on a guest."); box.addView(context);
        TextView scalingLabel = new TextView(a); scalingLabel.setText(hosting ? "Video scaling · host uses the emulator’s original layout" : "Guest video scaling"); box.addView(scalingLabel);
        Spinner scaling = new Spinner(a); scaling.setAdapter(new ArrayAdapter<>(a, android.R.layout.simple_spinner_dropdown_item, new String[]{"Fit · preserve aspect ratio", "Stretch · fill screen"})); scaling.setSelection(value.optString("scale").equals("stretch") ? 1 : 0); scaling.setEnabled(!hosting); box.addView(scaling);
        TextView filterLabel = new TextView(a); filterLabel.setText("Image filtering"); box.addView(filterLabel);
        Spinner filtering = new Spinner(a); filtering.setAdapter(new ArrayAdapter<>(a, android.R.layout.simple_spinner_dropdown_item, new String[]{"Sharp pixels", "Smooth"})); filtering.setSelection(value.optString("filter").equals("linear") ? 1 : 0); box.addView(filtering);
        TextView volumeLabel = new TextView(a); volumeLabel.setText("Volume · " + value.optInt("volume") + "%"); box.addView(volumeLabel);
        SeekBar volume = new SeekBar(a); volume.setMax(100); volume.setProgress(value.optInt("volume")); volume.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar v,int n,boolean user){volumeLabel.setText("Volume · "+n+"%");}public void onStartTrackingTouch(SeekBar v){}public void onStopTrackingTouch(SeekBar v){}}); box.addView(volume);
        CheckBox mute = new CheckBox(a); mute.setText("Mute game audio"); mute.setChecked(value.optBoolean("muted")); box.addView(mute);
        RadioGroup scope = new RadioGroup(a); RadioButton global = new RadioButton(a); global.setId(View.generateViewId()); global.setText("Default for all games"); scope.addView(global);
        RadioButton specific = new RadioButton(a); specific.setId(View.generateViewId()); specific.setText("This game only"); specific.setEnabled(ControllerProfiles.game(game)); scope.addView(specific); global.setChecked(true); if (ControllerProfiles.game(game) && prefs(a).contains("game:" + game)) specific.setChecked(true); box.addView(scope);
        ScrollView scroll = new ScrollView(a); scroll.addView(box);
        AlertDialog dialog = new AlertDialog.Builder(a).setTitle("Player settings").setView(scroll).setNegativeButton("Cancel", null)
            .setNeutralButton(ControllerProfiles.game(game) ? "Use defaults for this game" : "Reset defaults", (d,w) -> { prefs(a).edit().remove(ControllerProfiles.game(game) ? "game:" + game : "defaults").apply(); changed.run(); })
            .setPositiveButton("Save", (d,w) -> { JSONObject next = MainActivity.obj("scale", scaling.getSelectedItemPosition() == 1 ? "stretch" : "fit", "filter", filtering.getSelectedItemPosition() == 1 ? "linear" : "nearest", "volume", volume.getProgress(), "muted", mute.isChecked()); prefs(a).edit().putString(specific.isChecked() ? "game:" + game : "defaults", next.toString()).apply(); changed.run(); }).create();
        dialog.setOnDismissListener(d -> dismissed.run()); dialog.show(); return dialog;
    }
}
