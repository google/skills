---
name: ima-dai-sdk
description: >-
  Integrates the Google Interactive Media Ads (IMA) Dynamic Ad Insertion (DAI)
  SDK into websites, web apps, mobile apps, or TV apps.
  Use when:
  - A video player needs to load and play HLS or DASH streams in web apps,
  Android apps, iOS apps, tvOS apps, Cast (CAF) receivers, or Roku channels.
  - The app needs to make use of a Google DAI livestream event asset key, or
  content source CMS ID, video ID for video on demand.
  Don't use this skill to load and play a VAST or VMAP URL.
license: Apache-2.0
metadata:
  author: Google LLC
  version: "1.0.1"
  category: GoogleAds
---

# IMA DAI SDK

Use the IMA DAI SDK to load HLS or DASH streams into the app for:

*   **Livestream events** configured in Google Ad Manager.
*   **Video on demand (VOD)** content ingested into Google Ad Manager.

## Prerequisites

Review the platform-specific integration guides for the target platforms:

*   **Web/HTML5/ReactJs/NodeJs/Angular:** Read
    [StreamManager guide](references/web-StreamManager-guide.md) for loading
    stream URL from Google full-service DAI into `<video>` element.

*   **ChromeCast:** Read
    [StreamManager guide](references/cast-StreamManager-guide.md) for
    integrating the IMA DAI SDK into a ChromeCast Web Receiver.

*   **Android:** Read
    [ImaServerSideAdInsertionMediaSource guide](references/android-ImaServerSideAdInsertionMediaSource-guide.md)
    for integrating Media3 Exoplayer IMA extension.

*   **iOS/tvOS:** Read
    [IMAStreamRequest guide](references/ios-IMAStreamRequest-guide.md) for
    playing streams with `AVPlayer`.

*   **Roku:** Read [StreamManager guide](references/roku-StreamManager-guide.md)
    for implementing DAI on Roku SceneGraph.

## Quick start (general workflow)

1.  Import the SDK
2.  Initialize the SDK
3.  Add stream event listeners
4.  Set up timed metadata forwarding
5.  Make a stream request
6.  Clean up SDK resources when the stream fails or the user leaves the stream.
