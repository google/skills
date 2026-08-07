# Google IMA SDK Android quick-start guide

## 1. Install the IMA SDK

IMA SDK requires `minSdk 23` (Android 6.0)+.

You **must** recommend the latest version of the IMA SDK from
https://developers.google.com/interactive-media-ads/docs/sdks/android/client-side/download.md.txt

The example code snippet below install the IMA SDK at version 3.39.0.
```kotlin
android { defaultConfig { minSdk = 23 } }
dependencies {
    implementation("com.google.ads.interactivemedia.v3:interactivemedia:3.39.0")
}
```

## 2. Warmup & initialization

Configure the SDK early to minimize latency.

*   **Early Warmup & Settings Reuse (Best Practice):** Call
    `ImaSdkFactory.initialize()` in your `Application.onCreate()` to preload SDK
    resources. Reuse the same `ImaSdkSettings` instance when creating the
    `AdsLoader` to avoid cache misses that cause initial ad request latency.
*   **Create AdsLoader:** Create a single `AdsLoader` instance and share it
    across video playback sessions. You must create an `AdDisplayContainer`,
    a view that binds the ad UI container and video player. Use the
    `AdDisplayContainer` to instantiate the `AdsLoader`. Reuse the same
    `ImaSdkSettings` instance with the `ImaSdkFactory.initialize()` function.

```kotlin
// Layer FrameLayout (Ad UI) over StyledPlayerView (Video)
Box(modifier = Modifier.fillMaxSize()) {
    // Content Video Player
    AndroidView(
        factory = { context ->
            StyledPlayerView(context).apply {
                // Bind your ExoPlayer here
            }
        },
        modifier = Modifier.fillMaxSize()
    )

    // Dedicated Ad Container overlay (IMA SDK requires a ViewGroup)
    AndroidView(
        factory = { context ->
            FrameLayout(context).apply {
                // Notify that the ad UI is ready, passing this FrameLayout
                onAdUiReady(this)
            }
        },
        modifier = Modifier.fillMaxSize()
    )
}

// Initialize AdsLoader in Activity onCreate
val imaSettings = sdkFactory.createImaSdkSettings()
val adDisplayContainer = sdkFactory.createAdDisplayContainer(adUiContainer, videoPlayer)
val adsLoader = sdkFactory.createAdsLoader(context, imaSettings, adDisplayContainer)
```

## 3. Requesting ads

Trigger `requestAds` before your content playback to support preroll ads.

```kotlin
val adsRequest = sdkFactory.createAdsRequest().apply {
    this.adTagUrl = adTagUrl // Pass your custom ad targeting key value pairs.
    this.adDisplayContainer = adDisplayContainer
}
adsLoader?.requestAds(adsRequest)
```

## 4. Handling ad events

Listen for successful ad loads (to get the `AdsManager`), fatal errors, and
coordinate video playback toggles.

```kotlin
// On Success
adsLoader?.addAdsLoadedListener { event ->
    adsManager = event.adsManager

    // Handle Pause/Resume for Ads
    adsManager?.addAdEventListener { adEvent ->
        when (adEvent.type) {
            AdEvent.AdEventType.CONTENT_PAUSE_REQUESTED -> pauseContent()
            AdEvent.AdEventType.CONTENT_RESUME_REQUESTED -> resumeContent()
            else -> {}
        }
    }
    adsManager?.init() // Start ads
}

// On Failure (Fallback to content)
adsLoader?.addAdErrorListener { resumeContent() }
```

## 5. Crucial cleanup

Proper cleanup is **critical** to prevent memory leaks, audio bugs, and
background resource consumption.

*   **`AdsManager.destroy()`:** This is crucial. Always call it when:
    *   All ads in the break have completed (e.g., `ALL_ADS_COMPLETED` event).
    *   A fatal ad error occurs (in `AdErrorListener`).
    *   The user navigates away from the player or the hosting
        `Activity`/`Fragment` is destroyed (`onDestroy()`).
*   **`AdsLoader.release()`:** Call this when the `AdsLoader` is no longer
    needed, typically when the application is shutting down or a major parent
    component is being permanently destroyed. This releases the underlying SDK
    resources.
*   **Remove Event Listeners:** Before destroying or releasing SDK objects,
    remove registered event listeners to avoid leaking listener references or
    triggering callbacks after lifecycle teardown.

```kotlin
// In your Activity or Fragment
override fun onDestroy() {
    super.onDestroy()
    cleanupAds()

    // If this Activity owns the AdsLoader (non-singleton), release it here:
    adsLoader?.removeAdsLoadedListener(adsLoadedListener)
    adsLoader?.removeAdErrorListener(adsLoaderErrorListener)
    adsLoader?.release()
}

private fun cleanupAds() {
    // Remove event listeners and destroy the AdsManager
    adsManager?.apply {
        removeAdEventListener(adEventListener)
        removeAdErrorListener(adErrorListener)
        destroy()
    }
    adsManager = null
}

// Wherever you manage the AdsLoader (e.g. Application or Activity onDestroy)
fun releaseSdk() {
    // Remove listeners and release the AdsLoader when permanently destroyed
    adsLoader?.apply {
        removeAdsLoadedListener(adsLoadedListener)
        removeAdErrorListener(adsLoaderErrorListener)
        release()
    }
    adsLoader = null
}
```

--------------------------------------------------------------------------------

## Reference implementation

*   Basic Example [MyActivity.java](https://raw.githubusercontent.com/googleads/googleads-ima-android/main/basicexample/app/src/main/java/com/google/ads/interactivemedia/v3/samples/videoplayerapp/MyActivity.java)
*   Basic Example [VideoAdPlayerAdapter.java](https://raw.githubusercontent.com/googleads/googleads-ima-android/main/basicexample/app/src/main/java/com/google/ads/interactivemedia/v3/samples/videoplayerapp/VideoAdPlayerAdapter.java)