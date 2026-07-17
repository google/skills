# Google IMA SDK DAI - Pod Serving Integration Guide

In Pod Serving, you use Google DAI with a third-party manifest manipulator or video technology partner (VTP). Google DAI builds the ad pods, but your manifest manipulator stitches the ad pods with content to give you a final, single ad-stitched stream.

The SDK registers a session, receives a `streamId`, and you use this ID to construct the stream URL that your player will play.

--------------------------------------------------------------------------------

## Key Differences: Live vs. VOD Metadata Loading

*   **Live Linear Pod Serving:** Relies on in-manifest timed metadata (ID3 or DASH emsg tags embedded in the live stream) to report ad events.
*   **VOD Pod Serving:** Requires calling `streamManager.loadStreamMetadata()` (Web) or `streamManager.loadThirdPartyStream()` (Android/iOS) because VOD streams do NOT contain in-manifest timed metadata tags. Calling `loadStreamMetadata()` immediately after initiating playback or loading the VTP URL fetches out-of-band ad break cue points from Google DAI servers.

--------------------------------------------------------------------------------

## 1. Web Integration

### A. Requesting the Stream

When requesting a Pod Serving stream on Web, create either:
*   `PodStreamRequest` (for Live): Set `networkCode` and `customAssetKey`.
*   `PodVodStreamRequest` (for VOD): Set `networkCode` and `cmsId`/`videoId` (or `contentSourceId`/`videoId`).

```typescript
let streamManager: google.ima.dai.api.StreamManager;

// 1. Live Pod Stream Request
function requestLivePodStream(networkCode: string, customAssetKey: string): void {
  const streamRequest = new google.ima.dai.api.PodStreamRequest();
  streamRequest.networkCode = networkCode;
  streamRequest.customAssetKey = customAssetKey;
  streamManager.requestStream(streamRequest);
}

// 2. VOD Pod Stream Request
function requestVODPodStream(networkCode: string, cmsId: string, videoId: string): void {
  const streamRequest = new google.ima.dai.api.PodVodStreamRequest();
  streamRequest.networkCode = networkCode;
  streamRequest.contentSourceId = cmsId;
  streamRequest.videoId = videoId;
  streamManager.requestStream(streamRequest);
}
```

### B. Handling `STREAM_INITIALIZED` & Out-of-Band Metadata Loading

1. Listen for the `STREAM_INITIALIZED` event to obtain `event.getStreamData().streamId`.
2. Send the `streamId` to your third-party manifest stitcher (VTP) to assemble the playback URL.
3. For VOD, call `streamManager.loadStreamMetadata()` immediately after retrieving the VTP manifest URL to fetch ad cue points out-of-band.

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

  // 1. Send streamId to your VTP / manifest manipulator
  getVtpStreamUrl({ streamId: streamId }).then((vtpManifestUrl: string) => {
    // 2. For VOD: Call loadStreamMetadata() immediately to fetch ad cue points out-of-band
    if (isVod) {
      streamManager.loadStreamMetadata();
    }

    // 3. Pass manifest URL to video player
    videoElement.src = vtpManifestUrl;
    videoElement.play();
  });
}
```

### C. Segment Redirects Troubleshooting

If ad segments return black screens or fail during Pod Serving:
*   **Automatic 302 Redirects:** Verify that your video player or browser automatically follows HTTP 302 redirects issued by segment redirect URLs.
*   **Authentication & Credentials:** Set `withCredentials = true` on your player's HTTP request config if redirects require session cookies or authentication headers.
*   **Network Diagnostics:** Inspect browser Network Inspector logs for 302 redirect status responses, CORS preflight failures (`OPTIONS`), or missing Access-Control-Allow-Origin headers on ad CDN servers.

--------------------------------------------------------------------------------

## 2. Android Integration

*Note: Media3 SSAI extension does not support Pod Serving out-of-the-box. You must use the Custom Player integration method.*

### A. Requesting the Stream

```kotlin
val request: StreamRequest = if (isLive) {
  sdkFactory.createPodStreamRequest(NETWORK_CODE, CUSTOM_ASSET_KEY, API_KEY)
} else {
  sdkFactory.createPodVodStreamRequest(NETWORK_CODE)
}

request.format = StreamFormat.HLS // or StreamFormat.DASH
adsLoader.requestStream(request)
```

### B. Handling `STREAM_INITIALIZED` & Playback

Listen for `STREAM_INITIALIZED` (or `onAdsManagerLoaded`) to obtain `streamId`, send it to your third-party manifest stitcher, and load the stream URL.

```kotlin
override fun onAdsManagerLoaded(event: AdsManagerLoadedEvent) {
  val streamManager = event.streamManager
  streamManager.init()
  
  // 1. Extract streamId from StreamManager upon initialization
  val streamId = streamManager.streamId

  if (isLive) {
    // 2a. Send streamId to VTP and play live stream
    val liveStreamUrl = getVtpLiveStreamURL(streamId)
    videoPlayer.setStreamUrl(liveStreamUrl)
    videoPlayer.play()
  } else {
    // 2b. Send streamId to VTP and load VOD stream via loadThirdPartyStream()
    val vodStreamUrl = getVtpVodStreamURL(streamId)
    // loadThirdPartyStream() automatically retrieves out-of-band ad metadata and triggers player load
    streamManager.loadThirdPartyStream(vodStreamUrl, emptyList())
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
