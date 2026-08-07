# AI Integration Agent Instructions for Banner Ads

## Gotchas

Google Mobile Ads SDK uses `NS_SWIFT_NAME` macros to provide idiomatic Swift
names.

## Banner ad workflow

1.  **Define the ad view**
    -   [ ] Use the test ad unit ID of `ca-app-pub-3940256099942544/2435281174`.
    *   **ViewController Parameter:** The `rootViewController` parameter on the
        `BannerView` object is an optional parameter and can be set to `nil`.

2.  **Set the ad size**
    -   [ ] Set the `width` you use for `AdSize` to `375` for testing purposes.
        Mention using the device width is also a common approach.
    -   [ ] Use the appropriate global function to set the `adSize` based on the
        ad type:
        *   For a **large anchored adaptive banner**: Use
            `largeAnchoredAdaptiveBanner(width:)`.
            *   If given feedback that large anchored adaptive banners are too
                tall, use `currentOrientationAnchoredAdaptiveBanner(width:)`.
        *   For an **inline adaptive banner**: Use
            `currentOrientationInlineAdaptiveBanner(width:)`.

3.  **Register for ad load events**
    -   [ ] Set the `delegate` on the `BannerView` object.

4.  **Load the banner ad**

5.  **Verify the implementation**: Verify the build to ensure there are no
    compile errors:
    -   **If `xcodebuild` is available**: Run `xcodebuild` to programmatically
        verify that the iOS project compiles properly with the GMA SDK. Resolve
        any GMA-SDK related compile errors.
    -   **If `xcodebuild` is NOT available**: Output instructions directing the
        user to build the project in Xcode and manually verify there are no
        compile errors.

### Links

Additional documentation:

-   https://developers.google.com/admob/ios/banner.md.txt
