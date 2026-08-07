# AI Integration Agent Instructions for Interstitial Ads

## Gotchas

Google Mobile Ads SDK uses `NS_SWIFT_NAME` macros to provide idiomatic Swift
names.

## Interstitial ad workflow

1.  **Load the ad**
    *   For Swift code, use `async/await` instead of a completion handler.

2.  **Register for ad event callbacks**
    -   [ ] Set the `fullScreenContentDelegate` on the `InterstitialAd` object.
        *   Drop the reference to the interstitial ad when the ad is dismissed
            or fails to show.

3.  **Show the ad**
    *   **ViewController Parameter:** The `rootViewController` parameter in the
    `present(from:)` method is an optional parameter and can be set to `nil`.

4.  **Verify the implementation**: Verify the build to ensure there are no
    compile errors:
    -   **If `xcodebuild` is available**: Run `xcodebuild` to programmatically
        verify that the iOS project compiles properly with the GMA SDK. Resolve
        any GMA-SDK related compile errors.
    -   **If `xcodebuild` is NOT available**: Output instructions directing the
        user to build the project in Xcode and manually verify there are no
        compile errors.

#### Troubleshooting

**ONLY** if you exhaust your internal knowledge and not able to complete the
workflow steps, read
https://developers.google.com/admob/ios/interstitial.md.txt and try again.