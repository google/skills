# Google IMA HTML5 SDK on Mobile Safari (iOS) guide

This guide covers best practices for the Google Interactive Media Ads (IMA)
HTML5 SDK to support mobile Safari (iOS).

## Essential setup

You must do the following steps:

*   Check and make sure that the `playsinline` attribute is added for the HTML
    `<video>` element.

*   Add a play button to initiate playback by user gesture.

Example:

```html
<!-- This video will attempt to play within its layout on iOS -->
<video playsinline controls></video>
```