# Google IMA SDK DAI - Roku Integration Guide

This guide covers the integration steps for the Google IMA SDK for Roku DAI,
which is designed for Roku SceneGraph (RSG) applications using BrightScript.

--------------------------------------------------------------------------------

## 1. SDK Setup

Download Roku IMA SDK zip package using the following commands:

```bash
curl -L -O https://pubads.g.doubleclick.net/html5/shared/js/sdks/roku/v3/roku_ima_sdk.zip
```

Install the IMA SDK to your app.

--------------------------------------------------------------------------------

## 2. Initialization

The Roku IMA SDK runs as a background `Task` node to prevent blocking the main
render thread.

```brightscript
sub init()
  m.video = m.top.findNode("myVideo")

  ' Create the IMA SDK Task node
  m.imaTask = createObject("RoSGNode", "ImaSdkTask")
  m.imaTask.observeField("sdkLoaded", "onSdkLoaded")
  m.imaTask.observeField("errors", "onSdkErrors")
  m.imaTask.observeField("adEvents", "onAdEvent")

  ' Start the task
  m.imaTask.control = "RUN"
end sub
```

--------------------------------------------------------------------------------

## 3. Requesting a Stream

Pass the stream request parameters to the SDK Task.

### A. Live Stream Request

```brightscript
sub requestLiveStream()
  request = {
    assetKey: "YOUR_ASSET_KEY"
    apiKey: "YOUR_API_KEY" ' Optional
    networkCode: "YOUR_NETWORK_CODE"
    type: "live"
  }
  m.imaTask.requestStream = request
end sub
```

### B. VOD Stream Request

```brightscript
sub requestVodStream()
  request = {
    contentSourceId: "YOUR_CMS_ID"
    videoId: "YOUR_VIDEO_ID"
    apiKey: "YOUR_API_KEY" ' Optional
    networkCode: "YOUR_NETWORK_CODE"
    type: "vod"
  }
  m.imaTask.requestStream = request
end sub
```

--------------------------------------------------------------------------------

## 4. Handling Stream Load & Playback

When the stream is loaded, the SDK Task will return the stream URL via
`streamInfo`. You must pass this URL to your `Video` node.

```brightscript
sub onSdkLoaded(event as Object)
  streamInfo = event.getData()
  if streamInfo <> invalid and streamInfo.url <> invalid
    ' Set the stream URL to the Video node
    videoContent = createObject("RoSGNode", "ContentNode")
    videoContent.url = streamInfo.url
    videoContent.streamFormat = "hls"

    m.video.content = videoContent
    m.video.control = "play"

    ' Important: Pass the Video node to the SDK so it can monitor playback progress
    m.imaTask.videoNode = m.video
  end if
end sub
```

--------------------------------------------------------------------------------

## 5. Ad Event Handling

Monitor `adEvents` to manage player controls (like disabling trickplay/seeking
during ads).

```brightscript
sub onAdEvent(event as Object)
  adEvent = event.getData()
  if adEvent <> invalid
    if adEvent.type = "AD_BREAK_STARTED"
      ' Disable seek/rewind/fast-forward
      m.video.enableTrickPlay = false
    else if adEvent.type = "AD_BREAK_ENDED"
      ' Re-enable trickplay
      m.video.enableTrickPlay = true
    end if
  end if
end sub
```

--------------------------------------------------------------------------------

## 6. Roku-Specific Considerations

*   **Trickplay Control:** You must explicitly disable `enableTrickPlay` on the
    `Video` node during ad breaks, as Roku does not automatically block user
    seek inputs.
*   **Keep-Alive:** The `ImaSdkTask` must remain running for the duration of the
    stream to handle tracking pings. Do not destroy it until the video is
    closed.
