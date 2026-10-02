# Proguard rules for ZeroMeta
-keep class com.zerometa.app.** { *; }
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
