package com.zerometa.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ClipData;
import android.content.ContentResolver;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;

public class MainActivity extends Activity {
    private static final int REQUEST_PICK_PHOTOS = 1001;
    private WebView webView;
    private NativeBridge bridge;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);

        bridge = new NativeBridge(this, webView);
        webView.addJavascriptInterface(bridge, "AndroidBridge");

        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient());

        // Dark background
        webView.setBackgroundColor(0xFF090D16);

        webView.loadUrl("file:///android_asset/www/index.html");

        // Ask for permissions
        bridge.requestStoragePermission();
    }

    public void openNativePhotoPicker() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("image/*");
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        startActivityForResult(intent, REQUEST_PICK_PHOTOS);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        if (requestCode == REQUEST_PICK_PHOTOS && resultCode == RESULT_OK && data != null) {
            JSONArray items = new JSONArray();

            if (data.getClipData() != null) {
                ClipData clipData = data.getClipData();
                for (int i = 0; i < clipData.getItemCount(); i++) {
                    Uri uri = clipData.getItemAt(i).getUri();
                    JSONObject obj = resolveUriDetails(uri);
                    if (obj != null) items.put(obj);
                }
            } else if (data.getData() != null) {
                Uri uri = data.getData();
                JSONObject obj = resolveUriDetails(uri);
                if (obj != null) items.put(obj);
            }

            if (items.length() > 0) {
                String js = "window.onNativePhotosPicked(" + items.toString() + ");";
                webView.post(() -> webView.evaluateJavascript(js, null));
            }
        }
    }

    private JSONObject resolveUriDetails(Uri uri) {
        try {
            try {
                getContentResolver().takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                );
            } catch (Exception ignored) {}

            JSONObject obj = new JSONObject();
            String name = "foto.png";
            long size = 0;

            Cursor cursor = getContentResolver().query(uri, null, null, null, null);
            if (cursor != null) {
                int nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                int sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE);
                if (cursor.moveToFirst()) {
                    if (nameIndex != -1) name = cursor.getString(nameIndex);
                    if (sizeIndex != -1) size = cursor.getLong(sizeIndex);
                }
                cursor.close();
            }

            String realPath = getRealPathFromUri(uri, name);

            obj.put("name", name);
            obj.put("size", size);
            obj.put("uri", uri.toString());
            obj.put("realPath", realPath != null ? realPath : "");

            return obj;
        } catch (Exception e) {
            e.printStackTrace();
            return null;
        }
    }

    private String getRealPathFromUri(Uri uri, String displayName) {
        // Try direct file path query
        try {
            String[] proj = {MediaStore.Images.Media.DATA};
            Cursor cursor = getContentResolver().query(uri, proj, null, null, null);
            if (cursor != null) {
                int colIndex = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DATA);
                if (cursor.moveToFirst()) {
                    String path = cursor.getString(colIndex);
                    cursor.close();
                    if (path != null && new File(path).exists()) {
                        return path;
                    }
                }
                cursor.close();
            }
        } catch (Exception ignored) {}

        // Fallback: Check Pictures / DCIM directly on storage
        try {
            File picturesDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES);
            File candidate = new File(picturesDir, displayName);
            if (candidate.exists()) return candidate.getAbsolutePath();

            File dcimDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DCIM);
            File candidateCamera = new File(new File(dcimDir, "Camera"), displayName);
            if (candidateCamera.exists()) return candidateCamera.getAbsolutePath();
        } catch (Exception ignored) {}

        return null;
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
