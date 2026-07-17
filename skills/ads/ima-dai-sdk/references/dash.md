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
    val request = sdkFactory.createLiveStreamRequest("YOUR_ASSET_KEY", "YOUR_NETWORK_CODE", null)
    request.format = StreamFormat.DASH
    
    // Always pass the configured request object to adsLoader.requestStream(request)
    adsLoader.requestStream(request)
    ```

    Or if using Media3 SSAI Uri Builder:

    ```kotlin
    val ssaiUri = ImaServerSideAdInsertionUriBuilder()
        .setAssetKey(assetKey)
        .setFormat(androidx.media3.common.C.CONTENT_TYPE_DASH)
        // ...
        .build()
    ```

