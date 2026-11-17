# Google IMA DAI SDK Android - ExoPlayer IMA Extension Guide

Use the `ImaServerSideAdInsertionMediaSource` class of the ExoPlayer IMA
extension (`androidx.media3:media3-exoplayer-ima`) to request livestream or VOD
stream from Google full-service DAI.

## Table of Contents

*   [Dependencies](#dependencies) (Line 21)
*   [IMA DAI SDK required permissions](#ima-dai-sdk-required-permissions)
    (Line 57)
*   [UI Setup](#ui-setup) (Line 66)
*   [Early SDK Initialization](#early-sdk-initialization) (Line 89)
*   [Create a reusable AdsLoader](#create-a-reusable-adsloader) (Line 104)
*   [Listen to stream events and ad events](#listen-to-stream-events-and-ad-events)
    (Line 123)
*   [Initialize ExoPlayer with SSAI MediaSource Factory](#initialize-exoplayer-with-ssai-mediasource-factory)
    (Line 155)
*   [Request a livestream](#request-a-livestream) (Line 180)
    *   [Video on Demand (VOD) Streams](#video-on-demand-vod-streams) (Line 202)
*   [Clean up SDK resources](#clean-up-sdk-resources) (Line 227)
*   [Reference implementation](#reference-implementation) (Line 240)

## Dependencies

Add the Media3 ExoPlayer IMA extension in `build.gradle`. This component
automatically imports the IMA DAI SDK.

```groovy
apply plugin: "com.android.application"

android {
    compileOptions {
        // Required by IMA SDK v3.37.0+
        coreLibraryDesugaringEnabled = true
    }

    defaultConfig {
        minSdkVersion(23)
    }
}

repositories {
    google()
    mavenCentral()
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
    implementation("androidx.media3:media3-ui")
    implementation("androidx.media3:media3-exoplayer")
    implementation("androidx.media3:media3-exoplayer-hls")
    implementation("androidx.media3:media3-exoplayer-dash")
    implementation("androidx.media3:media3-exoplayer-ima")
}
```

Use latest versions as posted on
[Media3](https://developer.android.com/jetpack/androidx/releases/media3.md.txt)

## IMA DAI SDK required permissions

Ensure to declare the permissions required by the IMA DAI SDK in
`AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE"/>
```

## UI Setup

Place the `PlayerView` inside the layout. For example:

```xml
<androidx.media3.ui.PlayerView android:id="@+id/player_view" />
```

If Jetpack Compose is used, create a `PlayerView` wrapping an exoplayer:

```kotlin
AndroidView(
  factory = { ctx ->
    PlayerView(ctx).apply {
      player = exoPlayer
    }
  },
  update = { playerView ->
    playerView.player = exoPlayer
  }
)
```

## Early SDK Initialization

Initialize the IMA SDK as early as possible in the app lifecycle (such as inside
`onCreate()` of `Application` or the main `Activity`) to minimize stream load
times:

Create a `ImaSdkSettings` object to initialize the SDK. Save it for reuse with
`ImaServerSideAdInsertionMediaSource`.

```kotlin
val imaSdkFactory = ImaSdkFactory.getInstance()
val sharedImaSdkSettings: ImaSdkSettings = imaSdkFactory.createImaSdkSettings()
imaSdkFactory.initialize(this, sharedImaSdkSettings)
```

## Create a reusable `AdsLoader`

Provide the `androidx.media3.ui.PlayerView` to build a
`ImaServerSideAdInsertionMediaSource.AdsLoader`.

Provide the same `ImaSdkSettings` from
`ImaSdkFactory.getInstance().initialize()` the previous step.

```kotlin
val playerView = findViewById(R.id.player_view)
val adsLoaderBuilder =
    ImaServerSideAdInsertionMediaSource.AdsLoader.Builder(this, playerView)

val adsLoader = adsLoaderBuilder
    .setAdEventListener(buildAdEventListener())
    .setImaSdkSettings(sharedImaSdkSettings)
    .build()
```

## Listen to stream events and ad events

Implement DAI stream event handling by creating an `AdEventListener`. Provide
this listener to the `AdsLoader` builder during instantiation.

```kotlin
val adEventListener = AdEvent.AdEventListener { event ->
    when (event.type) {
      AdEvent.AdEventType.LOADED,
      AdEvent.AdEventType.CUEPOINTS_CHANGED,
      AdEvent.AdEventType.AD_BREAK_STARTED,
      AdEvent.AdEventType.AD_BREAK_ENDED,
      AdEvent.AdEventType.AD_PERIOD_STARTED,
      AdEvent.AdEventType.AD_PERIOD_ENDED,
      AdEvent.AdEventType.STARTED,
      AdEvent.AdEventType.FIRST_QUARTILE,
      AdEvent.AdEventType.MIDPOINT,
      AdEvent.AdEventType.THIRD_QUARTILE,
      AdEvent.AdEventType.COMPLETED,
      AdEvent.AdEventType.PAUSED,
      AdEvent.AdEventType.RESUMED,
      AdEvent.AdEventType.SKIPPABLE_STATE_CHANGED,
      AdEvent.AdEventType.SKIPPED,
      AdEvent.AdEventType.CLICKED -> Log.i(LOG_TAG, "Ad event: ${event.type}")
      AdEvent.AdEventType.AD_PROGRESS -> {
        // High-frequency event fired periodically during ad playback; ignore to prevent log spam
      }
      else -> Log.i(LOG_TAG, "Unhandled ad event: ${event.type}")
    }
  }
```

## Initialize ExoPlayer with SSAI MediaSource Factory

Create `DefaultMediaSourceFactory` and
`ImaServerSideAdInsertionMediaSource.Factory` objects to build the `ExoPlayer`
instance.

Ensure to call `AdsLoader.setPlayer()`, providing the `ExoPlayer` instance
above, before calling `ExoPlayer.setMediaItem` with a
`ImaServerSideAdInsertionUri`.

```kotlin
val dataSourceFactory: DataSource.Factory = DefaultDataSource.Factory(this)
val mediaSourceFactory = DefaultMediaSourceFactory(dataSourceFactory)

val adsMediaSourceFactory =
    ImaServerSideAdInsertionMediaSource.Factory(adsLoader, mediaSourceFactory)

mediaSourceFactory.setServerSideAdInsertionMediaSourceFactory(adsMediaSourceFactory)

player = ExoPlayer.Builder(this)
    .setMediaSourceFactory(mediaSourceFactory)
    .build()
adsLoader.setPlayer(player)
```

## Request a livestream

Build a live stream URI using `ImaServerSideAdInsertionUriBuilder` with the
asset key:

```kotlin
val liveStreamUri: Uri = ImaServerSideAdInsertionUriBuilder()
      .setNetworkCode(<NETWORK_CODE_PLACEHOLDER>)
      .setAssetKey(<ASSET_KEY_PLACEHOLDER>)
      .setFormat(androidx.media3.common.C.CONTENT_TYPE_HLS)
      .build()

val liveStreamMediaItem: MediaItem = MediaItem.fromUri(liveStreamUri)
player.setMediaItem(liveStreamMediaItem)
```

Provide the following parameters:

*   **<NETWORK_CODE_PLACEHOLDER>**: The Google Ad Manager network code.
*   **<ASSET_KEY_PLACEHOLDER>**: The livestream asset key configured in Google
    Ad Manager.

### Video on Demand (VOD) Streams

Build a VOD stream URI using `ImaServerSideAdInsertionUriBuilder` with content
source ID (CMS ID) and video ID:

```kotlin
val vodStreamUri: Uri = ImaServerSideAdInsertionUriBuilder()
      .setNetworkCode(<NETWORK_CODE_PLACEHOLDER>)
      .setContentSourceId(<CONTENT_SOURCE_ID_PLACEHOLDER>)
      .setVideoId(<VIDEO_ID_PLACEHOLDER>)
      .setFormat(androidx.media3.common.C.CONTENT_TYPE_HLS)
      .build()
val vodStreamItem: MediaItem = MediaItem.fromUri(vodStreamUri)
player.setMediaItem(vodStreamItem)
```

Provide the following parameters:

*   **<NETWORK_CODE_PLACEHOLDER>**: The Google Ad Manager network code.
*   **<CONTENT_SOURCE_ID_PLACEHOLDER>**: The CMS ID in Google Ad Manager.
*   **<VIDEO_ID_PLACEHOLDER>**: The video ID in the CMS.

For testing purposes, use values of DAI sample streams from
https://developers.google.com/ad-manager/dynamic-ad-insertion/streams.md.txt?utm_source=agent-skills&utm_medium=content&utm_campaign=adr-ss-ai&utm_content=ima-dai-sdk

## Clean up SDK resources

Call `ImaServerSideAdInsertionMediaSource.AdsLoader.release()` when releasing
the player or handling stream errors to tear down active DAI sessions.

Save the returned `AdsLoader.State` object to restore player during
configuration changes like screen rotations.

```kotlin
adsLoader?.setPlayer(null)
adsLoaderState = adsLoader?.release()
```

## Reference implementation

*   [ExoPlayerExample/app/src/main/res/layout/activity_my.xml](https://raw.githubusercontent.com/googleads/googleads-ima-android-dai/refs/heads/main/ExoPlayerExample/app/src/main/res/layout/activity_my.xml)
*   [ExoPlayerExample/app/src/main/java/com/google/ads/interactivemedia/v3/samples/videoplayerapp/MyActivity.java](https://raw.githubusercontent.com/googleads/googleads-ima-android-dai/refs/heads/main/ExoPlayerExample/app/src/main/java/com/google/ads/interactivemedia/v3/samples/videoplayerapp/MyActivity.java)
