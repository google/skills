# Google IMA SDK tvOS integration guide

The Google IMA SDK for tvOS is highly consistent with the iOS SDK, sharing the
same API and integration flow.

**Before proceeding, you must read the [Google IMA SDK iOS Integration Guide](references/ima-sdk-ios-guide.md)
for the complete step-by-step lifecycle flow (Initialization -> Ad Request -> Ad
Load -> Playback -> Cleanup).**

This document outlines the critical differences and tvOS-specific requirements
you must implement.

--------------------------------------------------------------------------------

## Key differences from iOS

### 1. Import the SDK

By default, use Swift Package Manager to add the main branch of
https://github.com/googleads/swift-package-manager-google-interactive-media-ads-tvos.

If the app must use CocoaPods, install the `GoogleAds-IMA-tvOS-SDK` pod.

### 2. Autoplay for tvOS

Add tvOS platform check to your app and make ad request with autoplay.

### 3. Focus management (tvOS specific)

To handle the Siri Remote, you must manage focus:

*   **Ad UI Focus:** The IMA SDK automatically manages the focus of the "Skip"
    button and other ad UI views when needed. Ensure your application's focus
    engine does not intercept or override focus changes, which would prevent the
    user from focusing and clicking the skip button.

*   **Safe Area:** Ensure your ad UI container respects the tvOS safe area
    layout guides to prevent ad overlays or skip buttons from being cut off by
    TV overscan.

### 4. Remote control gestures (tvOS specific)

To prevent user interactions from interfering with ad playback (e.g.,
fast-forwarding through an ad):

*   **Disable Custom Gestures:** You **must** disable your application's custom
    remote control gesture recognizers (such as play/pause, swiping, or menu
    button overrides) when the ad starts (on `LOADED` or `STARTED` events).
*   **Restore Gestures:** Re-enable these gestures only after the ad completes
    (on `CONTENT_RESUME_REQUESTED`) or fails.

--------------------------------------------------------------------------------

## Code implementation differences

Refer to the [iOS Guide](references/ima-sdk-ios-guide.md) for the main
`AdsManager` and `PlayerViewController` implementation. Adjust the tvOS
implementation as follows:

### Ad UI setup (safe area)

In your `ViewController`, align the ad container with the safe area layout guide
to prevent TV overscan clipping:

```swift
func setupAdContainer(in viewController: UIViewController, overlaying videoView: UIView) -> UIView {
    let adContainerView = UIView()
    adContainerView.translatesAutoresizingMaskIntoConstraints = false
    viewController.view.addSubview(adContainerView)

    // tvOS Specific: Align with safe area to prevent overscan clipping
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

### Focus management (preferred focus environments)

To ensure the Siri Remote can focus on the SDK's interactive elements (like the
"Skip" button), you must call the `setNeedsFocusUpdate()` function and override
the `preferredFocusEnvironments` property of the `ViewController` object at the
`IMAAdEvent.Type.STARTED` event.

You must revert to standard focus rules when the ad finishes playing, such as
`IMAAdEvent.Type.COMPLETE` or `IMAAdEvent.Type.SKIPPED` event.

```swift
import UIKit
import GoogleInteractiveMediaAds

class YourViewController: UIViewController, IMAAdsManagerDelegate {

    // Tracks state to determine who gets focus
    var isAdPlaying: Bool = false
    var adDisplayContainer: IMAAdDisplayContainer?

    // MARK: - Focus Management

    override var preferredFocusEnvironments: [UIFocusEnvironment] {
        // Check if an ad is playing and if the IMA SDK has a valid focus environment
        if isAdPlaying, let adFocusEnvironment = adDisplayContainer?.focusEnvironment {
            // Hand focus routing over to the IMA SDK UI (e.g., "Skip" button)
            return [adFocusEnvironment]
        }

        // Otherwise, use the app's standard focus rules (e.g., video player controls)
        return super.preferredFocusEnvironments
    }

    // MARK: - IMAAdsManagerDelegate Methods

    func adsManager(_ adsManager: IMAAdsManager, didReceive event: IMAAdEvent) {
        switch event.type {
        case .LOADED:
            // tvOS Specific: Disable custom remote gestures during ad
            disableAppGestures()
            adsManager.start()

        case .STARTED:
            // Update state and force tvOS to move focus to the ad
            isAdPlaying = true
            setNeedsFocusUpdate()

        case .COMPLETED, .SKIPPED, .ALL_ADS_COMPLETED:
            // Update state and reclaim focus back to the app
            isAdPlaying = false
            setNeedsFocusUpdate()

        default:
            break
        }
    }

    func adsManagerDidRequestContentResume(_ adsManager: IMAAdsManager) {
        // tvOS Specific: Restore gestures when ad break finishes
        enableAppGestures()
        resumeContent()
    }

    func adsManager(_ adsManager: IMAAdsManager, failedWith error: IMAAdError) {
        // Safety check: Reset focus state just in case an ad fails mid-playback
        isAdPlaying = false
        setNeedsFocusUpdate()

        // tvOS Specific: Restore gestures on failure
        enableAppGestures()
        cleanupAds()
        resumeContent()
    }

    // MARK: - App-Specific Helpers (Implementation depends on your app)

    private func disableAppGestures() { /* ... */ }
    private func enableAppGestures() { /* ... */ }
    private func resumeContent() { /* ... */ }
    private func cleanupAds() { /* ... */ }
}
```