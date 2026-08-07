# AI Integration Agent Instructions for Interstitial Ads

## Required Imports

Use the following imports to implement an interstitial ad:

```
import com.google.android.libraries.ads.mobile.sdk.common.AdRequest
import com.google.android.libraries.ads.mobile.sdk.common.AdLoadCallback
import com.google.android.libraries.ads.mobile.sdk.common.FullScreenContentError
import com.google.android.libraries.ads.mobile.sdk.common.LoadAdError
import com.google.android.libraries.ads.mobile.sdk.interstitial.InterstitialAd
import com.google.android.libraries.ads.mobile.sdk.interstitial.InterstitialAdEventCallback
```

## Method Signatures

Use the following method signatures to implement interstitial ads:

The `AdRequest` object takes the ad unit ID:

```
AdRequest.Builder(adUnitId: String).build()
```

The method signature to load an ad from `InterstitialAd`:

```
fun load(
    adRequest: AdRequest,
    adLoadCallback: AdLoadCallback<InterstitialAd>
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

## Interstitial ad workflow

1.  **Load the ad**

2.  **Register for ad event callbacks**
    -   [ ] Set the `adEventCallback` on the `InterstitialAd` object.
        *   Drop the reference to the interstitial ad when the ad is dismissed
            or fails to show.

3.  **Show the ad**

4.  **Verify the implementation**: Verify the build to ensure there are no
    compile errors:
    -   [ ] Run `gradle build -x test` to confirm a successful clean build.
        Resolve any GMA SDK related compile errors.

#### Troubleshooting

**ONLY** if you exhaust your internal knowledge and not able to complete the
workflow steps, read
https://developers.google.com/admob/android/next-gen/interstitial.md.txt and try
again.
