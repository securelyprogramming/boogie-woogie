package com.emulatormayo.boogie;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import org.json.JSONObject;
import java.io.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.*;

/** Same-sandbox integration. Neither credentials nor game paths enter intents or the broker. */
public final class BoogieIntegration {
    private BoogieIntegration() {}
    static boolean rommConnected;
    public static File storage(Context context) {
        File root = new File(context.getApplicationContext().getFilesDir(), "boogie-woogie");
        if (!root.isDirectory() && !root.mkdirs()) throw new IllegalStateException("Cannot open co-op storage");
        return root;
    }
    public static void open(Activity activity, String brand) {
        activity.getSharedPreferences("boogie-integration", Context.MODE_PRIVATE).edit()
            .putString("brand", "rommayo".equals(brand) ? "rommayo" : "emulatormayo").apply();
        activity.startActivity(new Intent(activity, MainActivity.class));
    }
    public static void connectRomm(Context context, String server, String cookie) {
        try {
            clearRomm(context);
            URI uri = new URI(server);
            if (!Arrays.asList("https", "http").contains(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null || server.length() > 2048 || cookie == null || cookie.isEmpty() || cookie.length() > 16384 || cookie.chars().anyMatch(c -> c < 32 || c == 127)) throw new IOException();
            // Native library validates the same server again before every authenticated operation.
            HostRommLibrary.atomicBytes(new File(storage(context), "romm-session.json"), new JSONObject()
                .put("rommServer", server).put("rommCookie", cookie).toString().getBytes(StandardCharsets.UTF_8));
        rommConnected = true;
        } catch (Exception error) { throw new IllegalArgumentException("Connect to RomM before opening co-op."); }
    }
    public static void clearRomm(Context context) {
        File root = storage(context);
        new File(root, "romm-session.json").delete();
        // Forget the active pointer, retaining account caches and all checkpoints.
        try { File record = new File(root, "current-game.json"); JSONObject active = new JSONObject(new String(HostRommLibrary.readBounded(record, 8192), StandardCharsets.UTF_8));
            if (!LOCAL_ACCOUNT.equals(active.optString("accountKey"))) { record.delete(); new File(root, "game.nes").delete(); }
        } catch (Exception ignored) {}
        rommConnected = false;
    }
    static final String LOCAL_ACCOUNT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    /** The source document stays intact. Activation uses the same rollback path as RomM downloads. */
    public static synchronized void importLocal(Context context, File game, String title) throws Exception {
        String digest = HostRommLibrary.verifyGame(game);
        File files = storage(context), folder = new File(files, "romm-library/" + LOCAL_ACCOUNT + "/games");
        if (!folder.isDirectory() && !folder.mkdirs()) throw new IOException("Could not open local library");
        File cached = new File(folder, digest + ".nes"), pending = File.createTempFile("import-", ".tmp", folder);
        HostRommLibrary.privateFile(pending);
        try {
            try (InputStream in = new FileInputStream(game); FileOutputStream out = new FileOutputStream(pending)) {
                byte[] buffer = new byte[65536]; int count, size = 0;
                while ((count = in.read(buffer)) != -1) { size += count; if (size > HostRommLibrary.MAX_ROM) throw new IOException("NES import is too large"); out.write(buffer, 0, count); }
                out.getFD().sync();
            }
            if (!digest.equals(HostRommLibrary.verifyGame(pending))) throw new IOException("Game changed during import");
            HostRommLibrary.atomicMove(pending, cached);
            int id = (int) (Long.parseLong(digest.substring(0, 7), 16) + 1);
            JSONObject metadata = new JSONObject().put("id", id).put("name", HostRommLibrary.text(title, 250, "Imported NES game"))
                .put("fs_name", digest + ".nes").put("platform_id", 1).put("platform_display_name", "NES")
                .put("platform_slug", "nes").put("fs_size_bytes", cached.length()).put("gameKey", "sha256:" + digest);
            HostRommLibrary.atomicBytes(new File(folder, digest + ".json"), metadata.toString().getBytes(StandardCharsets.UTF_8));
            HostRommLibrary service = HostRommLibrary.local(files, () -> false);
            HostRommLibrary.Prepared selection = new HostRommLibrary.Prepared(new HostRommLibrary.Game(metadata), LOCAL_ACCOUNT, "sha256:" + digest, cached);
            try (HostRommLibrary.Activation staged = service.stage(selection)) { service.commit(staged); }
        } finally { pending.delete(); }
    }
    static JSONObject pairing(JSONObject source) throws Exception {
        // Imported files cannot replace a RomM session, choose a file path, or alter core options.
        if (!(source.opt("host") instanceof Boolean)) throw new IOException("Pairing file must specify host true or false");
        boolean host = source.getBoolean("host");
        URI uri = new URI(source.getString("baseUrl"));
        if (!"https".equals(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null || !(uri.getPath().isEmpty() || uri.getPath().equals("/")) || uri.getPort() > 65535 || uri.getPort() == 0) throw new IOException("Pairing needs an HTTPS broker origin");
        String pin = source.getString("certificateSha256"), invite = source.getString("invitationSecret");
        if (!pin.matches("[a-f0-9]{64}") || !invite.matches("[A-Za-z0-9_-]{32,128}")) throw new IOException("Pairing certificate or invitation is invalid");
        JSONObject safe = new JSONObject().put("host", host).put("baseUrl", uri.toString().replaceAll("/+$", ""))
            .put("certificateSha256", pin).put("invitationSecret", invite);
        if (host) { String key = source.getString("hostCredential"); if (!key.matches("[A-Za-z0-9_-]{32,128}")) throw new IOException("Host credential is invalid"); safe.put("hostCredential", key); }
        return safe;
    }
}
