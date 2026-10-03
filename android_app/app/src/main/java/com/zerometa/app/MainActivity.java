package com.zerometa.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ClipData;
import android.content.ContentResolver;
import android.content.ContentUris;
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
            String name = null;
            long size = 0;

            // 1. Tentar ler OpenableColumns primeiro
            try (Cursor cursor = getContentResolver().query(uri, null, null, null, null)) {
                if (cursor != null && cursor.moveToFirst()) {
                    int nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                    int sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE);
                    if (nameIndex != -1) {
                        String fetched = cursor.getString(nameIndex);
                        if (fetched != null && !fetched.trim().isEmpty()) {
                            name = fetched.trim();
                        }
                    }
                    if (sizeIndex != -1) size = cursor.getLong(sizeIndex);
                }
            } catch (Exception ignored) {}

            // 2. Se size não veio do cursor, tentar AssetFileDescriptor
            if (size <= 0) {
                try (AssetFileDescriptor pfd = getContentResolver().openAssetFileDescriptor(uri, "r")) {
                    if (pfd != null) size = pfd.getLength();
                } catch (Exception ignored) {}
            }

            // 3. Extrair ID numérico do PhotoPicker se houver (ex: content://media/picker/.../386085)
            long mediaId = -1;
            String lastSegment = uri.getLastPathSegment();
            if (lastSegment != null && lastSegment.matches("\\d+")) {
                try {
                    mediaId = Long.parseLong(lastSegment);
                } catch (Exception ignored) {}
            }
            if (mediaId == -1 && name != null && name.matches("\\d+")) {
                try {
                    mediaId = Long.parseLong(name);
                } catch (Exception ignored) {}
            }

            String realPath = null;

            // 4. Se temos um ID numérico, buscar o nome real e caminho real no MediaStore
            if (mediaId > 0) {
                String[] proj = {
                    MediaStore.MediaColumns.DISPLAY_NAME,
                    MediaStore.MediaColumns.DATA,
                    MediaStore.MediaColumns.SIZE
                };

                Uri[] queryUris = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
                    ? new Uri[]{
                        MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                        MediaStore.Files.getContentUri("external"),
                        MediaStore.Downloads.EXTERNAL_CONTENT_URI
                    }
                    : new Uri[]{
                        MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                        MediaStore.Files.getContentUri("external")
                    };

                for (Uri qUri : queryUris) {
                    try (Cursor c = getContentResolver().query(
                        qUri,
                        proj,
                        MediaStore.MediaColumns._ID + "=?",
                        new String[]{String.valueOf(mediaId)},
                        null
                    )) {
                        if (c != null && c.moveToFirst()) {
                            int dIdx = c.getColumnIndex(MediaStore.MediaColumns.DISPLAY_NAME);
                            int pIdx = c.getColumnIndex(MediaStore.MediaColumns.DATA);
                            int sIdx = c.getColumnIndex(MediaStore.MediaColumns.SIZE);

                            if (dIdx != -1) {
                                String disp = c.getString(dIdx);
                                if (disp != null && disp.contains(".")) {
                                    name = disp;
                                }
                            }
                            if (pIdx != -1) {
                                String path = c.getString(pIdx);
                                if (path != null && new File(path).exists()) {
                                    realPath = path;
                                }
                            }
                            if (size <= 0 && sIdx != -1) {
                                size = c.getLong(sIdx);
                            }
                            if (realPath != null) break;
                        }
                    } catch (Exception ignored) {}
                }
            }

            // 5. Se ainda não temos realPath ou nome com extensão real, tentar resolver por busca
            if (realPath == null) {
                realPath = getRealPathFromUri(uri, name, size);
            }

            if (realPath != null) {
                File f = new File(realPath);
                if (f.exists()) {
                    if (name == null || !name.contains(".") || name.matches("\\d+")) {
                        name = f.getName();
                    }
                    if (size <= 0) {
                        size = f.length();
                    }
                }
            }

            // 6. Fallback de extensão se ainda não tiver ponto
            if (name == null || !name.contains(".")) {
                String mime = getContentResolver().getType(uri);
                String ext = ".jpg";
                if (mime != null && mime.contains("png")) ext = ".png";
                else if (mime != null && mime.contains("webp")) ext = ".webp";
                name = (name != null && !name.trim().isEmpty() ? name : "foto") + ext;
            }

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
        // 1. Tentar ler coluna DATA diretamente da URI
        try {
            String[] proj = {MediaStore.Images.Media.DATA};
            try (Cursor cursor = getContentResolver().query(uri, proj, null, null, null)) {
                if (cursor != null && cursor.moveToFirst()) {
                    int colIndex = cursor.getColumnIndex(MediaStore.Images.Media.DATA);
                    if (colIndex != -1) {
                        String path = cursor.getString(colIndex);
                        if (path != null && new File(path).exists()) {
                            return path;
                        }
                    }
                }
            }
        } catch (Exception ignored) {}

        // 2. Se temos displayName com extensão (ex: 1790945695631_092325.jpg), consultar MediaStore
        if (displayName != null && displayName.contains(".")) {
            try {
                String[] proj = {MediaStore.MediaColumns.DATA};
                Uri[] qUris = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
                    ? new Uri[]{MediaStore.Images.Media.EXTERNAL_CONTENT_URI, MediaStore.Downloads.EXTERNAL_CONTENT_URI, MediaStore.Files.getContentUri("external")}
                    : new Uri[]{MediaStore.Images.Media.EXTERNAL_CONTENT_URI, MediaStore.Files.getContentUri("external")};

                for (Uri qUri : qUris) {
                    try (Cursor cursor = getContentResolver().query(
                        qUri,
                        proj,
                        MediaStore.MediaColumns.DISPLAY_NAME + "=?",
                        new String[]{displayName},
                        MediaStore.MediaColumns.DATE_MODIFIED + " DESC"
                    )) {
                        if (cursor != null) {
                            int dataIdx = cursor.getColumnIndex(MediaStore.MediaColumns.DATA);
                            while (cursor.moveToNext()) {
                                if (dataIdx != -1) {
                                    String path = cursor.getString(dataIdx);
                                    if (path != null && new File(path).exists()) {
                                        return path;
                                    }
                                }
                            }
                        }
                    } catch (Exception ignored) {}
                }
            } catch (Exception ignored) {}
        }

        // 3. Se temos o tamanho exato (size > 0), consultar MediaStore por SIZE
        if (size > 0) {
            try {
                String[] proj = {MediaStore.MediaColumns.DATA, MediaStore.MediaColumns.DISPLAY_NAME};
                try (Cursor cursor = getContentResolver().query(
                    MediaStore.Files.getContentUri("external"),
                    proj,
                    MediaStore.MediaColumns.SIZE + "=?",
                    new String[]{String.valueOf(size)},
                    MediaStore.MediaColumns.DATE_MODIFIED + " DESC"
                )) {
                    if (cursor != null) {
                        int dataIdx = cursor.getColumnIndex(MediaStore.MediaColumns.DATA);
                        while (cursor.moveToNext()) {
                            if (dataIdx != -1) {
                                String path = cursor.getString(dataIdx);
                                if (path != null && new File(path).exists()) {
                                    return path;
                                }
                            }
                        }
                    }
                }
            } catch (Exception ignored) {}
        }

        // 4. Varredura direta em diretórios comuns de armazenamento
        try {
            File[] searchDirs = {
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
                new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DCIM), "Camera"),
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DCIM),
                new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES), "Screenshots"),
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES),
                Environment.getExternalStorageDirectory()
            };

            // Se temos displayName com extensão
            if (displayName != null && displayName.contains(".")) {
                for (File dir : searchDirs) {
                    if (dir != null && dir.exists()) {
                        File candidate = new File(dir, displayName);
                        if (candidate.exists()) {
                            return candidate.getAbsolutePath();
                        }
                    }
                }
            }

            // Se temos size > 0, checar arquivos pelo tamanho exato nas pastas públicas
            if (size > 0) {
                for (File dir : searchDirs) {
                    if (dir != null && dir.exists() && dir.isDirectory()) {
                        File[] files = dir.listFiles();
                        if (files != null) {
                            for (File f : files) {
                                if (f.isFile() && f.length() == size) {
                                    String lower = f.getName().toLowerCase();
                                    if (lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".png") || lower.endsWith(".webp")) {
                                        return f.getAbsolutePath();
                                    }
                                }
                            }
                        }
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
