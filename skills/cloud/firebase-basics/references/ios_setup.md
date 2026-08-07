# Firebase iOS Setup Guide

## ⛔️ CRITICAL RULE: STATE MANAGEMENT (OBSERVATION VS COMBINE) ⛔️

When writing or updating SwiftUI code, you **MUST** prioritize the modern Swift
**Observation framework (`@Observable` macro and `@State`)** as your default
approach.

However, it is acceptable to use **Combine** (`ObservableObject`, `@Published`,
`@StateObject`, `@EnvironmentObject`) under the following conditions:

-   The user explicitly asks you to use Combine.
-   There are strong signals in the existing codebase that the project is
    heavily relying on Combine.

If neither of those conditions are true, default to the Swift 5.9+ Observation
framework.

## ⛔️ CRITICAL RULE: INITIALIZATION ORDER ⛔️

When using SwiftUI, you **MUST** ensure `FirebaseApp.configure()` is called
**BEFORE** any Firebase-dependent state objects are initialized.

-   **UNSAFE (CRASH):** Declaring a `@State` (for `@Observable`) or
    `@StateObject` (for Combine) property in the root `App` struct if its
    initializer touches Firebase. Property initializers run *before* the
    `App.init()` body, meaning the object's `init()` will fire before Firebase
    is configured.
-   **SAFE:** Initialize Firebase in `App.init()` and pass your state objects
    into the sub-views (like `ContentView`), or use `onAppear` for delayed
    setup.

Failing to follow this will result in a fatal crash: `Default FirebaseApp is not
configured`.

## 1. Create a Firebase Project and App (Automated)

Do not use the Firebase Console. Use the CLI to automate setup:

1.  Create the project: `npx -y firebase-tools@latest projects:create`
1.  Action: Read the Xcode project (`.pbxproj` or `Info.plist`) to determine the
    iOS bundle ID.
1.  Register the iOS app: `npx -y firebase-tools@latest apps:create IOS
    <bundle-id>`
1.  Fetch the config: `npx -y firebase-tools@latest apps:sdkconfig IOS <App-ID>`
1.  Save the output as `GoogleService-Info.plist` in your Xcode project folder.
    Ensure you remove any non-XML CLI output headers, and ensure the file is
    linked to the main application target.

## 2. Installation (Automated via Swift Package Manager CLI)

Do not use raw text parsing, sed, or Ruby scripts (like `xcodeproj` gem) to
modify `.pbxproj` files directly.

Instead, use the **`xcode-project-setup`** skill. Load that skill using your
tools to securely execute its native Swift package setup script. That skill
handles installing the required SPM packages and safely linking the
`GoogleService-Info.plist` file.

> **💡 TIP: ALWAYS USE THE LATEST SDK VERSION** To ensure access to the latest
> features and security fixes, always check for the most recent version of the
> Firebase iOS SDK at
> [https://github.com/firebase/firebase-ios-sdk/releases](https://github.com/firebase/firebase-ios-sdk/releases)
> and use that version when adding the SPM dependency.

## 3. Initialization

Configure the shared `FirebaseApp` instance. You can do this either in a modern
SwiftUI `App` structure or a traditional `AppDelegate`.

### SwiftUI (Modern - SAFE PATTERN)

```swift
import SwiftUI
import FirebaseCore

@main
struct YourApp: App {
  // ⛔️ FATAL CRASH: @State private var auth = AuthManager()
  // property initializers run before init(), causing FirebaseApp not configured error
  @State private var authManager: AuthManager

  init() {
    // ✅ SAFE: This runs FIRST
    FirebaseApp.configure()

    // ✅ SAFE: Initialize state ONLY AFTER Firebase is configured
    _authManager = State(initialValue: AuthManager())
  }

  var body: some Scene {
    WindowGroup {
      ContentView()
        .environment(authManager)
    }
  }
}
```

### AppDelegate (Traditional / UIKit)

```swift
import UIKit
import FirebaseCore

@main
class AppDelegate: UIResponder, UIApplicationDelegate {
  func application(_ application: UIApplication,
                   didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey : Any]? = nil) -> Bool {
    // ✅ SAFE: Always the first line in didFinishLaunching
    FirebaseApp.configure()
    return true
  }
}
```
