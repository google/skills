# Google IMA SDK DAI - Web Integration Guide

This guide covers the general lifecycle and integration steps for the Google IMA
DAI SDK on the Web (HTML5/JavaScript).

For protocol-specific details, see [HLS Guide](hls.md) and
[DASH Guide](dash.md). For DAI workflows, see
[Full Service Guide](full-service.md) and [Pod Serving Guide](pod-serving.md).

--------------------------------------------------------------------------------

## 1. SDK Setup

Include the IMA DAI SDK script in your HTML:

```html
<script type="text/javascript" src="//imasdk.googleapis.com/js/sdkloader/ima3_dai.js"></script>
```

--------------------------------------------------------------------------------

## 2. Initialization

Instantiate the `StreamManager` early. It requires the content video element and
the Ad UI container element (which overlays the video).

```javascript
const videoElement = document.getElementById('video');
const adUiElement = document.getElementById('adUi');
let streamManager;

function initializeDAI() {
  // The Ad UI element must be positioned directly over the video element
  streamManager = new google.ima.dai.api.StreamManager(videoElement, adUiElement);
  setupStreamManagerListeners();
}
```

--------------------------------------------------------------------------------

## 3. Event Handling

You must listen for lifecycle events to manage playback and UI.

```javascript
function setupStreamManagerListeners() {
  // Stream loaded (Full Service)
  streamManager.addEventListener(google.ima.dai.api.StreamEvent.Type.LOADED, onStreamLoaded, false);

  // Stream initialized (Pod Serving)
  streamManager.addEventListener(google.ima.dai.api.StreamEvent.Type.STREAM_INITIALIZED, onStreamInitialized, false);

  // Error handling
  streamManager.addEventListener(google.ima.dai.api.StreamEvent.Type.ERROR, onStreamError, false);

  // Ad Break events
  streamManager.addEventListener(
      [
        google.ima.dai.api.StreamEvent.Type.AD_BREAK_STARTED,
        google.ima.dai.api.StreamEvent.Type.AD_BREAK_ENDED
      ],
      onAdBreakEvent,
      false
  );
}
```

--------------------------------------------------------------------------------

## 4. Ad Break UI Management

During ad breaks, you **must** disable custom player controls (seeking, pausing,
etc.) to prevent users from bypassing ads, and display the Ad UI overlay.

```javascript
function onAdBreakEvent(e) {
  switch (e.type) {
    case google.ima.dai.api.StreamEvent.Type.AD_BREAK_STARTED:
      videoElement.controls = false; // Hide native controls
      adUiElement.style.display = 'block'; // Show Ad UI overlay
      // Disable custom UI controls here
      break;
    case google.ima.dai.api.StreamEvent.Type.AD_BREAK_ENDED:
      videoElement.controls = true; // Restore controls
      adUiElement.style.display = 'none'; // Hide Ad UI overlay
      // Enable custom UI controls here
      break;
  }
}
```

--------------------------------------------------------------------------------

## 5. Cleanup

Destroy the `StreamManager` when the player is disposed to release resources.

````javascript
function destroyDAI() {
  if (streamManager) {
    streamManager.destroy();
    streamManager = null;
  }
}

--------------------------------------------------------------------------------

## 6. HLS Integration (Timed Metadata)

When playing HLS streams, you must extract timed metadata (ID3 tags) and pass it to the SDK.

### A. hls.js (Cross-Browser)

HLS.js extracts ID3 tags from TS and fMP4 media segments during fragment parsing and emits them via event listeners (`Hls.Events.FRAG_PARSING_METADATA`). You must pass the exact presentation timestamp (`sample.pts`) along with `sample.data` so the SDK matches ad cues accurately with video playback timeline.

```javascript
import Hls from 'hls.js';

function setupHlsPlayer(streamUrl) {
  const hls = new Hls();
  hls.loadSource(streamUrl);
  hls.attachMedia(videoElement);

  hls.on(Hls.Events.FRAG_PARSING_METADATA, (event, data) => {
    if (streamManager && data) {
      data.samples.forEach((sample) => {
        // Parameters: Type ('ID3'), Raw Data (Uint8Array), PTS (Presentation Timestamp)
        // Pass the exact sample.pts so the SDK matches cues accurately
        streamManager.processMetadata('ID3', sample.data, sample.pts);
      });
    }
  });
}
```

If dash.js or ShakaPlayer is used, read and follow the official guide for extracting and processing timed metadata at https://developers.google.com/ad-manager/dynamic-ad-insertion/sdk/html5/timed-metadata.

--------------------------------------------------------------------------------

## 7. Custom Targeting Parameters

Custom targeting parameters allow Google Ad Manager to serve targeted ad campaigns based on audience segments, content categories, or user metadata.

Set key-value string pairs on `streamRequest.adTagParameters`:

```typescript
const streamRequest = new google.ima.dai.api.LiveStreamRequest();
streamRequest.assetKey = 'YOUR_ASSET_KEY';
streamRequest.networkCode = 'YOUR_NETWORK_CODE';

// Configure custom targeting parameters for Google Ad Manager
streamRequest.adTagParameters = {
  'category': 'sports',
  'user_type': 'premium'
};

streamManager.requestStream(streamRequest);
```

--------------------------------------------------------------------------------

## 8. Iframe Integration

When hosting the video player and the IMA SDK inside an `<iframe>`, you must ensure the iframe has access to the top level page and the necessary permissions for playback features like autoplay, fullscreen, or DRM.

Add the following attributes to the `<iframe>` tag:

*   `allow="autoplay"`: Allows the SDK and player to autoplay ads and content.
*   `allow="encrypted-media"`: Required if your DAI streams use DRM (e.g., Widevine, FairPlay).
*   `allowfullscreen`: Allows the player to enter fullscreen mode.

Example:

```html
<iframe
  src="YOUR_PLAYER_URL"
  allow="autoplay; encrypted-media"
  allowfullscreen>
</iframe>
```

If using the `sandbox` attribute, you must include the following directives:

*   `allow-scripts`: Required to run the IMA SDK.
*   `allow-same-origin`: Required for the SDK to function correctly and access necessary APIs.
*   `allow-popups`: Required to allow ad click-throughs to open in new tabs/windows.

### Cross-Origin Iframe Workaround

If you detect that the IMA SDK is loaded inside an iframe from a domain different from the domain of the main page containing the video player, you must provide the main page's URL to the SDK by setting the `adsRequest.pageUrl` property.

Example code:

```typescript
const adsRequest: google.ima.AdsRequest = new google.ima.AdsRequest();
adsRequest.adTagUrl = 'YOUR_AD_TAG_URL';

// Manually set the page URL to the parent page's URL
adsRequest.pageUrl = 'https://<your_domain>/<path_to_your_page>';
```

--------------------------------------------------------------------------------

## 9. Mobile Safari Considerations

Mobile Safari (particularly on iOS/iPhone) has specific behaviors and restrictions that affect video playback and ad overlays.

You must do the following steps:

*   Check and make sure that the `playsinline` attribute is added for the HTML `<video>` element.
*   Add a play button to initiate playback by user gesture.

Example:

```html
<!-- This video will attempt to play within its layout on iOS -->
<video playsinline controls></video>
```

--------------------------------------------------------------------------------
