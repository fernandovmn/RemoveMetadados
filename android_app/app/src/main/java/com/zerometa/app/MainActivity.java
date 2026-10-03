package com.zerometa.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ClipData;
import android.content.ContentResolver;
import android.content.Intent;
import android.content.res.AssetFileDescriptor;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.view.View;
import android.webkit.ValueCallback;
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
    private static final int REQUEST_FILE_CHOOSER = 1002;

    private WebView webView;
    private NativeBridge bridge;
    private ValueCallback<Uri[]> mFilePathCallback;

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
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback, FileChooserParams fileChooserParams) {
                if (mFilePathCallback != null) {
                    mFilePathCallback.onReceiveValue(null);
                }
                mFilePathCallback = filePathCallback;
                launchPhotoPickerIntent(REQUEST_FILE_CHOOSER);
                return true;
            }
        });

        // Dark background
        webView.setBackgroundColor(0xFF090D16);

        webView.loadUrl("file:///android_asset/www/index.html");

        // Ask for permissions
        bridge.requestStoragePermission();
    }

    public void openNativePhotoPicker() {
        launchPhotoPickerIntent(REQUEST_PICK_PHOTOS);
    }

    private void launchPhotoPickerIntent(int requestCode) {
        // 1. Android 13+ (API 33+) Photo Picker Oficial (interface visual moderna de fotos com abas de albuns e selecao multipla)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            try {
                Intent intent = new Intent(MediaStore.ACTION_PICK_IMAGES);
                intent.setType("image/*");
                int maxLimit = 100;
                try {
                    maxLimit = MediaStore.getPickImagesMaxLimit();
                } catch (Throwable ignored) {}
                intent.putExtra(MediaStore.EXTRA_PICK_IMAGES_MAX, maxLimit);
                startActivityForResult(intent, requestCode);
                return;
            } catch (Exception ignored) {}
        }

        // 2. Galeria Nativa do Aparelho (Samsung Galeria, Google Fotos, Xiaomi Galeria, etc.)
        try {
            Intent intent = new Intent(Intent.ACTION_PICK, MediaStore.Images.Media.EXTERNAL_CONTENT_URI);
            intent.setType("image/*");
            intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
            intent.putExtra("multi-pick", true);
            startActivityForResult(intent, requestCode);
            return;
        } catch (Exception ignored) {}

        // 3. Fallback com Chooser direcionado para imagens
        try {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("image/*");
            intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
            startActivityForResult(Intent.createChooser(intent, "Selecionar Fotos"), requestCode);
        } catch (Exception e) {
            e.printStackTrace();
            if (requestCode == REQUEST_FILE_CHOOSER && mFilePathCallback != null) {
                mFilePathCallback.onReceiveValue(null);
                mFilePathCallback = null;
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        // Retorno do seletor de fotos invocado pela interface nativa
        if (requestCode == REQUEST_PICK_PHOTOS) {
            if (resultCode == RESULT_OK && data != null) {
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
            return;
        }

        // Retorno do seletor invocado via WebView FileChooser
        if (requestCode == REQUEST_FILE_CHOOSER) {
            if (mFilePathCallback != null) {
                Uri[] results = null;
                if (resultCode == RESULT_OK && data != null) {
                    if (data.getClipData() != null) {
                        int count = data.getClipData().getItemCount();
                        results = new Uri[count];
                        for (int i = 0; i < count; i++) {
                            results[i] = data.getClipData().getItemAt(i).getUri();
                        }
                    } else if (data.getData() != null) {
                        results = new Uri[]{data.getData()};
                    }
                }
                mFilePathCallback.onReceiveValue(results);
                mFilePathCallback = null;
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
            String name = "foto.jpg";
            long size = 0;

            Cursor cursor = getContentResolver().query(uri, null, null, null, null);
            if (cursor != null) {
                int nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                int sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE);
                if (cursor.moveToFirst()) {
                    if (nameIndex != -1) {
                        String fetchedName = cursor.getString(nameIndex);
                        if (fetchedName != null && !fetchedName.trim().isEmpty()) {
                            name = fetchedName;
                        }
                    }
                    if (sizeIndex != -1) size = cursor.getLong(sizeIndex);
                }
                cursor.close();
            }

            if (size <= 0) {
                try {
                    AssetFileDescriptor pfd = getContentResolver().openAssetFileDescriptor(uri, "r");
                    if (pfd != null) {
                        size = pfd.getLength();
                        pfd.close();
                    }
                } catch (Exception ignored) {}
            }

            if (!name.contains(".")) {
                String mime = getContentResolver().getType(uri);
                if (mime != null && mime.contains("png")) name += ".png";
                else if (mime != null && mime.contains("webp")) name += ".webp";
                else name += ".jpg";
            }

            String realPath = getRealPathFromUri(uri, name, size);

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

    private String getRealPathFromUri(Uri uri, String displayName, long size) {
        // 1. Try querying MediaStore by uri first
        try {
            String[] proj = {MediaStore.Images.Media.DATA};
            Cursor cursor = getContentResolver().query(uri, proj, null, null, null);
            if (cursor != null) {
                int colIndex = cursor.getColumnIndex(MediaStore.Images.Media.DATA);
                if (colIndex != -1 && cursor.moveToFirst()) {
                    String path = cursor.getString(colIndex);
                    cursor.close();
                    if (path != null && new File(path).exists()) {
                        return path;
                    }
                }
                cursor.close();
            }
        } catch (Exception ignored) {}

        // 2. Query MediaStore by DISPLAY_NAME (essential for Android PhotoPicker URIs)
        try {
            String[] proj = {MediaStore.Images.Media.DATA};
            Cursor cursor = getContentResolver().query(
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                proj,
                MediaStore.Images.Media.DISPLAY_NAME + "=?",
                new String[]{displayName},
                MediaStore.Images.Media.DATE_MODIFIED + " DESC"
            );
            if (cursor != null) {
                int dataIdx = cursor.getColumnIndex(MediaStore.Images.Media.DATA);
                while (cursor.moveToNext()) {
                    if (dataIdx != -1) {
                        String path = cursor.getString(dataIdx);
                        if (path != null && new File(path).exists()) {
                            cursor.close();
                            return path;
                        }
                    }
                }
                cursor.close();
            }
        } catch (Exception ignored) {}

        // 3. Fallback: Search common storage directories directly
        try {
            File[] searchDirs = {
                new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DCIM), "Camera"),
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DCIM),
                new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES), "Screenshots"),
                new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES), "ZeroMeta"),
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES),
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            };
            for (File dir : searchDirs) {
                if (dir != null && dir.exists()) {
                    File candidate = new File(dir, displayName);
                    if (candidate.exists()) {
                        return candidate.getAbsolutePath();
                    }
                }
            }
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
