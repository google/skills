---
name: ima-dai-sdk
description: >-
  Integrates the Google Interactive Media Ads (IMA) DAI SDK into websites, web apps,
  mobile apps, or TV apps for Google Dynamic Ad Insertion (DAI) with HLS or DASH streams.

  Use when:
  - Integrating the IMA DAI SDK for Google Dynamic Ad Insertion (DAI), Server-Side Ad Insertion (SSAI), Full Service DAI, or DAI Pod Serving redirect.
  - Requesting HLS (.m3u8) or MPEG-DASH (.mpd) DAI streams on Web, Android, iOS/tvOS, or Roku platforms.

  Don't use for:
  - Client-side ad insertion (CSAI) with VAST and VMAP requests (use the `ima-sdk-client-side` skill instead).

license: Apache-2.0
metadata:
  author: Google LLC
  version: "1.0.0"
---

# IMA SDK DAI Basics

The Google IMA DAI SDK lets you load a single stream containing both content and
ads into websites, apps, TVs and other digital platforms. Use an IMA SDK to
request an HLS or MPEG DASH stream from a video stitcher or stream origin.

## Mandatory Prerequisites

Correct integration requires identifying the streaming protocol, DAI type, and target platform up front. Review the relevant reference guides below to ensure proper setup:

1.  **Identify the Streaming Protocol:**

    *   **HLS (HTTP Live Streaming):** Stream URLs end in `.m3u8`. Read the [HLS Guide](references/hls.md).
    *   **MPEG DASH:** Stream URLs end in `.mpd`. Read the [DASH Guide](references/dash.md).

2.  **Identify the DAI Type:**

    *   **Full Service DAI:** Request a Google DAI stream URL using an `assetKey` (Live) or `cmsId`/`videoId` (VOD). Read the [Full Service Guide](references/full-service.md).
    *   **Pod Serving DAI:** Request a Google DAI `streamId` using an `assetKey`/`customAssetKey` (linear stream, livestream) or `cmsId`/`videoId` (VOD). Construct a playback stream URL with the `streamId`. Read the [Pod Serving Guide](references/pod-serving.md).

3.  **Identify the Target Platform:**

    *   **Web/NodeJs/ReactJs:** Native JavaScript/TypeScript environments (browsers, Smart TVs). Read the [Web Guide](references/web.md).
    *   **Android/AndroidTV:** Native Java/Kotlin environments. Read the [Android Guide](references/android-ima-extension.md).
    *   **iOS/tvOS:** Native Swift/Objective-C environments. Read the [iOS/tvOS Guide](references/ios-tvos.md).
    *   **Roku:** Native BrightScript/SceneGraph environments. Read the [Roku Guide](references/roku.md).

--------------------------------------------------------------------------------

## Quick Start (General Workflow)

For all apps, the integration follows this general logical flow:

1.  Import the SDK: Set up prerequisites and dependencies.
2.  Initialization: Early setup, Warmup, Settings Configuration, and Ad UI Setup.
3.  Ad Stream request: Create the livestream or VOD stream request.
4.  Ad Stream Load Success/Failure: Handle the stream load event to obtain the `StreamManager` or handle early fatal errors.
5.  Stream Playback Events: Listen to timed metadata events for forwarding ID3/emsg tags to the IMA DAI SDK, and handle non-fatal LOG events or fatal stream errors.
6.  Cleanup: Properly destroy the `StreamManager` to release resources and prevent memory leaks.

### Basic Web Live Stream Integration Example

```typescript
import { LiveStreamRequest, StreamManager, StreamEvent } from '@google/ima-dai-sdk';

const videoElement = document.getElementById('video-player') as HTMLVideoElement;
const adUiElement = document.getElementById('ad-ui') as HTMLElement;

// 1. Initialize StreamManager
const streamManager = new StreamManager(videoElement, adUiElement);

// 2. Listen for stream loaded event
streamManager.addEventListener(
  StreamEvent.Type.LOADED,
  (event: StreamEvent) => {
    const streamUrl = event.getStreamData().url;
    videoElement.src = streamUrl;
    videoElement.play();
  }
);

// 3. Request live stream
const streamRequest = new LiveStreamRequest();
streamRequest.assetKey = 'YOUR_ASSET_KEY';
streamRequest.networkCode = 'YOUR_NETWORK_CODE';
streamManager.requestStream(streamRequest);
```

For detailed, platform-specific implementation details, refer to the guides in the **Mandatory Prerequisites** section.

