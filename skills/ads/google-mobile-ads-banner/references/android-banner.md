# AI Integration Agent Instructions for Android Banner Ads

## Required Imports

Use the following imports to implement a banner ad:

```
import com.google.android.libraries.ads.mobile.sdk.banner.AdSize
import com.google.android.libraries.ads.mobile.sdk.banner.AdView
import com.google.android.libraries.ads.mobile.sdk.banner.BannerAd
import com.google.android.libraries.ads.mobile.sdk.banner.BannerAdRequest
import com.google.android.libraries.ads.mobile.sdk.common.AdLoadCallback
import com.google.android.libraries.ads.mobile.sdk.common.LoadAdError
```

## Method Signatures

Use the following method signatures to implement banner ads:

The `BannerAdRequest` object takes the ad unit ID and `AdSize`:

```
BannerAdRequest.Builder(adUnitId: String, adSize: AdSize).build()
```

The method signature to load a banner ad from `AdView`:

```
fun loadAd(
    adRequest: BannerAdRequest,
    adLoadCallback: AdLoadCallback<BannerAd>
): Unit
```

The `AdLoadCallback` interface is defined as:

```
interface AdLoadCallback<T> {
    fun onAdLoaded(ad: T): Unit
    fun onAdFailedToLoad(adError: LoadAdError): Unit
}
```

## Gotchas

**UI Threading**: **MANDATORY**: Callbacks in GMA-Next Gen SDK are invoked on a
background thread. **ALL UI-RELATED OPERATIONS** (e.g., Toasts, View updates,
Fragment transactions) **MUST** be wrapped in `runOnUiThread {}` or
`Dispatchers.Main.launch {}` within GMA SDK callbacks. SKIPPING THIS STEP WILL
CAUSE THE APPLICATION TO CRASH.

## Banner Ad workflow

1.  **Define the ad view**
    -   [ ] Use `AdView` for defining GMA Next-Gen SDK banners instead of the
        deprecated `BannerAd`.

2.  **Set the ad size**:
    -   [ ] Set the `width` you use for `AdSize` to `360` for testing purposes.
        Mention using the device width is also a common approach.
    -   [ ] Use the appropriate `AdSize` method and test ad unit ID
        (`ca-app-pub-3940256099942544/9214589741`) based on the ad type:
        *   For a **large anchored adaptive banner**: Use
            `AdSize.getLargeAnchoredAdaptiveBannerAdSize(context, width)`.
            *   If given feedback that large anchored adaptive banners are too
                tall, use
                `AdSize.getCurrentOrientationAnchoredAdaptiveBannerAdSize(context, width)`.
        *   For an **inline adaptive banner**: Use
            `AdSize.getCurrentOrientationInlineAdaptiveBannerAdSize(context, width)`.
    -   [ ] Pass the `AdSize` and ad unit ID to the `BannerAdRequest.Builder`,
        not directly on the `AdView`.

3.  **Register for ad load events**:
    -   [ ] Pass the `AdLoadCallback` implementation in the `loadAd()` method,
        not directly on the `AdView`.

4.  **Load the banner ad**:

5.  **Verify the implementation**: Check the build to ensure there are no
    compile errors:
    -   [ ] Run `gradle build -x test` to confirm a successful clean build.
        Resolve any GMA SDK related compile errors.

### Links

Additional documentation:

-   https://developers.google.com/admob/android/next-gen/banner.md.txt
