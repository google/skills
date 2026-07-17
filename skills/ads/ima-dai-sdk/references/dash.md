# Google IMA SDK DAI - DASH Integration Guide

This guide covers DASH stream request configuration with IMA DAI SDK.

When requesting a DASH stream, you set the stream format as follows.

*   **Web (TypeScript):**

    ```typescript
    const streamRequest = new google.ima.dai.api.LiveStreamRequest();
    streamRequest.format = 'dash'; // the format property is also available for
                                  // VODStreamRequest,
                                  // PodStreamRequest, PodVodStreamRequest.
    ```

*   **Android (Kotlin):**

    ```kotlin
    val request = sdkFactory.createLiveStreamRequest(...)
    request.format = StreamFormat.DASH
    ```

    Or if using Media3 SSAI Uri Builder:

    ```kotlin
    val ssaiUri = ImaServerSideAdInsertionUriBuilder()
        .setAssetKey(assetKey)
        .setFormat(androidx.media3.common.C.CONTENT_TYPE_DASH)
        // ...
        .build()
    ```
