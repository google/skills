
## Optional: quick test without bundletool

`quick_test/` holds a copy of each Google Tensor build, laid out so that the
debug APK can carry it together with the NPU runtime. Then
`./gradlew installDebug` runs the model on your Pixel's TPU, without
bundletool, the AI pack or the runtime feature module. It is for trying the
model on your own phone only: nothing changes unless you pass
`-PtensorQuickTest`, and even then only the debug build changes, so what you
upload to Google Play is unaffected.

1. Copy `quick_test/` to `{{APP_MODULE_DIR}}/tensor_quick_test/`. It holds a
   full copy of each build, so you may want to add it to `.gitignore`.
2. Add at the end of `{{APP_MODULE_DIR}}/build.gradle.kts`:

   ```kotlin
   // Quick test on a Pixel without bundletool (debug builds only):
   //   ./gradlew :{{APP_MODULE}}:installDebug -PtensorQuickTest={{FIRST_SOC}}
   // The debug APK then carries the Google Tensor build and the NPU runtime.
   providers.gradleProperty("tensorQuickTest").orNull?.let { soc ->
     android.sourceSets.getByName("debug")
       .assets.srcDir("tensor_quick_test/$soc/assets")
     dependencies.add(
       "debugImplementation",
       "com.google.ai.edge.litert:litert-npu-runtime-google-tensor:{{LITERT_MAVEN_RELEASE}}",
     )
   }
   ```

   Groovy DSL: `def soc = providers.gradleProperty('tensorQuickTest').orNull`,
   then, inside `if (soc != null) { ... }`,
   `android.sourceSets.debug.assets.srcDir("tensor_quick_test/$soc/assets")`
   and the same `dependencies.add(...)` call.
3. Run `./gradlew :{{APP_MODULE}}:installDebug -PtensorQuickTest=<SoC>`, with
   the phone's SoC written with an underscore: `adb shell getprop ro.soc.model`
   prints `Tensor G5` for `Tensor_G5` (this package has builds for
   {{QUICK_TEST_SOCS}}). Start the app and check
   `adb logcat -s LiteRtTensor` for `"path":"npu"`.

Without `-PtensorQuickTest`, `installDebug` installs the base APK only, and
the model runs on the CPU.
