# AI Integration Agent Instructions for the Unity Google Mobile Ads Plugin

## SDK Integration Workflow

1.  **Add the SDK dependency**:

    Install via `Packages/manifest.json`:

    -   Run the following command to fetch the latest version. The tag returned
        (excluding the 'v' prefix) is the latest version of the Google Mobile
        Ads SDK:

        ```bash
        curl -sS https://api.github.com/repos/googleads/googleads-mobile-unity/releases/latest | jq -r '.tag_name'
        ```

    -   Modify `Packages/manifest.json` with the "OpenUPM" scoped registry,
        using the latest version.

        ```json
        {
          "scopedRegistries": [
            {
              "name": "OpenUPM",
              "url": "https://package.openupm.com",
              "scopes": [
                "com.google"
              ]
            }
          ],
          "dependencies": {
            // Replace 11.2.0 with the latest stable version.
            "com.google.ads.mobile": "11.2.0"
          }
        }
        ```

2.  **Set the application identifier**:

    Modify `Assets/GoogleMobileAds/Resources/GoogleMobileAdsSettings.asset`. Set
    `adMobAndroidAppId` and `adMobIOSAppId` to the sample App IDs:

    -   Android: `ca-app-pub-3940256099942544~3347511713`
    -   iOS: `ca-app-pub-3940256099942544~1458002511`

    Remind the user to replace it with their actual AdMob App ID before
    publishing.

3.  **Initialize the SDK**:

    Write a script to handle initialization. Ensure background ad callbacks
    interacting with Unity objects (`UnityEngine`) are explicitly scheduled on
    the main thread using `ExecuteInUpdate()`.

    Do not set `MobileAds.RaiseAdEventsOnUnityMainThread` to `true`, it is
    obsolete.

    ```c#
    using GoogleMobileAds.Api;
    using GoogleMobileAds.Common;
    using UnityEngine;

    public class GoogleMobileAdsController : MonoBehaviour
    {
        public void Start()
        {
            // Initialize the Google Mobile Ads SDK exactly once.
            MobileAds.Initialize((InitializationStatus initStatus) =>
            {
                Debug.Log("Google Mobile Ads SDK initialized.");

                MobileAdsEventExecutor.ExecuteInUpdate(() =>
                {
                    // Interact with UnityEngine objects on the main thread here.
                });
            });
        }
    }
    ```

4.  **Verify the integration**:

    Compile the Unity csproj file by running `dotnet build`. Resolve any GMA SDK
    related compile errors.

### Links

Additional documentation and guides:

-   Quick Start Guide:
    https://developers.google.com/admob/unity/quick-start.md.txt
-   Global Settings Guide:
    https://developers.google.com/admob/unity/global-settings.md.txt
-   OpenUPM Package: https://openupm.com/packages/com.google.ads.mobile/
