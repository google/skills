# Google IMA DAI SDK Roku - StreamManager Guide

For Google full-service DAI, use `CreateLiveStreamRequest` to request a
livestream and `CreateVodStreamRequest` to request a VOD stream.

## Table of Contents

*   [Import the IMA DAI SDK](#import-the-ima-dai-sdk) (Line 21)
*   [SDK Initialization](#sdk-initialization) (Line 43)
*   [Video Player Setup](#video-player-setup) (Line 54)
*   [Make Stream Requests](#make-stream-requests) (Line 87)
    *   [Request a livestream](#request-a-livestream) (Line 89)
    *   [Request a VOD stream](#request-a-vod-stream) (Line 105)
    *   [Execute stream request](#execute-stream-request) (Line 126)
*   [Start Stream Playback](#start-stream-playback) (Line 153)
*   [Timed Metadata Forwarding](#timed-metadata-forwarding) (Line 177)
*   [Listen to Ad Events](#listen-to-ad-events) (Line 205)
    *   [Skippable Ads Support](#skippable-ads-support) (Line 244)
*   [Reference Implementation](#reference-implementation) (Line 256)

## Import the IMA DAI SDK

Add the required libraries to `manifest`:

```
bs_libs_required=roku_ads_lib,googleima3
```

Create a Task component `components/Sdk.xml` to load libraries and run the SDK
on a background thread:

```xml
<component name="imasdk" extends="Task">
  <script type="text/brightscript">
    <![CDATA[
      Library "Roku_Ads.brs"
      Library "IMA3.brs"
    ]]>
  </script>
</component>
```

## SDK Initialization

Initialize the IMA SDK instance using `New_IMASDK()`:

```brightscript
if m.sdk = invalid
  m.sdk = New_IMASDK()
  m.sdk.initSdk()
end if
```

## Video Player Setup

Create the player instance with `sdk.createPlayer()`.

```brightscript
m.player = m.sdk.createPlayer()
m.player.top = m.top
```

Create ad break callbacks:

```brightscript
m.player.loadUrl = Function(urlData)
  m.top.video.enableTrickPlay = false
  m.top.urlData = urlData
End Function

m.player.adBreakStarted = Function(adBreakInfo as Object)
  m.top.adPlaying = true
  m.top.video.enableTrickPlay = false
End Function

m.player.adBreakEnded = Function(adBreakInfo as Object)
  m.top.adPlaying = false
  m.top.video.enableTrickPlay = true
End Function

m.player.seek = Function(timeSeconds as Double)
  m.top.video.seekMode = "accurate"
  m.top.video.seek = timeSeconds
End Function
```

## Make Stream Requests

### Request a livestream

```brightscript
streamRequest = m.sdk.CreateLiveStreamRequest(
  <ASSET_KEY_PLACEHOLDER>,
  "", ' Replace the empty string with a Google DAI API key if the app uses one
  <NETWORK_CODE_PLACEHOLDER>
)
```

Provide the following parameters:

*   **<NETWORK_CODE_PLACEHOLDER>**: The Google Ad Manager network code.
*   **<ASSET_KEY_PLACEHOLDER>**: The livestream asset key configured in Google
    Ad Manager.

### Request a VOD stream

```brightscript
streamRequest = m.sdk.CreateVodStreamRequest(
  <CONTENT_SOURCE_ID_PLACEHOLDER>,
  <VIDEO_ID_PLACEHOLDER>,
  "", ' Replace the empty string with a Google DAI API key if the app uses one
  <NETWORK_CODE_PLACEHOLDER>
)
```

Provide the following parameters:

*   **<NETWORK_CODE_PLACEHOLDER>**: The Google Ad Manager network code.
*   **<CONTENT_SOURCE_ID_PLACEHOLDER>**: The content source ID (CMS ID) in
    Google Ad Manager.
*   **<VIDEO_ID_PLACEHOLDER>**: The video ID in the CMS.

For testing purposes, use values of DAI sample streams from
https://developers.google.com/ad-manager/dynamic-ad-insertion/streams.md.txt?utm_source=agent-skills&utm_medium=content&utm_campaign=adr-ss-ai&utm_content=ima-dai-sdk

### Execute stream request

Pass the player object and video node reference (`adUiNode`) to the request.

```brightscript
streamRequest.player = m.player
streamRequest.adUiNode = m.top.findNode("myVideo")
requestResult = m.sdk.requestStream(streamRequest)
If requestResult <> Invalid
  print "Error requesting stream ";requestResult
Else
  m.streamManager = Invalid
  While m.streamManager = Invalid
    sleep(50)
    m.streamManager = m.sdk.getStreamManager()
  End While
  If m.streamManager = Invalid or (m.streamManager["type"] <> Invalid and m.streamManager["type"] = "error")
    errors = CreateObject("roArray", 1, True)
    print "error ";m.streamManager["info"]
    errors.push(m.streamManager["info"])
    m.top.errors = errors
  Else
    m.streamManager.start()
  End If
End If

```

## Start Stream Playback

Listen for the stream manifest data in `MainScene.xml` and pass it to the
`Video` node:

```brightscript
m.sdkTask.observeField("urlData", "urlLoadRequested")
' Setting control to run starts the task thread.
m.sdkTask.control = "RUN"

Sub urlLoadRequested(message as Object)
  data = message.getData()
  vidContent = createObject("RoSGNode", "ContentNode")
  vidContent.url = data.manifest
  vidContent.title = m.videoTitle
  vidContent.streamformat = data.format
  m.video.content = vidContent
  m.video.setFocus(true)
  m.video.visible = true
  m.video.control = "play"
  m.video.EnableCookies()
End Sub
```

## Timed Metadata Forwarding

Forward all timed metadata and video node events to
`StreamManager.onMessage(msg)` during stream playback:

```brightscript
m.top.video.timedMetaDataSelectionKeys = ["*"]

m.port = CreateObject("roMessagePort")
fields = m.top.video.getFields()
for each field in fields
  m.top.video.observeField(field, m.port)
end for

while true
  msg = wait(1000, m.port)
  if m.top.video = invalid
    exit while
  end if

  m.streamManager.onMessage(msg)
  currentTime = m.top.video.position
  if currentTime > 3 and not m.top.adPlaying
    m.top.video.enableTrickPlay = true
  end if
end while
```

## Listen to Ad Events

Register event listeners on `m.streamManager` to monitor ad lifecycle and error
events:

```brightscript
m.streamManager.addEventListener(m.sdk.AdEvent.ERROR, errorCallback)
m.streamManager.addEventListener(m.sdk.AdEvent.START, startCallback)
m.streamManager.addEventListener(m.sdk.AdEvent.FIRST_QUARTILE, firstQuartileCallback)
m.streamManager.addEventListener(m.sdk.AdEvent.MIDPOINT, midpointCallback)
m.streamManager.addEventListener(m.sdk.AdEvent.THIRD_QUARTILE, thirdQuartileCallback)
m.streamManager.addEventListener(m.sdk.AdEvent.COMPLETE, completeCallback)

Function startCallback(ad as Object) as Void
  print "Ad event: START"
End Function

Function firstQuartileCallback(ad as Object) as Void
  print "Ad event: FIRST_QUARTILE"
End Function

Function midpointCallback(ad as Object) as Void
  print "Ad event: MIDPOINT"
End Function

Function thirdQuartileCallback(ad as Object) as Void
  print "Ad event: THIRD_QUARTILE"
End Function

Function completeCallback(ad as Object) as Void
  print "Ad event: COMPLETE"
End Function

Function errorCallback(error as Object) as Void
  print "Ad event: ERROR - "; error
  m.errorState = true
End Function
```

### Skippable Ads Support

To support skippable ads, implement the `seek` callback method on `m.player` and
ensure `streamRequest.adUiNode` is set to the video node in the stream request:

```brightscript
m.player.seek = Function(timeSeconds as Double)
  m.top.video.seekMode = "accurate"
  m.top.video.seek = timeSeconds
End Function
```

## Reference Implementation

BasicExample:

*   [Sdk.xml](https://raw.githubusercontent.com/googleads/googleads-ima-roku-dai/refs/heads/main/basic_example/components/Sdk.xml)
*   [MainScene.xml](https://raw.githubusercontent.com/googleads/googleads-ima-roku-dai/refs/heads/main/basic_example/components/MainScene.xml)
