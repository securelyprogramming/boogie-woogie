package com.emulatormayo.boogie;

import android.app.Instrumentation;
import android.content.Context;
import android.content.ContextWrapper;
import android.content.ComponentName;
import android.os.Bundle;
import org.json.JSONObject;
import java.io.*;
import java.nio.file.Files;
import java.util.Arrays;

/** Runs only against a temporary directory; never touches the owner's games/pairing. */
public final class IntegrationSmoke extends Instrumentation {
    int checks;
    void check(boolean okay, String message) { if (!okay) throw new AssertionError(message); checks++; }
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle result = new Bundle(); File temporary = null;
        try {
            temporary = Files.createTempDirectory(getTargetContext().getCacheDir().toPath(), "boogie-test-").toFile();
            final File root = temporary;
            Context sandbox = new ContextWrapper(getTargetContext()) {
                @Override public Context getApplicationContext() { return this; }
                @Override public File getFilesDir() { return root; }
            };
            check(BoogieIntegration.storage(sandbox).equals(new File(root, "boogie-woogie")), "Storage escaped namespace");
            JSONObject raw = new JSONObject().put("host", false).put("baseUrl", "https://192.168.50.25:9443")
                .put("certificateSha256", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
                .put("invitationSecret", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
                .put("hostCredential", "do-not-retain").put("rommCookie", "do-not-retain").put("game", "/private/path");
            JSONObject safe = BoogieIntegration.pairing(raw);
            check(safe.length() == 4 && !safe.has("hostCredential") && !safe.has("rommCookie") && !safe.has("game"), "Pairing retained untrusted fields");
            String[] bad = {"http://192.168.50.25", "https://user@example.com", "https://example.com/path", "https://example.com/#secret", "https://example.com:0"};
            for (String address : bad) { boolean rejected = false; try { BoogieIntegration.pairing(new JSONObject(raw.toString()).put("baseUrl", address)); } catch (Exception expected) { rejected = true; } check(rejected, "Unsafe broker origin accepted"); }
            File source = new File(root, "original.nes"); byte[] rom = new byte[16 + 16384]; rom[0]='N';rom[1]='E';rom[2]='S';rom[3]=26;rom[4]=1;
            Files.write(source.toPath(), rom); BoogieIntegration.importLocal(sandbox, source, "Original test fixture");
            File files = BoogieIntegration.storage(sandbox);
            JSONObject extraFields = new JSONObject().put("id",1).put("name","Synthetic fixture").put("fs_name","fixture.nes").put("platform_slug","nes")
                .put("rommCookie","synthetic-secret").put("password","synthetic-secret").put("apiToken","synthetic-secret");
            JSONObject gameFields = new HostRommLibrary.Game(extraFields).json();
            check(gameFields.length()==7 && !gameFields.toString().contains("synthetic-secret"),"Game metadata retained credentials or unknown fields");
            JSONObject activeFields = new JSONObject(new String(Files.readAllBytes(new File(files,"current-game.json").toPath()),java.nio.charset.StandardCharsets.UTF_8));
            check(activeFields.length()==11 && activeFields.getString("accountKey").matches("[a-f0-9]{64}") && activeFields.getString("gameKey").matches("sha256:[a-f0-9]{64}"),"Active metadata schema changed");
            BoogieIntegration.connectRomm(sandbox,"https://example.invalid/","synthetic_session=not-a-real-cookie");
            check(BoogieIntegration.hasRommSession()&&!new File(files,"romm-session.json").exists(),"Native cookie persisted to disk");
            BoogieIntegration.clearRomm(sandbox);
            check(!BoogieIntegration.hasRommSession(),"Native session survived clear");
            HostRommLibrary.Prepared selected = HostRommLibrary.current(files);
            check(selected != null && BoogieIntegration.LOCAL_ACCOUNT.equals(selected.accountKey), "Local import identity incorrect");
            check(Arrays.equals(rom, Files.readAllBytes(source.toPath())), "Import changed source document");
            HostRommLibrary library = new HostRommLibrary(files, () -> false);
            check(library.list("fixture",false,0).games.size() == 1 && library.list("missing",false,0).games.isEmpty(), "Local search failed");
            check(library.platforms().size() == 1 && library.download(selected.game).gameKey.equals(selected.gameKey), "Local picker activation failed");
            File oldState = new File(files, "states/keep.bin"); oldState.getParentFile().mkdirs(); Files.write(oldState.toPath(), new byte[]{1,2,3});
            JSONObject record = new JSONObject(new String(Files.readAllBytes(new File(files,"current-game.json").toPath()), java.nio.charset.StandardCharsets.UTF_8));
            record.put("accountKey", "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"); Files.write(new File(files,"current-game.json").toPath(),record.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
            BoogieIntegration.clearRomm(sandbox);
            check(!new File(files,"current-game.json").exists() && !new File(files,"game.nes").exists(), "Account clear retained active RomM game");
            check(oldState.isFile() && selected.cachedGame.isFile(), "Account clear deleted saves or cache");
            check(!getTargetContext().getPackageManager().getActivityInfo(new ComponentName(getTargetContext().getPackageName(),MainActivity.class.getName()),0).exported, "Embedded activity exported");
            try (InputStream in = getTargetContext().getAssets().open("boogie/player.html")) { check(in.read() == '<', "Namespaced player missing"); }
            result.putString("stream", "Boogie integration checks passed: " + checks + "\n"); finish(-1,result);
        } catch (Throwable error) { result.putString("stream", "FAILED: " + error.getClass().getSimpleName() + ": " + error.getMessage() + "\n"); finish(0,result); }
        finally { if (temporary != null) remove(temporary); }
    }
    void remove(File file) { File[] children = file.listFiles(); if(children!=null)for(File child:children)remove(child);file.delete(); }
}
