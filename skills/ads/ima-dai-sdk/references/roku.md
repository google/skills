# Google IMA SDK DAI - Roku Integration Guide

This guide covers the integration steps for the Google IMA SDK for Roku DAI, which is designed for Roku SceneGraph (RSG) applications using BrightScript.

--------------------------------------------------------------------------------

## 1. SDK Download & CLI Setup

Download and install the Roku IMA SDK package into your Roku channel project structure using terminal CLI commands:

```bash
# 1. Download the latest SDK package zip
curl -L -O https://pubads.g.doubleclick.net/html5/shared/js/sdks/roku/v3/roku_ima_sdk.zip

# 2. Extract the package
unzip roku_ima_sdk.zip -d roku_ima_sdk

# 3. Copy SDK components directly into your Roku channel project package structure
cp roku_ima_sdk/components/ImaSdk.brs components/
cp roku_ima_sdk/components/ImaSdkTask.xml components/
```

Include `ImaSdk.brs` and `ImaSdkTask.xml` inside your Roku project's `components/` directory so SceneGraph can load the SDK task node.

--------------------------------------------------------------------------------

## 2. Component Initialization

The Roku IMA SDK runs as a background `Task` node to avoid blocking the main render thread. Create the `ImaSdkTask` SceneGraph node in BrightScript:

```brightscript
sub init()
  m.video = m.top.findNode("myVideo")

  ' Create the ImaSdkTask SceneGraph node using createObject("roSGNode", "ImaSdkTask")
  m.imaTask = createObject("roSGNode", "ImaSdkTask")
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

When the stream is loaded, the SDK Task will return the stream URL via `streamInfo`. You must pass this URL to your `Video` node.

```brightscript
sub onSdkLoaded(event as Object)
  streamInfo = event.getData()
  if streamInfo <> invalid and streamInfo.url <> invalid
    ' Set the stream URL to the Video node
    videoContent = createObject("roSGNode", "ContentNode")
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

## 5. Ad Event & Trickplay Control

Roku OS does **NOT** automatically block seek or fast-forward inputs during ad breaks. You must explicitly control trickplay state when ad breaks begin and end.

```brightscript
sub onAdEvent(event as Object)
  adEvent = event.getData()
  if adEvent <> invalid
    if adEvent.type = "AD_BREAK_STARTED"
      ' Disable seek/rewind/fast-forward trickplay on the Video node
      m.video.enableTrickPlay = false
    else if adEvent.type = "AD_BREAK_ENDED"
      ' Re-enable trickplay controls
      m.video.enableTrickPlay = true
    end if
  end if
end sub

' Intercept remote key press events if your channel implements custom seeking UI
function onKeyEvent(key as String, press as Boolean) as Boolean
  handled = false
  if m.adIsPlaying
    if key = "fastforward" or key = "rewind" or key = "left" or key = "right"
      ' Block custom seeking during ad breaks
      handled = true
    end if
  end if
  return handled
end function
```

--------------------------------------------------------------------------------

## 6. Roku-Specific Considerations

*   **Trickplay Control:** Roku does NOT automatically enforce ad lockouts. You must explicitly set `enableTrickPlay = false` during `AD_BREAK_STARTED` and intercept remote key presses in `onKeyEvent` if custom seek controls are present.
*   **Keep-Alive:** The `ImaSdkTask` node must remain running for the duration of the stream to send ad tracking pings. Do not destroy it until video playback ends.

