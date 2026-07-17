# Google IMA SDK DAI - Media3 IMA Extension Integration Guide

This guide covers integrating the Google IMA SDK for Android DAI using the
**Media3 IMA Extension** (`androidx.media3:media3-exoplayer-ima`) and
`ImaServerSideAdInsertionMediaSource`.

Using the extension is the recommended approach for Media3 ExoPlayer
integrations as it handles stream wrapping, ad UI overlays, and ad event
synchronization automatically without requiring a custom `VideoStreamPlayer`
implementation.

--------------------------------------------------------------------------------

## 1. Dependencies and Configuration

Add the Media3 IMA extension dependency to your app's `build.gradle.kts` file.

Use latest version of the IMA SDK, which is published at
https://developers.google.com/interactive-media-ads/docs/sdks/android/client-side/download.md.txt.
Use the latest version of the ExoPlayer and IMA extension at
https://developer.android.com/jetpack/androidx/releases/media3.md.txt.

```kotlin
android {
    defaultConfig {
        minSdk = 23
    }
}

dependencies {
    implementation("androidx.media3:media3-ui:$latestVersion")
    implementation("androidx.media3:media3-exoplayer:$latestVersion")

    // Recommend using latest version of media3-exoplayer-ima (version 1.10.1 or higher)
    implementation("androidx.media3:media3-exoplayer-ima:1.10.1")
}
```

--------------------------------------------------------------------------------

### 2. Initialization & Best Practices

Configure the SDK early to minimize latency, and reuse the SDK settings:

*   **Early Warmup & Settings Reuse:** Call `ImaSdkFactory.initialize()` in your `Application.onCreate()` to preload SDK resources.
*   **Reuse `ImaSdkSettings`:** You MUST reuse the exact same `ImaSdkSettings` instance in both the `ImaSdkFactory.initialize()` call and the `ImaServerSideAdInsertionMediaSource.AdsLoader.Builder.setImaSdkSettings()` call. Recreating settings causes cache misses and ad loading latency spikes.
*   **Do NOT use `ImaAdsLoader`:** For DAI / SSAI streams, do NOT use the client-side `ImaAdsLoader` class. Use `ImaServerSideAdInsertionMediaSource.AdsLoader` instead.

```kotlin
// 1. Application class for early warmup
class MyApplication : Application() {
    companion object {
        lateinit var sdkFactory: ImaSdkFactory
        lateinit var imaSettings: ImaSdkSettings
    }

    override fun onCreate() {
        super.onCreate()
        sdkFactory = ImaSdkFactory.getInstance()

        // Configure settings early
        imaSettings = sdkFactory.createImaSdkSettings().apply {
            language = "en"
            isDebugMode = true
        }

        sdkFactory.initialize(this, imaSettings)
    }
}
...

private fun createAdsLoader(): ImaServerSideAdInsertionMediaSource.AdsLoader {
    // Reuse the exact same imaSettings from MyApplication
    return ImaServerSideAdInsertionMediaSource.AdsLoader.Builder(this, playerView)
        .setImaSdkSettings(MyApplication.imaSettings)
        .build()
}
```

### 3. Build DAI Request URIs

Create an `ImaServerSideAdInsertionUriBuilder` to build an SSAI stream URL.

```kotlin
import android.net.Uri
import androidx.media3.common.C
import androidx.media3.exoplayer.ima.ImaServerSideAdInsertionUriBuilder

// Example 1: HLS Live Stream
val hlsLiveUri: Uri = ImaServerSideAdInsertionUriBuilder()
    .setAssetKey("YOUR_LIVE_ASSET_KEY")
    .setFormat(C.CONTENT_TYPE_HLS)
    .build()

// Example 2: HLS VOD Stream
val hlsVodUri: Uri = ImaServerSideAdInsertionUriBuilder()
    .setContentSourceId("YOUR_CMS_ID")
    .setVideoId("YOUR_VIDEO_ID")
    .setFormat(C.CONTENT_TYPE_HLS)
    .build()
```

### 4. Create an ads-aware `MediaSourceFactory`

When using the ExoPlayer IMA extension, you must use the
`ImaServerSideAdInsertionMediaSource.AdsLoader` class instead of the
`ImaAdsLoader` class.

When creating the `ImaServerSideAdInsertionMediaSource.AdsLoader`, you must
provide the `PlayerView` object for rendering ad UI elements.

You must create a `DefaultMediaSourceFactory` object for your content and call
the `DefaultMediaSourceFactory.setServerSideAdInsertionMediaSourceFactory()`
method with the `ImaServerSideAdInsertionMediaSource.AdsLoader` object.

```kotlin
// Construct the AdsLoader instance
val adsLoader = ImaServerSideAdInsertionMediaSource.AdsLoader.Builder(context, playerView)
    .build()

// Instantiate the factory and bind the AdsLoader for SSAI handling
val mediaSourceFactory = DefaultMediaSourceFactory(context)
    .setServerSideAdInsertionMediaSourceFactory(adsLoader)
```

### 5. Set Up ExoPlayer

Create the ExoPlayer instance with your ad-aware media source factory and
provide the ExoPlayer instance to the `AdsLoader` for monitoring ad events.

```kotlin
// Construct the player using the configured factory
val player = ExoPlayer.Builder(context)
    .setMediaSourceFactory(mediaSourceFactory)
    .build()

// Bind the player to the AdsLoader immediately
adsLoader.setPlayer(player)
```

### 6. Load the media item

### 6. Load Media and Manage the Lifecycle

Pass your constructed SSAI URI directly into the player as a `MediaItem`.

When destroying the player activity or handling background events, you must
execute a strict teardown sequence to preserve the user's session. Call
`release()` on the `AdsLoader` before releasing the ExoPlayer instance. Capture
the returned `AdsLoader.State` object and store it securely (e.g., in a
`ViewModel`). Provide this saved state back to the `AdsLoader.Builder` during
reinitialization to ensure ad playback resumes exactly where it left off.
