# Ad preloading validation checks

-   **Follow These Steps**:
    -   [ ] Search for GMA SDK ad preloading calls for the respective platform:

        | API | Android | iOS | Unity |
        | :--- | :--- | :--- | :--- |
        | Start Preload | `startPreload` | `preload` | `Preload` |
        | Stop Preload | `destroyAll` | `stopPreloadingAndRemoveAllAds` | `DestroyAll` |
        | Poll Ad | `pollAd` | `ad(withPreloadID:)` | `DequeueAd` |
        | Peek Ad | `peekAdResponseInfo` | `responseInfo(withPreloadID:)` | `PeekAdResponseInfo` |
        | Ad Preloaded | `onAdPreloaded` | `adAvailable(forPreloadID:)` | `OnAdPreloaded` |
        | Ad Failed to Preload | `onAdFailedToPreload` | `adFailedToPreload(forPreloadID:error:)` | `OnAdFailedToPreload` |
        | Ads Exhausted | `onAdsExhausted` | `adsExhausted(forPreloadID:)` | `OnAdsExhausted` |
        | Ad Available Check | `isAdAvailable` | `isAdAvailable(withPreloadID:)` | `IsAdAvailable` |

-   **Pass/Fail Criteria**:
    -   **Fail**: Any of the following improper ad preloading patterns are
        detected in the project:
        -   Polls an ad without showing it within the same method scope.
        -   Polls an ad to inspect its response info.
        -   Polls an ad unconditionally inside the ad preloaded callback.
        -   Starts or stops preloading in the ad preloaded, ad failed to
            preload, or ads exhausted callback.
        -   Starts preloading for the same preload ID multiple times without
            stopping the preloader first.
        -   Uses an empty string or null as the preload ID.
        -   Checks ad availability inside an `Update` loop on **Unity**.
    -   **Warning**:
        -   Polls an ad conditionally inside the ad preloaded callback. Notify
            the user that polling an ad triggers another ad load.
        -   Preloads multiple ad unit IDs for the same ad format.
        -   Uses a buffer size greater than 5.
    -   **N/A**: The project doesn't use the ad preloading APIs.
