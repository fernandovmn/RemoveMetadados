package com.zerometa.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
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
        try {
            byte[] cleanBytes = Base64.decode(base64CleanData, Base64.DEFAULT);
            File targetFile = new File(filePath);

            // Write clean bytes directly over original file
            FileOutputStream fos = new FileOutputStream(targetFile, false);
            fos.write(cleanBytes);
            fos.flush();
            fos.close();

            // Refresh Android MediaStore gallery thumbnail in-place
            MediaScannerConnection.scanFile(activity, new String[]{targetFile.getAbsolutePath()}, null, (path, uri) -> {
                // Scanned
            });

            return true;
        } catch (Exception e) {
            e.printStackTrace();
            return false;
        }
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
