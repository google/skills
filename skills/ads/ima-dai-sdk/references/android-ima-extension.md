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

    // CRITICAL: Add the Media3 IMA Extension
    implementation("androidx.media3:media3-exoplayer-ima:$latestVersion")
}
```

--------------------------------------------------------------------------------

### 2. Initialization

Configure the SDK early to minimize latency, and reuse the SDK settings.

*   **Early Warmup & Settings Reuse (Best Practice):** Call
    `ImaSdkFactory.initialize()` in your `Application.onCreate()` to preload SDK
    resources.
*   Reuse the same `ImaSdkSettings` instance when creating the
    `ImaServerSideAdInsertionMediaSource.AdsLoader.Builder.setImaSdkSettings` to
    avoid cache misses that cause latency spikes.

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
            language = YOUR_LANGUAGE_CODE // Use 2 lowercase letters to identify
                                          //   the language of your app UI.
            isDebugMode = true
        }

        sdkFactory.initialize(this, imaSettings)
    }
}
...

private ImaServerSideAdInsertionMediaSource.AdsLoader createAdsLoader() {
  val adsLoaderBuilder = new ImaServerSideAdInsertionMediaSource.AdsLoader.Builder(this, playerView);

  return adsLoaderBuilder
      .setImaSdkSettings(getImaSdkSettings())
      .build();
}
```

### 3. Build DAI Request UIRs

Create an `ImaServerSideAdInsertionUriBuilder` to build an SSAI livestream URL.

Make sure to use an `assetKey`, which is a string of alphanumeric characters as
a URL-safe base64 encoded value. For example, here are the assetKeys of DAI
sample streams: `c-rArva4ShKVIAkNfy6HUQ`,
`XYrjlG09QTa8pxAo5Fzjww`,`PSzZMzAkSXCmlJOWDmRj8Q`.

```kotlin
import android.net.Uri
import androidx.media3.common.C
import androidx.media3.exoplayer.ima.ImaServerSideAdInsertionUriBuilder

// Example 1: HLS Live Stream
val hlsLiveUri: Uri = ImaServerSideAdInsertionUriBuilder()
    .setAssetKey("YOUR_LIVE_ASSET_KEY")
    .setFormat(C.CONTENT_TYPE_DASH)
    .build()

// Example 2: HLS VOD Stream
val hlsVodUri: Uri = ImaServerSideAdInsertionUriBuilder()
    .setContentSourceId("YOUR_CMS_ID")
    .setVideoId("YOUR_VIDEO_ID")
    .setFormat(C.CONTENT_TYPE_DASH)
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
