# Google IMA SDK HTML5 (Web) integration guide

This guide covers the integration of the Google IMA SDK for HTML5 (client-side)
following the natural lifecycle of ad playback.

## Integration flow

### 1. Import the SDK

Load the SDK script at the page level. Ensure the SDK can access
`window.top.location.href`.

```html
<script src="https://imasdk.googleapis.com/js/sdkloader/ima3.js"></script>
```

### 2. Initialization

Configure the SDK settings early, set up the Ad UI, and initialize the
`AdDisplayContainer` and `AdsLoader`.

*   **Configure Settings Early (Best Practice):** You **must** set your
    configurations on the global singleton `google.ima.settings` *before*
    creating the `AdDisplayContainer` or the `AdsLoader`. Late changes will not
    propagate.
*   **Ad UI Setup:** Always use a dedicated HTML element (e.g., `<div
    id="adContainer">`) solely for the IMA SDK, layered directly on top of the
    video player. Hide custom player controls when ads play.
*   **Create AdDisplayContainer:** Instantiate `google.ima.AdDisplayContainer`
    passing the ad container HTML element and the content video element.
*   **Create AdsLoader:** Instantiate `google.ima.AdsLoader` passing your
    `AdDisplayContainer` instance. This object handles the lifecycle of ad
    requests.

```html
<!-- HTML Structure -->
<div id="playerContainer" style="position:relative; width:640px; height:360px;">
  <video id="contentVideo" style="width:100%; height:100%;"></video>
  <div id="adContainer" style="position:absolute; top:0; left:0; width:100%; height:100%; z-index:10;"></div>
</div>
```

```typescript
// TypeScript Initialization
let adsLoader: google.ima.AdsLoader;
let adDisplayContainer: google.ima.AdDisplayContainer;

function initializeIMA(): void {
    // 1. Configure global settings early
    google.ima.settings.setLocale('en');
    google.ima.settings.setVpaidMode(google.ima.ImaSdkSettings.VpaidMode.ENABLED);

    // 2. Set up Ad UI Container
    const adContainerElement = document.getElementById('adContainer') as HTMLElement;
    const videoElement = document.getElementById('contentVideo') as HTMLVideoElement;

    adDisplayContainer = new google.ima.AdDisplayContainer(adContainerElement, videoElement);

    // 3. Initialize AdsLoader
    adsLoader = new google.ima.AdsLoader(adDisplayContainer);

    // Setup listeners for Ad Load Success/Failure
    setupAdsLoaderListeners();
}
```

### 3. Set up app UI

You **must** suggest the best practice to use a user action, such as button
click, to start content and ad playback.

If your app needs autoplay ads, you must write the code to check whether the
browser supports autoplay. If unmuted autoplay fails, fallback to muted
autoplay. If that fails, fallback to using a user action, such as button click,
to start content and ad playback.

Crucially, you must inform the IMA SDK of the final state using
`setAdWillAutoPlay()` and `setAdWillPlayMuted()`. This guarantees the ad server
returns an ad formatted for your specific playback environment.

```typescript
const request = new google.ima.AdsRequest();
request.adTagUrl = 'YOUR_AD_TAG_URL';

// Inform the SDK of the current playback capabilities
request.setAdWillAutoPlay(isAutoPlay);
request.setAdWillPlayMuted(isMuted);

adsLoader.requestAds(request);
```

### 4. Ad request

Create an `AdsRequest` and use `AdsLoader` to load it.

```typescript
function requestAds() {
    adDisplayContainer.initialize();

    const adsRequest = new google.ima.AdsRequest();
    adsRequest.adTagUrl = `YOUR_AD_TAG_URL`;

    adsLoader.requestAds(adsRequest);
}
```

### 5. Ad load success/failure

Listen for the `AdsLoader` to successfully load the ads (providing the
`AdsManager`) or fail early (fatal loading errors).

```typescript
let adsManager: google.ima.AdsManager | null = null;

function setupAdsLoaderListeners(): void {
    // Handle Ad Load Success
    adsLoader.addEventListener(
        google.ima.AdsManagerLoadedEvent.Type.ADS_MANAGER_LOADED,
        onAdsManagerLoaded
    );

    // Handle Ad Load Failure (Fatal Error)
    adsLoader.addEventListener(
        google.ima.AdErrorEvent.Type.AD_ERROR,
        onAdError
    );
}

function onAdsManagerLoaded(adsManagerLoadedEvent: google.ima.AdsManagerLoadedEvent): void {
    // Get the AdsManager
    const adsRenderingSettings = new google.ima.AdsRenderingSettings();
    adsManager = adsManagerLoadedEvent.getAdsManager(videoElement, adsRenderingSettings);

    setupAdsManagerListeners(adsManager);

    try {
        // Initialize the manager
        adsManager.init(width, height, google.ima.ViewMode.NORMAL);
        // Start ad playback
        adsManager.start();
    } catch (adError) {
        // Handle initialization errors
        resumeContent();
    }
}

function onAdError(adErrorEvent: google.ima.AdErrorEvent): void {
    console.error("IMA SDK Fatal Error:", adErrorEvent.getError().toString());
    cleanupAds();
    resumeContent(); // Fallback to content
}
```

### 6. Ad playback events

Use the `AdsManager` to listen for playback events, coordinate content
pausing/resumption, and monitor non-fatal logs.

*   **Pause Content:** On `CONTENT_PAUSE_REQUESTED`, pause the content video
    player and hide custom controls.
*   **Resume Content:** On `CONTENT_RESUME_REQUESTED`, hide the ad container,
    restore player controls, and play the content video.
*   **Non-Fatal Logs:** Listen for `LOG` events to detect silent failures (e.g.,
    failed tracking pings) without interrupting the user.

```typescript
function setupAdsManagerListeners(manager: google.ima.AdsManager): void {
    // Playback Events
    manager.addEventListener(
        google.ima.AdEvent.Type.CONTENT_PAUSE_REQUESTED,
        () => { pauseContent(); }, // Pause player, hide custom controls
        false
    );

    manager.addEventListener(
        google.ima.AdEvent.Type.CONTENT_RESUME_REQUESTED,
        () => { resumeContent(); }, // Resume player, restore controls
        false
    );

    // Non-Fatal Logs
    manager.addEventListener(
        google.ima.AdEvent.Type.LOG,
        (adEvent: google.ima.AdEvent) => {
            const logData = adEvent.getAdData();
            if (logData && logData['errorMessage']) {
                console.warn("IMA SDK Non-fatal Log:", logData['errorMessage']);
            }
        },
        false
    );

    // Playback Errors (Fatal errors during active playback)
    manager.addEventListener(
        google.ima.AdErrorEvent.Type.AD_ERROR,
        onAdError,
        false
    );
}
```

### 7. Cleanup

Proper cleanup is **critical** in HTML5 to prevent memory leaks, redundant event
callbacks, and leftover DOM elements (like SDK iframes).

*   **`adsManager.destroy()`:** This is crucial. Always call it when ads finish,
    on fatal error, or when the player is unmounted/navigated away.
*   **`adsLoader.contentComplete()`:** Call this to signal to the SDK that
    content has finished. This is required for the SDK to play post-roll ads.
*   **`adDisplayContainer.destroy()`:** Call this when disposing of the player.
    It removes the internal DOM elements (including iframes) created by the SDK.
*   **Nullify References:** Set all references to `null` to allow garbage
    collection.

```typescript
// Call this when the player is being destroyed/unmounted (e.g., ngOnDestroy, componentWillUnmount)
function tearDownPlayer(): void {
    cleanupAds();

    // 1. Signal content completion (important for post-rolls)
    if (adsLoader) {
        adsLoader.contentComplete();
    }

    // 2. Destroy the display container to clean up DOM/iframes
    if (adDisplayContainer) {
        adDisplayContainer.destroy();
        adDisplayContainer = null;
    }

    // 3. Nullify the loader if tearing down the page
    adsLoader = null;
}

function cleanupAds(): void {
    // 4. Destroy the AdsManager to release active ad resources
    if (adsManager) {
        adsManager.destroy();
        adsManager = null;
    }
}
```

--------------------------------------------------------------------------------

## Reference implementation

*   UI setup: [simple/index.html](https://raw.githubusercontent.com/googleads/googleads-ima-html5/main/simple/index.html)
*   App logic: [simple/ads.js](https://raw.githubusercontent.com/googleads/googleads-ima-html5/main/simple/ads.js)
*   Optionally, install type definitions for TypeScript projects:

```bash
    npm install --save-dev @types/google_interactive_media_ads_types