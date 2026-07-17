# Google IMA SDK DAI - Pod Serving Integration Guide

In Pod Serving, you use Google DAI with a third-party manifest manipulator or
video technology partner (VTP). Google DAI builds the ad pods, but your manifest
manipulator stitches the ad pods with content to give you a final, single ad
stitched stream.

The SDK registers a session, receives a `streamId`, and you use this ID to
construct the stream URL that your player will play.

--------------------------------------------------------------------------------

## 1. Web Integration

### A. Requesting the Stream

Use `PodStreamRequest` (Livestream) or `PodVodStreamRequest` (VOD).

```typescript
let streamManager: google.ima.dai.api.StreamManager;

function requestStream(): void {
    const streamRequest = new google.ima.dai.api.PodStreamRequest();
    streamRequest.networkCode = 'YOUR_NETWORK_CODE';
    streamRequest.customAssetKey = 'YOUR_CUSTOM_ASSET_KEY';
    streamManager.requestStream(streamRequest);

    // For VOD stream, use the code lines below
    // const streamRequest = new google.ima.dai.api.PodVodStreamRequest();
    // streamRequest.networkCode = 'YOUR_NETWORK_CODE';
    // streamManager.requestStream(streamRequest);
  }
```

### B. Handling `STREAM_INITIALIZED` & Playback

Listen for `STREAM_INITIALIZED` to get the `streamId`, build the URL, and play.

```typescript
streamManager.addEventListener(
  google.ima.dai.api.StreamEvent.Type.STREAM_INITIALIZED,
  onStreamInitialized,
  false
);

function onStreamInitialized(e: google.ima.dai.api.StreamEvent): void {
  const streamData = e.getStreamData();
  if (!streamData) return;

  const streamId = streamData.streamId;
    const url = YOUR_STREAM_URL.replace('[[STREAMID]]', streamId);
    playStream(url);
}
```

For VOD, you must pass the `streamId` to your manifest manipulator, call
`loadStreamMetadata()` to fetch the ad cue points, and retrieve or construct the
stream URL to the video player.

```typescript
function onStreamInitializedVOD(e: google.ima.dai.api.StreamEvent): void {
  const streamData = e.getStreamData();
  if (!streamData) return;

  const streamId = streamData.streamId;

  // 1. Send the DAI stream ID to your video stitcher to retrieve a stream URL
  getStreamUrl({ streamId: streamId }).then((streamUrl: string) => {
    // 2. Load the ad metadata from Google
    streamManager.loadStreamMetadata();

    // 3. Play the stream
    playStream(streamUrl);
  });
}
```

--------------------------------------------------------------------------------

## 2. Android Integration

*Note: Media3 SSAI extension does not support Pod Serving out-of-the-box. You
must use the Custom Player integration method.*

### A. Requesting the Stream

```kotlin
val request: StreamRequest =
  sdkFactory.createPodStreamRequest(NETWORK_CODE, CUSTOM_ASSET_KEY, API_KEY)
  // or VOD: sdkFactory.createPodVodStreamRequest(NETWORK_CODE)

request.format = StreamFormat.HLS // or DASH
adsLoader.requestStream(request)
```

### B. Handling Load & Playback

Extract the `streamId`, construct the URL, and load it. For Live, play directly.
For VOD, load via `StreamManager`.

```kotlin
override fun onAdsManagerLoaded(event: AdsManagerLoadedEvent) {
  val streamManager = event.streamManager
  streamManager.init()
  val streamId = streamManager.streamId

  if (isLive) {
    val liveStreamUrl = getLiveStreamURL(streamId)
    videoPlayer.setStreamUrl(liveStreamUrl)
    videoPlayer.play() // SDK does NOT call VideoStreamPlayer.loadUrl for live pod serving
  } else {
    val vodStreamUrl = getVODStreamURL(streamId)
    // Note: Android SDK does not have a separate loadStreamMetadata() method.
    // loadThirdPartyStream() automatically retrieves ad metadata and loads the stream.
    streamManager.loadThirdPartyStream(vodStreamUrl, emptyList()) // Triggers VideoStreamPlayer.loadUrl()
  }
}
```

--------------------------------------------------------------------------------

## 3. iOS/tvOS Integration

### A. Requesting the Stream

Use `IMAPodStreamRequest` or `IMAPodVODStreamRequest`.

```swift
func requestPodStream() {
  if isLive {
    let request = IMAPodStreamRequest(networkCode: "YOUR_NETWORK_CODE", customAssetKey: "YOUR_CUSTOM_ASSET_KEY", adDisplayContainer: adDisplayContainer!, videoDisplay: imaVideoDisplay, pictureInPictureProxy: nil, userContext: nil)
    adsLoader?.requestStream(with: request)
  } else {
    let request = IMAPodVODStreamRequest(networkCode: "YOUR_NETWORK_CODE", adDisplayContainer: adDisplayContainer!, videoDisplay: imaVideoDisplay, pictureInPictureProxy: nil, userContext: nil)
    adsLoader?.requestStream(with: request)
  }
}
```

### B. Handling Load & Playback

```swift
func adsLoader(_ loader: IMAAdsLoader, adsLoadedWith adsLoadedData: IMAAdsLoadedData) {
  streamManager = adsLoadedData.streamManager
  streamManager?.delegate = self
  streamManager?.initialize(with: nil)

  guard let streamID = streamManager?.streamId else { return }
  let urlString = getStreamUrl(streamId: streamID)
  guard let streamUrl = URL(string: urlString) else { return }

  if isLive {
    imaVideoDisplay.loadStream(streamUrl, withSubtitles: [])
    imaVideoDisplay.play()
  } else {
    streamManager?.loadThirdPartyStream(streamUrl, streamSubtitles: [])
  }
}
```
