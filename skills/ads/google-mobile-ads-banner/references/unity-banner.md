# AI Integration Agent Instructions for Unity Banner Ads

## Required Imports

Use the following imports to implement a banner ad:

```c#
using System;
using UnityEngine;
using GoogleMobileAds.Api;
using GoogleMobileAds.Common;
```

## Banner Ad Workflow

1.  **Define the ad view**:

    Use the `BannerView` class from `GoogleMobileAds.Api` for defining banner
    ads. Set the appropriate test ad unit ID when creating the ad view:

    -   Android anchored adaptive: `ca-app-pub-3940256099942544/9214589741`
    -   iOS anchored adaptive: `ca-app-pub-3940256099942544/2435281174`

2.  **Set the ad size**:

    Pass `AdSize.Banner` or the appropriate adaptive ad size to the
    `BannerView` constructor along with `AdPosition` (`AdPosition.Top` or
    `AdPosition.Bottom`).

    For an anchored adaptive banner, use a large anchored adaptive ad size
    unless the user complains or a small height is needed.

    ```c#
    int width = MobileAds.Utils.GetDeviceSafeWidth();
    AdSize adSize = AdSize
        .GetCurrentOrientationLargeAnchoredAdaptiveBannerAdSizeWithWidth(width);
    BannerView bannerView =
        new BannerView(_adUnitId, adSize, AdPosition.Bottom);
    ```

3.  **Register for ad load events**:

    Subscribing to ad events on the `BannerView` object is optional and depends
    on your application requirements:

    -   `OnBannerAdLoaded`: Subscribe to update UI state when the banner ad is
        ready and displayed.
    -   `OnBannerAdLoadFailed`: Subscribe to log errors if the banner ad fails
        to load.
    -   `OnAdPaid`: Subscribe to log estimated ad revenue (`AdValue`) for
        impression-level ad monetization tracking.
    -   `OnAdImpressionRecorded`: Subscribe to track ad impressions in
        internal telemetry or third-party analytics platforms.
    -   `OnAdClicked`: Subscribe to record user clicks on the ad.
    -   `OnAdFullScreenContentOpened`: Subscribe to pause game audio,
        timers, or gameplay loops when the banner click opens full-screen
        destination content.
    -   `OnAdFullScreenContentClosed`: Subscribe to resume game audio or
        gameplay loops when full-screen destination content is dismissed.

    **CRITICAL**: Whenever you provide code or instructions for Unity ads, you
    MUST explicitly state that background ad callbacks interacting with Unity
    objects (`UnityEngine`) must be scheduled on the main thread using
    `MobileAdsEventExecutor.ExecuteInUpdate()`, because Unity APIs are not
    thread-safe.

    ```c#
    bannerView.OnBannerAdLoaded += () =>
    {
        MobileAdsEventExecutor.ExecuteInUpdate(() =>
        {
            // Interact with UnityEngine objects on the main thread here.
        });
    };
    ```

4.  **Load the banner ad**:

    Call the `LoadAd()` method on the `BannerView` object passing a new
    `AdRequest` object (`bannerView.LoadAd(new AdRequest())`).

    ```c#
    bannerView.LoadAd(new AdRequest());
    ```

5.  **Verify the implementation**:

    Compile the Unity csproj file by running `dotnet build`. Resolve any GMA SDK
    related compile errors.

### Links

Additional documentation:

-   https://developers.google.com/admob/unity/banner.md.txt
