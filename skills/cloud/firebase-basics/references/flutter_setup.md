# Flutter & Firebase Setup Guide

This guide covers the initial setup of Flutter and its integration with Firebase
using the FlutterFire CLI.

## Prerequisites

1.  **Flutter SDK**: Ensure Flutter is installed and available in the PATH.

    **Standard Setup (Manual):**

    1.  **Determine Architecture**: Check if you are on Intel (`x64`) or Apple
        Silicon (`arm64`) using `uname -m`.
    1.  **Download SDK**: Fetch the latest stable SDK from the
        [Flutter Archive](https://docs.flutter.dev/install/archive?tab=macos).
    1.  **Extract**: Unzip the SDK to a permanent directory (e.g.,
        `~/development/flutter`).
    1.  **Update PATH**: Add the `bin` folder to your shell configuration (e.g.,
        `~/.zshrc`).

        ```bash
        echo 'export PATH="$PATH:$HOME/development/flutter/bin"' >> ~/.zshrc
        source ~/.zshrc
        ```

    1.  **Verify**: Run `flutter doctor` to ensure the SDK is correctly linked
        and initialized.

1.  **Firebase CLI**: Ensure the Firebase CLI is available.

    -   Run `npx -y firebase-tools@latest --version`.
    -   Login with `npx -y firebase-tools@latest login`.

1.  **FlutterFire CLI**: Install the official FlutterFire CLI globally.

    -   Run `dart pub global activate flutterfire_cli`.
    -   **Note**: Ensure `~/.pub-cache/bin` is also in your PATH if
        `flutterfire` is not found.

## Step 1: Create a Flutter Project

If you don't have a project yet, create one:

```bash
flutter create my_awesome_app
cd my_awesome_app
```

## Step 2: Configure Firebase

> [!IMPORTANT] **For Agents:** Before running the configuration command, you
> MUST pause and ask the developer if they prefer to:
>
> 1.  Create a new Firebase project, or
> 1.  Provide an existing Firebase Project ID.

-   If the developer provides an existing Project ID, run:

    ```bash
    flutterfire configure --project=<project_id>
    ```

-   If the developer prefers to create a new project interactively, run:

    ```bash
    flutterfire configure
    ```

This tool automates:

-   Registering your apps (iOS, Android, Web, etc.) with a Firebase project.
-   Generating the `lib/firebase_options.dart` file.

## Step 3: Initialize Firebase in Code

Add the `firebase_core` package and initialize it in your `main.dart`.

1.  Add the dependency:

```bash
flutter pub add firebase_core
```

2.  Update `lib/main.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'firebase_options.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );
  runApp(const MyApp());
}
```

## Step 4: Add Firebase Services

To add specific services (Firestore, Auth, etc.), follow the "Pub Add &
Configure" pattern:

1.  Add the service: `flutter pub add cloud_firestore`
1.  **Crucial**: Re-run `flutterfire configure` to sync platform configurations.
1.  Import and use the package in your code.

## Step 5: Important Gotchas & Platform Specifics

### 1. Re-running `flutterfire configure` Upon Renaming

When creating a new project, developers often change the bundle identifier (iOS)
or `applicationId` (Android) after the fact. If the package names change,
`flutterfire configure` **must** be re-run to update the respective Google
service files and `firebase_options.dart`.

### 2. Platform-Specific Build Requirements

-   **Android**: Adding Firebase often requires a higher `minSdkVersion`
    (commonly `21` or `23`) than the platform default. Be prepared to update
    `android/app/build.gradle` automatically when installing certain plugins.
-   **iOS**: Always check if there is a `Podfile` in the `/ios` directory
    whenever native services (like `cloud_firestore`) are added. If there is,
    run `pod install`. Failing to do this will cause Xcode build errors. Note
    that Flutter is moving towards Swift Package Manager (SPM), and FlutterFire
    supports SPM, so a `Podfile` may not exist if the project only uses SPM
    dependencies.

### 3. Web CORS Best Practices

When testing Firebase features locally on Chrome, requests to Google servers can
sometimes get blocked by CORS policies. Avoid relying on
`--disable-web-security` flags as it promotes bad security practices. Instead,
run the app on localhost with a specific port, and ensure `localhost` is added
to your Firebase Auth "Authorized Domains".

```bash
flutter run -d chrome --web-hostname=localhost --web-port=5000
```

### 4. Elaborating on `WidgetsFlutterBinding.ensureInitialized()`

In your `main.dart`, this call is mandatory before `Firebase.initializeApp()`.
*Why?* Because Firebase initialization requires communication across Flutter's
native iOS/Android method channels. `ensureInitialized()` guarantees the Fluter
engine is fully booted up and ready to handle these native platform calls before
`runApp()` executes.
