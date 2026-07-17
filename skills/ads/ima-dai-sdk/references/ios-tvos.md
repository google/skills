# Google IMA SDK DAI - iOS & tvOS Integration Guide

This guide covers the general integration steps for the Google IMA SDK for iOS
and tvOS DAI. The two SDKs share the same core API and lifecycle flow.

For protocol-specific details, see [HLS Guide](hls.md). For DAI workflows, see
[Full Service Guide](full-service.md) and [Pod Serving Guide](pod-serving.md).

--------------------------------------------------------------------------------

## 1. Installation

By default, use Swift Package Manager to add the the main branch of
https://github.com/googleads/swift-package-manager-google-interactive-media-ads-ios
or
https://github.com/googleads/swift-package-manager-google-interactive-media-ads-tvos

If the app must use CocoaPods, install the `GoogleAds-IMA-iOS-SDK` or
`GoogleAds-IMA-tvOS-SDK` pod.

## 2. Implement IMA protocols

*   **`IMAAdsLoaderDelegate`**: Required for your app to receive events when ads
    successfully load or if they fail to load.
*   **`IMAStreamManagerDelegate`**: Required for your app to handle events
    during ad playback (e.g., when an ad starts, pauses, completes, or when the
    user clicks an ad).

```swift
class PlayerViewController: IMAAdsLoaderDelegate, IMAStreamManagerDelegate

```

--------------------------------------------------------------------------------

## 3. Initialize AdsLoader Early

You must create the `AdsLoader` object early, such as when your view did load.
Set the `IMASettings` to match your app UI localization needs. Reuse the
`AdsLoader` and `IMASettings` objects.

```swift
import AVFoundation
import GoogleInteractiveMediaAds

class PlayerViewController: ..., IMAAdsLoaderDelegate, IMAStreamManagerDelegate {
  private var adsLoader: IMAAdsLoader?
  // ...

  override func viewDidLoad() {
    super.viewDidLoad()
    ...

    let settings = IMASettings()
    settings.language = LANGUAGE_CODE               // Use 2 letter language code to match the ad UI with your app UI's language.

    // 2. Initialize AdsLoader WITH the configured settings
    adsLoader = IMAAdsLoader(settings: settings)
  }
}
```

## 4. Create Ad Display Container

You must create the `IMAAdDisplayContainer` object for the SDK to render the ad
UI during ad playback. Pass your `videoView` so the SDK knows where to overlay
the ad UI on top of the video player.

```swift
adDisplayContainer = IMAAdDisplayContainer(adContainer: videoView)
```

## 5. Create `IMAAVPlayerVideoDisplay` object

You must create the `IMAAVPlayerVideoDisplay` object and provide your `AVPlayer`
object. You must provide the `AVPlayer` object that is intended to play the ads
if you have multiple instances of the `AVPlayer` class in your app. The SDK
needs to listen for the timed metadata (ID3 tags) embedded in the HLS manifest
from the ad player to trigger ad events.

```swift
imaVideoDisplay = IMAAVPlayerVideoDisplay(avPlayer: adVideoPlayer)
```

## 6. Make DAI Stream Request

Refer to the [full-service DAI guide](full-service.md) and
[pod-serving DAI guide](pod-serving.md) to determine the exact DAI stream
request.

--------------------------------------------------------------------------------

## 7. tvOS-Specific Requirements

Integrating on tvOS requires handling Apple TV remote focus and gestures.

### A. Safe Area Layout

Align your ad UI container with the safe area layout guide to prevent TV
overscan clipping.

```swift
func setupAdContainer(in viewController: UIViewController, overlaying videoView: UIView) -> UIView {
    let adContainerView = UIView()
    adContainerView.translatesAutoresizingMaskIntoConstraints = false
    viewController.view.addSubview(adContainerView)

    // Align with safe area
    let safeArea = viewController.view.safeAreaLayoutGuide
    NSLayoutConstraint.activate([
        adContainerView.leadingAnchor.constraint(equalTo: safeArea.leadingAnchor),
        adContainerView.trailingAnchor.constraint(equalTo: safeArea.trailingAnchor),
        adContainerView.topAnchor.constraint(equalTo: safeArea.topAnchor),
        adContainerView.bottomAnchor.constraint(equalTo: safeArea.bottomAnchor)
    ])
    return adContainerView
}
```

### B. Focus Management (Siri Remote)

The SDK automatically manages the focus of the "Skip" button. You must override
`preferredFocusEnvironments` to prefer the ad container when an ad is active:

```swift
var adIsPlaying = false // Update this based on IMAAdEvents

override var preferredFocusEnvironments: [UIFocusEnvironment] {
    if adIsPlaying, let adContainer = adContainerView {
        return [adContainer]
    }
    return super.preferredFocusEnvironments
}
```

### C. Remote Control Gestures

Disable custom remote gestures (like swipe or click-to-pause) during ad playback
to prevent users from skipping ads.

```swift
func streamManager(_ streamManager: IMAStreamManager, didReceive event: IMAAdEvent) {
  switch event.type {
  case .AD_BREAK_STARTED:
    adIsPlaying = true
    disableAppGestures() // Disable custom gestures
    setNeedsFocusUpdate()
  case .AD_BREAK_ENDED:
    adIsPlaying = false
    enableAppGestures() // Re-enable custom gestures
    setNeedsFocusUpdate()
  default:
    break
  }
}
```
