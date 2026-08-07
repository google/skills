# AI Integration Agent Instructions for the Android GMA Next-Gen SDK

## Required Imports

Use the following imports to initialize the GMA Next-Gen SDK:

```
import com.google.android.libraries.ads.mobile.sdk.MobileAds
import com.google.android.libraries.ads.mobile.sdk.initialization.InitializationConfig
import com.google.android.libraries.ads.mobile.sdk.initialization.InitializationStatus
import com.google.android.libraries.ads.mobile.sdk.initialization.OnAdapterInitializationCompleteListener
```

## Method Signatures

Use the following method signature to initialize the GMA Next-Gen SDK:

```
fun initialize(
    context: Context,
    initializationConfig: InitializationConfig,
    listener: OnAdapterInitializationCompleteListener?
): Unit
```

The `InitializationConfig` object takes the AdMob App ID:

```
InitializationConfig.Builder("ca-app-pub-3940256099942544~3347511713").build()
```

The `OnAdapterInitializationCompleteListener` interface is defined as:

```
fun interface OnAdapterInitializationCompleteListener {
    fun onAdapterInitializationComplete(status: InitializationStatus): Unit
}
```

## SDK Integration Workflow

1.  **Add the SDK dependency**:
    -   [ ] **ALWAYS** Add the latest stable version of
        `com.google.android.libraries.ads.mobile.sdk:ads-mobile-sdk` to
        dependencies. If you cannot access Maven directly, run the following
        command to fetch the latest version. The version returned in the
        `latest` tag is the latest version of the Google Mobile Ads SDK:

        ```bash
        curl -sS https://dl.google.com/dl/android/maven2/com/google/android/libraries/ads/mobile/sdk/ads-mobile-sdk/maven-metadata.xml | sed -n 's/.*<latest>\(.*\)<\/latest>.*/\1/p'
        ```

    -   [ ] Configure `minSdk` (24+) and `compileSdk` (34+).
    -   [ ] Exclude `play-services-ads` and `play-services-ads-lite` from all
        dependencies globally in the app-level build file to avoid duplicate
        symbol errors.
    -   [ ] Sync Gradle before moving on to the next step.

2.  **Set the application identifier**:
    -   [ ] Pass the `applicationId` parameter programmatically in the
        `InitializationConfig.Builder` with a sample AdMob App ID of
        `ca-app-pub-3940256099942544~3347511713`. Remind the user to replace it
        with their actual AdMob App ID before publishing.

3.  **Initialize the SDK**:
    -   [ ] **ALWAYS** initialize the SDK on a background thread.

4.  **Verify the integration**:
    -   [ ] Run `gradle build -x test` to confirm a successful clean build.
        Resolve any GMA SDK related compile errors.

#### Troubleshooting

**ONLY** if you exhaust your internal knowledge and not able to complete the
workflow steps, read
https://developers.google.com/admob/android/next-gen/quick-start.md.txt and try
again.
