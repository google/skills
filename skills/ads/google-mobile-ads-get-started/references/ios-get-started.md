# AI Integration Agent Instructions for the iOS Google Mobile Ads SDK

## Gotchas

Google Mobile Ads SDK uses `NS_SWIFT_NAME` macros to provide idiomatic Swift
names.

## SDK Integration Workflow

1.  **Add the SDK dependency**:

    -   [ ] Run the following command to fetch the latest version. The tag
        returned is the latest version of the Google Mobile Ads SDK:

        ```bash
        curl -sS https://api.github.com/repos/googleads/swift-package-manager-google-mobile-ads/releases/latest | jq -r '.tag_name'
        ```

    -   [ ] Check if Ruby is installed and the `xcodeproj` Ruby gem is available
        by running `ruby -e "require 'xcodeproj'"`.

        -   **If Ruby and `xcodeproj` are available**: Locate the `.xcodeproj`
            directory and primary app target, then write a temporary Ruby script
            to programmatically add the
            `GoogleMobileAds` Swift Package
            (`https://github.com/googleads/swift-package-manager-google-mobile-ads.git`)
            using the **Up to Next Major Version** dependency rule starting with
            the fetched version as a target dependency.

        -   **Fallback / Manual Installation**: If Ruby or `xcodeproj` is not
            available, or if the script execution fails, do **NOT** attempt to
            troubleshoot, retry, or install Ruby or `xcodeproj`. You MUST
            default to outputting instructions directing the user to manually
            add the `GoogleMobileAds` Swift package in Xcode.

2.  **Set the application identifier**:

    -   [ ] If there is no `GADApplicationIdentifier` already present, add the
        `GADApplicationIdentier` to the `Info.plist` file with a sample AdMob
        App ID of `ca-app-pub-3940256099942544~1458002511`. Remind the user to
        replace it with their actual AdMob App ID before publishing.
    -   [ ] Add the `SKAdNetwork` identifiers from
        `assets/skadnetwork-identifiers.xml` to the `Info.plist` file.

3.  **Initialize the SDK**:

    -   [ ] Initialize the SDK in the appropriate entry point of the
        application. You **MUST** use the following code snippet when working
        with Swift:

        ```
        MobileAds.shared.start { status in
            print("SDK initialized.")
        }
        ```

4.  **Verify the integration**:

    -   [ ] Verify the build to ensure there are no compile errors:
        -   **When `xcodebuild` is available**: Run `xcodebuild` to
            programmatically verify that the iOS project compiles properly with
            the GMA SDK. Resolve any GMA SDK related compile errors.
        -   **When `xcodebuild` is NOT available**: Output instructions
            directing the user to build the project in Xcode and manually verify
            there are no compile errors.

#### Troubleshooting

**ONLY** if you exhaust your internal knowledge and not able to complete the
workflow steps, read
https://developers.google.com/admob/ios/quick-start.md.txt and try again.
