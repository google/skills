# AI Integration Agent Instructions for Rewarded Ads

## Gotchas

Google Mobile Ads SDK uses `NS_SWIFT_NAME` macros to provide idiomatic Swift
names.

## Rewarded ad workflow

1.  **Load the ad**
    *   For Swift code, use `async/await` instead of a completion handler.

2.  **Register for ad event callbacks**
    -   [ ] Set the `fullScreenContentDelegate` on the `RewardedAd` object.
        *   Drop the reference to the rewarded ad when the ad is dismissed
            or fails to show.

3.  **Add an opt-in UI element** to give users the choice to watch the rewarded
    ad in exchange for an in-app reward.

4.  **Show the ad**
    *   **ViewController Parameter:** The `rootViewController` parameter in the
    `present(from:)` method is an optional parameter and can be set to `nil`.
    *   The `present(from:)` method requires a `UserDidEarnRewardHandler`
        object.

5.  **Verify the implementation**: Verify the build to ensure there are no
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
https://developers.google.com/admob/ios/rewarded.md.txt and try again.
