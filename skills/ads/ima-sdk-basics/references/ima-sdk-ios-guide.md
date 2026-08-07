# Google IMA SDK iOS integration guide

This guide covers the integration of the Google IMA SDK for iOS (client-side)
following the lifecycle of ad playback.

## Integration flow

### 1. Import the SDK

By default, use Swift Package Manager to add the the main branch of
https://github.com/googleads/swift-package-manager-google-interactive-media-ads-ios.

If the app must use CocoaPods, install the `GoogleAds-IMA-iOS-SDK` pod.

### 2. Initialization

Configure the SDK settings and initialize the `IMAAdsLoader` early in the
application lifecycle to minimize latency, and set up the Ad UI.

*   **Early Initialization:** Creating an `IMAAdsLoader` instance is expensive
    as it spins up an underlying WebView (1-2 seconds overhead). Instantiate the
    loader early (e.g., at app launch) and reuse the single instance.
*   **Settings Immutability:** Configure `IMASettings` before passing them to
    the loader. Once the loader is initialized, settings become read-only.
*   **Create the IMAAdsLoader:** Instantiate `IMAAdsLoader` passing your
    configured `IMASettings` instance. This object handles the lifecycle of ad
    requests and must be persisted and reused.
*   **Ad UI Setup:** Create a dedicated `UIView` for ads and layer it directly
    on top of your video player view using Auto Layout. Hide custom player
    controls when ads play.

```swift
import UIKit
import GoogleInteractiveMediaAds

// 1. Shared AdsManager to handle early initialization and reuse
class AdsManager: NSObject {
    static let shared = AdsManager()

    var adsLoader: IMAAdsLoader?
    var adsManager: IMAAdsManager?
    private var settings: IMASettings

    private override init() {
        // Configure settings early
        settings = IMASettings()
        settings.language = "en"
        settings.enableDebugMode = true

        super.init()

        // Initialize loader early. Settings are now locked.
        adsLoader = IMAAdsLoader(settings: settings)
    }

    // 2. Ad UI Setup helper
    func setupAdContainer(in viewController: UIViewController, overlaying videoView: UIView) -> UIView {
        let adContainerView = UIView()
        adContainerView.translatesAutoresizingMaskIntoConstraints = false
        viewController.view.addSubview(adContainerView)

        // Align perfectly with the video view
        NSLayoutConstraint.activate([
            adContainerView.leadingAnchor.constraint(equalTo: videoView.leadingAnchor),
            adContainerView.trailingAnchor.constraint(equalTo: videoView.trailingAnchor),
            adContainerView.topAnchor.constraint(equalTo: videoView.topAnchor),
            adContainerView.bottomAnchor.constraint(equalTo: videoView.bottomAnchor)
        ])

        return adContainerView
    }
}
```

### 3. Ad request

Create an `IMAAdDisplayContainer` and an `IMAAdsRequest`, then trigger the
request. It is highly recommended to trigger this on a user gesture (e.g.,
tapping play).

```swift
extension AdsManager {
    func requestAds(adTagUrl: String, adContainer: UIView, videoDisplay: IMAVideoDisplay, delegate: IMAAdsLoaderDelegate) {
        guard let loader = adsLoader else { return }
        loader.delegate = delegate

        // Create the ad display container
        let displayContainer = IMAAdDisplayContainer(adContainerViewController: delegate as? UIViewController, companionViews: nil)

        // Create the ads request
        let request = IMAAdsRequest(
            adTagUrl: adTagUrl,
            adDisplayContainer: displayContainer,
            contentPlayhead: nil,
            userContext: nil)

        // Request ads
        loader.requestAds(with: request)
    }
}
```

### 4. Ad load success/failure

Implement `IMAAdsLoaderDelegate` to handle successful ad loads (which returns
the `IMAAdsManager`) or early failures (fatal loading errors).

```swift
class PlayerViewController: UIViewController, IMAAdsLoaderDelegate {
    var videoView: UIView! // Your video player view
    var adContainerView: UIView?

    func startAdFlow() {
        // Set up UI and request ads
        self.adContainerView = AdsManager.shared.setupAdContainer(in: self, overlaying: videoView)

        let videoDisplay = IMAAVPlayerVideoDisplay(avPlayer: self.contentPlayer)
        AdsManager.shared.requestAds(
            adTagUrl: "YOUR_AD_TAG_URL",
            adContainer: self.adContainerView!,
            videoDisplay: videoDisplay,
            delegate: self)
    }

    // MARK: - IMAAdsLoaderDelegate (Success)
    func adsLoader(_ loader: IMAAdsLoader, admitsCompletedWith adsManagerLoadedData: IMAAdsManagerLoadedData) {
        // Ad Load Success: Get the AdsManager
        AdsManager.shared.adsManager = adsManagerLoadedData.adsManager
        AdsManager.shared.adsManager?.delegate = self

        // Initialize the ads manager
        AdsManager.shared.adsManager?.initialize(with: nil)
    }

    // MARK: - IMAAdsLoaderDelegate (Failure / Fatal Load Error)
    func adsLoader(_ loader: IMAAdsLoader, failedWith adErrorData: IMAAdLoadingErrorData) {
        print("IMA SDK Loading Error: \(adErrorData.adError.message ?? "Unknown error")")
        resumeContent() // Fallback to content
    }
}
```

### 5. Ad playback events

Implement `IMAAdsManagerDelegate` to listen for playback events, coordinate
content pausing/resumption, and handle playback errors.

*   **Pause Content:** On `pause` event, pause your content player and hide
    custom controls.
*   **Resume Content:** On `resume` event or
    `adsManagerDidRequestContentResume`, restore controls and play content.
*   **Non-Fatal Logs:** Monitor `log` events for silent tracking or VPAID issues
    without interrupting playback.

```swift
extension PlayerViewController: IMAAdsManagerDelegate {

    // MARK: - IMAAdsManagerDelegate (Playback Events)
    func adsManager(_ adsManager: IMAAdsManager, didReceive event: IMAAdEvent) {
        switch event.type {
        case .LOADED:
            // Start ad playback
            adsManager.start()
        case .PAUSE:
            pauseContent() // Pause player, hide custom controls
        case .RESUME:
            resumeContent() // Resume player, restore controls
        case .LOG:
            if let adData = event.adData {
                print("IMA SDK Non-fatal Log: \(adData)")
            }
        default:
            break
        }
    }

    func adsManagerDidRequestContentResume(_ adsManager: IMAAdsManager) {
        resumeContent() // Resume content when ad completes
    }

    // MARK: - IMAAdsManagerDelegate (Playback Failure / Fatal Error)
    func adsManager(_ adsManager: IMAAdsManager, failedWith error: IMAAdError) {
        print("IMA SDK Manager Error: \(error.message ?? "Unknown error")")
        cleanupAds()
        resumeContent()
    }
}
```

### 6. Cleanup

Proper cleanup is **critical** to prevent memory leaks, audio playback bugs, and
background resource consumption.

*   **`IMAAdsManager.destroy()`:** This is crucial. Always call it, and set your
    reference to `nil`, when:
    *   All ads have completed.
    *   A fatal ad error occurs (in `failedWith` delegate).
    *   The user dismisses the player or navigates away (e.g., in
        `viewWillDisappear` or `deinit`).
*   **`IMAAdsLoader` Cleanup:** The `IMAAdsLoader` is designed to be a
    long-lived object. Do not destroy it between ad requests. However, if you
    need to completely tear down the ad integration (e.g., when the app is
    shutting down or a major parent component is deinitialized), set the
    loader's delegate to `nil` and nullify your reference to allow ARC to
    deallocate it.

```swift
// In your PlayerViewController
deinit {
    cleanupAds()
}

override func viewWillDisappear(_ animated: Bool) {
    super.viewWillDisappear(animated)
    if isMovingFromParent {
        cleanupAds()
    }
}

func cleanupAds() {
    // 1. Destroy the AdsManager and nil its delegate
    if let manager = AdsManager.shared.adsManager {
        manager.destroy()
        manager.delegate = nil
        AdsManager.shared.adsManager = nil
    }

    // 2. Clean up UI
    self.adContainerView?.removeFromSuperview()
    self.adContainerView = nil
}

// Call this only when permanently tearing down the SDK integration
func tearDownSDK() {
    AdsManager.shared.adsLoader?.delegate = nil
    AdsManager.shared.adsLoader = nil
}
```

--------------------------------------------------------------------------------

## Reference implementation

*   BasicExample [BasicExampleApp.swift](https://raw.githubusercontent.com/googleads/googleads-ima-ios/main/Swift/BasicExample/BasicExample/BasicExampleApp.swift)
*   BasicExample [PlayerContainerViewController.swift](https://raw.githubusercontent.com/googleads/googleads-ima-ios/main/Swift/BasicExample/BasicExample/PlayerContainerViewController.swift)