# Google IMA DAI SDK iOS/tvOS - IMAStreamRequest Guide

For Google full-service DAI, use `IMALiveStreamRequest` to request a livestream
and `IMAVODStreamRequest` to request a VOD stream.

## Table of Contents

*   [Dependencies](#dependencies) (Line 19)
    *   [Use Swift Package Manager](#use-swift-package-manager) (Line 21)
*   [SDK Initialization](#sdk-initialization) (Line 35)
*   [UI Setup & Video Player](#ui-setup--video-player) (Line 51)
*   [Make stream requests](#make-stream-requests) (Line 68)
    *   [Request a livestream](#request-a-livestream) (Line 72)
    *   [Request a VOD stream](#request-a-vod-stream) (Line 92)
*   [Listen to Stream Load Events](#listen-to-stream-load-events) (Line 116)
*   [Listen to Stream and Ad Events](#listen-to-stream-and-ad-events) (Line 119)
*   [Reference Implementation](#reference-implementation) (Line 182)

## Dependencies

### Use Swift Package Manager

For iOS, add this package:

```
https://github.com/googleads/swift-package-manager-google-interactive-media-ads-ios
```

For tvOS, add this package:

```
https://github.com/googleads/swift-package-manager-google-interactive-media-ads-tvos
```

## SDK Initialization

Initialize the `IMAAdsLoader` early, such as in `ViewController.viewDidLoad`
event.

```swift
import GoogleInteractiveMediaAds

class ViewController {
  override func viewDidLoad() {
    super.viewDidLoad()
    adsLoader = IMAAdsLoader(settings: IMASettings())
  }
}
```

## UI Setup & Video Player

Create `IMAAdDisplayContainer` object using the `videoView` containing the
`AVPlayer`. Ad UI components will be rendered within the `videoView` over the
player.

```swift
adDisplayContainer = IMAAdDisplayContainer(adContainer: videoView, viewController: self)
```

Create `IMAAVPlayerVideoDisplay` with the `AVPlayer` instance so that the IMA
DAI SDK can listen to the video player for timed metadata during ad breaks.

```swift
imaVideoDisplay = IMAAVPlayerVideoDisplay(avPlayer: videoPlayer)
```

## Make stream requests

Reuse the same `AdsLoader` instance to make stream requests.

### Request a livestream

Instantiate `IMALiveStreamRequest` with the asset key and network code:

```swift
let request = IMALiveStreamRequest(
  assetKey: <ASSET_KEY_PLACEHOLDER>,
  networkCode: <NETWORK_CODE_PLACEHOLDER>,
  adDisplayContainer: adDisplayContainer,
  videoDisplay: imaVideoDisplay,
  userContext: nil)
adsLoader.requestStream(with: request)
```

Provide the following parameters:

*   **<NETWORK_CODE_PLACEHOLDER>**: The Google Ad Manager network code.
*   **<ASSET_KEY_PLACEHOLDER>**: The livestream asset key configured in Google
    Ad Manager.

### Request a VOD stream

Instantiate `IMAVODStreamRequest` with content source ID (CMS ID) and video ID:

```swift
let request = IMAVODStreamRequest(
  contentSourceID: <CONTENT_SOURCE_ID_PLACEHOLDER>,
  videoID: <VIDEO_ID_PLACEHOLDER>,
  networkCode: <NETWORK_CODE_PLACEHOLDER>,
  adDisplayContainer: adDisplayContainer,
  videoDisplay: imaVideoDisplay,
  userContext: nil)
adsLoader.requestStream(with: request)
```

Provide the following parameters:

*   **<NETWORK_CODE_PLACEHOLDER>**: The Google Ad Manager network code.
*   **<CONTENT_SOURCE_ID_PLACEHOLDER>**: The CMS ID in Google Ad Manager.
*   **<VIDEO_ID_PLACEHOLDER>**: The video ID in the CMS.

For testing purposes, use values of DAI sample streams from
https://developers.google.com/ad-manager/dynamic-ad-insertion/streams.md.txt?utm_source=agent-skills&utm_medium=content&utm_campaign=adr-ss-ai&utm_content=ima-dai-sdk

## Listen to Stream Load Events

Implement `IMAAdsLoaderDelegate` to handle stream initialization or failure:

```swift
func adsLoader(_ loader: IMAAdsLoader, adsLoadedWith adsLoadedData: IMAAdsLoadedData) {
  print("DAI session ID: \(adsLoadedData.streamManager!.streamId!)")
  streamManager = adsLoadedData.streamManager!
  streamManager!.initialize(with: nil)
}

func adsLoader(_ loader: IMAAdsLoader, failedWith adErrorData: IMAAdLoadingErrorData) {
  print("Failed to load DAI stream. Error: \(adErrorData.adError.message ?? "")")
  playBackupStream()
}
```

## Listen to Stream and Ad Events

Implement `IMAStreamManagerDelegate` to receive stream events, ad lifecycle
events, and errors:

```swift
func streamManager(_ streamManager: IMAStreamManager, didReceive event: IMAAdEvent) {
  print("Ad event: \(event.typeString)")
  switch event.type {
  case IMAAdEventType.STARTED:
    if let ad = event.ad {
      let extendedAdPodInfo = String(
        format: "Showing ad %zd/%zd, bumper: %@, title: %@, "
          +   "description: %@, contentType:%@, pod index: %zd, "
          +   "time offset: %lf, max duration: %lf.",
        ad.adPodInfo.adPosition,
        ad.adPodInfo.totalAds,
        ad.adPodInfo.isBumper ? "YES" : "NO",
        ad.adTitle,
        ad.adDescription,
        ad.contentType,
        ad.adPodInfo.podIndex,
        ad.adPodInfo.timeOffset,
        ad.adPodInfo.maxDuration)
      print("\(extendedAdPodInfo)")
    }
    break
  case IMAAdEventType.AD_BREAK_STARTED:
    print("Ad break started.")
    break
  case IMAAdEventType.AD_BREAK_ENDED:
    print("Ad break ended.")
    break
  case IMAAdEventType.AD_PERIOD_STARTED:
    print("Ad period started.")
    break
  case IMAAdEventType.AD_PERIOD_ENDED:
    print("Ad period ended.")
    break
  default:
    break
  }
}

func streamManager(_ streamManager: IMAStreamManager, didReceive error: IMAAdError) {
  print("Failed to play DAI stream. Error: \(error.message ?? "Unknown Error")")
  playBackupStream()
}
```

## Reference Implementation

BasicExample:

*   [iPhone.storyboard](https://raw.githubusercontent.com/googleads/googleads-ima-ios-dai/refs/heads/main/Swift/BasicExample/app/iPhone.storyboard)
*   [ViewController.swift](https://raw.githubusercontent.com/googleads/googleads-ima-ios-dai/refs/heads/main/Swift/BasicExample/app/ViewController.swift)
