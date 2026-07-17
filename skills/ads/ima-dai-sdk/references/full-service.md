# Google IMA SDK DAI - Full Service Integration Guide

In a Full Service integration, Google Ad Manager handles the entire server-side
ad insertion (SSAI) workflow, including selecting ads, transcoding them, and
stitching them directly into your video manifest. The SDK requests the stream
directly from Google DAI servers and returns a fully stitched stream URL (or
handles playback internally).

--------------------------------------------------------------------------------

## 1. Web Integration

### A. Requesting a Stream

You can request either a Live stream (requires `assetKey`) or a VOD stream
(requires `contentSourceId`/CMS ID and `videoId`).

```typescript
const videoElement = document.getElementById('video') as HTMLVideoElement;
const adUiElement = document.getElementById('adUi') as HTMLElement;
let streamManager: google.ima.dai.api.StreamManager;

function initializeDAI(): void {
  streamManager = new google.ima.dai.api.StreamManager(videoElement, adUiElement);
  setupStreamManagerListeners();
}

function requestLiveStream(assetKey: string, networkCode: string, apiKey?: string): void {
  const streamRequest = new google.ima.dai.api.LiveStreamRequest();
  streamRequest.assetKey = assetKey;
  streamRequest.networkCode = networkCode;

  if (apiKey) {
    streamRequest.apiKey = apiKey;
  }
  streamManager.requestStream(streamRequest);
}

function requestVODStream(cmsId: string, videoId: string, networkCode: string, apiKey?: string): void {
  const streamRequest = new google.ima.dai.api.VODStreamRequest();
  streamRequest.contentSourceId = cmsId;
  streamRequest.videoId = videoId;
  streamRequest.networkCode = networkCode;
  if (apiKey) {
    streamRequest.apiKey = apiKey;
  }
  streamManager.requestStream(streamRequest);
}
```

### B. Handling Stream Events

Listen for the `LOADED` event to get the stitched stream URL, and `ERROR` to
fallback to a backup stream.

```typescript
function setupStreamManagerListeners(): void {
  streamManager.addEventListener(
    google.ima.dai.api.StreamEvent.Type.LOADED,
    onStreamLoaded,
    false
  );
  streamManager.addEventListener(
    google.ima.dai.api.StreamEvent.Type.ERROR,
    onStreamError,
    false
  );
}

function onStreamLoaded(e: google.ima.dai.api.StreamEvent): void {
  const streamData = e.getStreamData();
  if (streamData) {
    const streamUrl = streamData.url;
    playStream(streamUrl); // Load into your player (hls.js, dash.js, etc.)
  }
}

function onStreamError(e: google.ima.dai.api.StreamEvent): void {
  const streamData = e.getStreamData();
  if (streamData) {
    console.error('DAI Error:', streamData.errorMessage);
  }
  playBackupStream(); // Fallback to unmonetized content
}
```

--------------------------------------------------------------------------------

## 2. Android Integration

You can integrate using the Media3 ExoPlayer SSAI extension (recommended) or
using custom player APIs.

### A. Media3 ExoPlayer SSAI Extension (Recommended)

The `media3-exoplayer-ima` extension handles player setup and metadata
extraction automatically.

```kotlin
private fun initializePlayer() {
  // 1. Create the SSAI AdsLoader
  adsLoader = ImaServerSideAdInsertionMediaSource.AdsLoader.Builder(this, playerView).build()

  // 2. Set up MediaSource Factory with SSAI support
  val mediaSourceFactory = DefaultMediaSourceFactory(this)
  val adsMediaSourceFactory =
      ImaServerSideAdInsertionMediaSource.Factory(adsLoader, mediaSourceFactory)
  mediaSourceFactory.setServerSideAdInsertionMediaSourceFactory(adsMediaSourceFactory)

  // 3. Create ExoPlayer
  player = ExoPlayer.Builder(this).setMediaSourceFactory(mediaSourceFactory).build()
  playerView.player = player
  adsLoader.setPlayer(player)

  // 4. Build SSAI URI (Live example)
  val ssaiUri = ImaServerSideAdInsertionUriBuilder()
      .setAssetKey("YOUR_ASSET_KEY")
      .setFormat(androidx.media3.common.C.CONTENT_TYPE_HLS)
      .build()

  val ssaiMediaItem = MediaItem.fromUri(ssaiUri)
  player.setMediaItem(ssaiMediaItem)
  player.prepare()
  player.play()
}
```

### B. Custom Player Integration

If not using the extension, you must implement `VideoStreamPlayer` and request
the stream manually.

```kotlin
val sdkFactory = ImaSdkFactory.getInstance()
val displayContainer =
    ImaSdkFactory.createStreamDisplayContainer(adUiContainer, videoStreamPlayer)
val adsLoader = sdkFactory.createAdsLoader(context, settings, displayContainer)

adsLoader.addAdsLoadedListener { event ->
  val streamManager = event.streamManager
  streamManager.init() // SDK automatically calls VideoStreamPlayer.loadUrl()
}

val request =
    sdkFactory.createVodStreamRequest("CMS_ID", "VIDEO_ID", null, "NETWORK_CODE")
adsLoader.requestStream(request)
```

The SDK will call your `VideoStreamPlayer.loadUrl(url, subtitles)` where you
must load the URL into your player.

--------------------------------------------------------------------------------

## 3. iOS/tvOS Integration (AVPlayer)

### A. Requesting the Stream

Use `IMALiveStreamRequest` or `IMAVODStreamRequest` and wrap `AVPlayer` with
`IMAAVPlayerVideoDisplay`.

```swift
override func viewDidLoad() {
  super.viewDidLoad()
  setupPlayer()
  adsLoader = IMAAdsLoader(settings: nil)
  adsLoader?.delegate = self
  adDisplayContainer = IMAAdDisplayContainer(adContainer: videoView, viewController: self, companionSlots: nil)
  imaVideoDisplay = IMAAVPlayerVideoDisplay(avPlayer: videoPlayer) // Handles HLS ID3 automatically
}

func requestStream() {
  if isLive {
    let request = IMALiveStreamRequest(assetKey: "YOUR_ASSET_KEY", networkCode: "YOUR_NETWORK_CODE", adDisplayContainer: adDisplayContainer!, videoDisplay: imaVideoDisplay, userContext: nil)
    adsLoader?.requestStream(with: request)
  } else {
    let request = IMAVODStreamRequest(contentSourceID: "YOUR_CMS_ID", videoID: "YOUR_VIDEO_ID", networkCode: "YOUR_NETWORK_CODE", adDisplayContainer: adDisplayContainer!, videoDisplay: imaVideoDisplay, userContext: nil)
    adsLoader?.requestStream(with: request)
  }
}
```

### B. Handling Stream Load

In `IMAAdsLoaderDelegate`, initialize the `StreamManager`. For Full Service, the
SDK automatically loads the stream into the `AVPlayer` and starts playback.

```swift
func adsLoader(_ loader: IMAAdsLoader, adsLoadedWith adsLoadedData: IMAAdsLoadedData) {
  streamManager = adsLoadedData.streamManager
  streamManager?.delegate = self
  streamManager?.initialize(with: nil)
}
```

--------------------------------------------------------------------------------

## 4. Passing Custom Parameters (Targeting)

You can pass custom parameters (such as targeting key-values) to the ad request
by setting ad tag parameters on the stream request.

### A. Web (TypeScript)

Set `adTagParameters` on the `StreamRequest` object.

```typescript
function requestLiveStreamWithTargeting(assetKey: string, networkCode: string): void {
  const streamRequest = new google.ima.dai.api.LiveStreamRequest();
  streamRequest.assetKey = assetKey;
  streamRequest.networkCode = networkCode;

  // Pass custom parameters
  streamRequest.adTagParameters = {
    'genre': 'action',
    'age': '25'
  };

  streamManager.requestStream(streamRequest);
}
```

### B. Android (Kotlin)

#### Using Media3 ExoPlayer SSAI Extension

Use `setAdTagParameters` on `ImaServerSideAdInsertionUriBuilder`.

```kotlin
val adTagParameters = mapOf("genre" to "action", "age" to "25")
val ssaiUri = ImaServerSideAdInsertionUriBuilder()
    .setAssetKey("YOUR_ASSET_KEY")
    .setFormat(androidx.media3.common.C.CONTENT_TYPE_HLS)
    .setAdTagParameters(adTagParameters)
    .build()
```

### C. iOS/tvOS (Swift)

Set `adTagParameters` on the `IMAStreamRequest` object.

```swift
func requestStreamWithTargeting() {
  let request = IMALiveStreamRequest(
    assetKey: "YOUR_ASSET_KEY",
    networkCode: "YOUR_NETWORK_CODE",
    adDisplayContainer: adDisplayContainer!,
    videoDisplay: imaVideoDisplay,
    userContext: nil
  )

  // Pass custom parameters
  request.adTagParameters = [
    "genre": "action",
    "age": "25"
  ]

  adsLoader?.requestStream(with: request)
}
```
