package com.zerometa.app;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.OutputStream;

public class NativeBridge {
    private final Activity activity;
    private final WebView webView;

    public NativeBridge(Activity activity, WebView webView) {
        this.activity = activity;
        this.webView = webView;
    }

    @JavascriptInterface
    public boolean isNative() {
        return true;
    }

    @JavascriptInterface
    public boolean hasStoragePermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            return Environment.isExternalStorageManager();
        }
        return true;
    }

    @JavascriptInterface
    public void requestStoragePermission() {
        activity.runOnUiThread(() -> {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                if (!Environment.isExternalStorageManager()) {
                    Toast.makeText(activity, "Por favor, autorize o acesso para sobrescrever fotos na pasta Pictures sem duplicar.", Toast.LENGTH_LONG).show();
                    try {
                        Intent intent = new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION);
                        intent.setData(Uri.parse("package:" + activity.getPackageName()));
                        activity.startActivity(intent);
                    } catch (Exception e) {
                        Intent intent = new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION);
                        activity.startActivity(intent);
                    }
                }
            }
        });
    }

    @JavascriptInterface
    public String readPhotoBase64(String filePath) {
        try {
            File f = new File(filePath);
            if (!f.exists() || !f.canRead()) {
                return null;
            }
            byte[] bytes = new byte[(int) f.length()];
            FileInputStream fis = new FileInputStream(f);
            int read = fis.read(bytes);
            fis.close();
            if (read > 0) {
                return Base64.encodeToString(bytes, Base64.NO_WRAP);
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        return null;
    }

    @JavascriptInterface
    public boolean overwritePhoto(String filePath, String base64CleanData) {
        if (filePath == null || filePath.trim().isEmpty()) {
            return false;
        }
        try {
            byte[] cleanBytes = Base64.decode(base64CleanData, Base64.DEFAULT);
            File targetFile = new File(filePath);
            if (!targetFile.exists()) {
                return false;
            }

            boolean written = false;

            // Tentativa 1: Escrita direta em File (funciona com MANAGE_EXTERNAL_STORAGE)
            try {
                FileOutputStream fos = new FileOutputStream(targetFile, false);
                fos.write(cleanBytes);
                fos.flush();
                fos.close();
                written = true;
            } catch (Exception e) {
                e.printStackTrace();
            }

            // Tentativa 2: Se falhar escrita direta, tentar sobrescrever via MediaStore ContentResolver
            if (!written) {
                try {
                    Uri contentUri = null;
                    try (Cursor c = activity.getContentResolver().query(
                        MediaStore.Files.getContentUri("external"),
                        new String[]{MediaStore.MediaColumns._ID},
                        MediaStore.MediaColumns.DATA + "=?",
                        new String[]{filePath},
                        null
                    )) {
                        if (c != null && c.moveToFirst()) {
                            long id = c.getLong(0);
                            contentUri = ContentUris.withAppendedId(MediaStore.Files.getContentUri("external"), id);
                        }
                    }
                    if (contentUri != null) {
                        try (OutputStream os = activity.getContentResolver().openOutputStream(contentUri, "wt")) {
                            if (os != null) {
                                os.write(cleanBytes);
                                os.flush();
                                written = true;
                            }
                        }
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                }
            }

            if (written) {
                // Refresh Android MediaStore gallery thumbnail in-place
                MediaScannerConnection.scanFile(activity, new String[]{targetFile.getAbsolutePath()}, null, (path, uri) -> {});
                return true;
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        return false;
    }

    @JavascriptInterface
    public boolean savePhotoToGallery(String fileName, String base64CleanData) {
        return savePhotoToGallery(fileName, base64CleanData, null);
    }

    @JavascriptInterface
    public boolean savePhotoToGallery(String fileName, String base64CleanData, String originalPath) {
        try {
            byte[] cleanBytes = Base64.decode(base64CleanData, Base64.DEFAULT);

            // 1. Prioridade máxima: Salvar diretamente na mesma pasta física da foto original
            if (originalPath != null && !originalPath.trim().isEmpty()) {
                try {
                    File origFile = new File(originalPath);
                    File parent = origFile.getParentFile();
                    if (parent != null && parent.exists() && parent.isDirectory()) {
                        File dest = new File(parent, fileName);
                        FileOutputStream fos = new FileOutputStream(dest, false);
                        fos.write(cleanBytes);
                        fos.flush();
                        fos.close();

                        MediaScannerConnection.scanFile(activity, new String[]{dest.getAbsolutePath()}, null, null);
                        return true;
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                }
            }

            // 2. Fallback via MediaStore
            ContentResolver resolver = activity.getContentResolver();
            ContentValues values = new ContentValues();
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
            String mimeType = "image/jpeg";
            String lower = fileName.toLowerCase();
            if (lower.endsWith(".png")) {
                mimeType = "image/png";
            } else if (lower.endsWith(".webp")) {
                mimeType = "image/webp";
            }
            values.put(MediaStore.MediaColumns.MIME_TYPE, mimeType);

            // Determinar diretório relativo baseado no caminho original
            String relativeDir = Environment.DIRECTORY_PICTURES;
            if (originalPath != null && !originalPath.trim().isEmpty()) {
                try {
                    File origFile = new File(originalPath);
                    File parent = origFile.getParentFile();
                    if (parent != null) {
                        String parentPath = parent.getAbsolutePath();
                        String storageRoot = Environment.getExternalStorageDirectory().getAbsolutePath();
                        if (parentPath.startsWith(storageRoot)) {
                            String sub = parentPath.substring(storageRoot.length());
                            while (sub.startsWith("/") || sub.startsWith("\\")) {
                                sub = sub.substring(1);
                            }
                            if (!sub.isEmpty()) {
                                relativeDir = sub.replace('\\', '/');
                            }
                        }
                    }
                } catch (Exception ignored) {}
            }

            Uri baseUri = MediaStore.Images.Media.EXTERNAL_CONTENT_URI;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                if (relativeDir.equalsIgnoreCase("Download") || relativeDir.toLowerCase().startsWith("download/")) {
                    baseUri = MediaStore.Downloads.EXTERNAL_CONTENT_URI;
                }
                values.put(MediaStore.MediaColumns.RELATIVE_PATH, relativeDir);
                values.put(MediaStore.MediaColumns.IS_PENDING, 1);
            } else {
                File dir = new File(Environment.getExternalStorageDirectory(), relativeDir);
                if (!dir.exists()) dir.mkdirs();
                File dest = new File(dir, fileName);
                values.put(MediaStore.MediaColumns.DATA, dest.getAbsolutePath());
            }

            Uri uri = resolver.insert(baseUri, values);
            if (uri != null) {
                OutputStream os = resolver.openOutputStream(uri);
                if (os != null) {
                    os.write(cleanBytes);
                    os.flush();
                    os.close();
                }

                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    values.clear();
                    values.put(MediaStore.MediaColumns.IS_PENDING, 0);
                    resolver.update(uri, values, null, null);
                } else {
                    MediaScannerConnection.scanFile(activity, new String[]{values.getAsString(MediaStore.MediaColumns.DATA)}, null, null);
                }

                return true;
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        return false;
    }

    @JavascriptInterface
    public String readPhotoBase64ByUri(String uriString) {
        try {
            Uri uri = Uri.parse(uriString);
            java.io.InputStream is = activity.getContentResolver().openInputStream(uri);
            if (is != null) {
                java.io.ByteArrayOutputStream baos = new java.io.ByteArrayOutputStream();
                byte[] buffer = new byte[16384];
                int len;
                while ((len = is.read(buffer)) != -1) {
                    baos.write(buffer, 0, len);
                }
                is.close();
                return Base64.encodeToString(baos.toByteArray(), Base64.NO_WRAP);
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        return null;
    }

    @JavascriptInterface
    public boolean overwritePhotoByUri(String uriString, String base64CleanData) {
        try {
            Uri uri = Uri.parse(uriString);
            byte[] cleanBytes = Base64.decode(base64CleanData, Base64.DEFAULT);
            java.io.OutputStream os = activity.getContentResolver().openOutputStream(uri, "wt");
            if (os != null) {
                os.write(cleanBytes);
                os.flush();
                os.close();
                return true;
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        return false;
    }

    @JavascriptInterface
    public void pickPhotosNative() {
        activity.runOnUiThread(() -> {
            if (activity instanceof MainActivity) {
                ((MainActivity) activity).openNativePhotoPicker();
            }
        });
    }

    @JavascriptInterface
    public void showToast(String message) {
        activity.runOnUiThread(() -> Toast.makeText(activity, message, Toast.LENGTH_SHORT).show());
    }
}
