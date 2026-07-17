# IMA SDK HTML5 iframe mode

This guide covers best practices when you can only use the Google IMA SDK for
HTML5 within iframes.

## Prioritize top page level over iframe

You should try to add the IMA SDK script at the top page level. The page level
is preferred over the use of IMA SDK inside an iframe.

### Same-origin iframe fallback

If you detect that the IMA SDK script is inside an iframe, ensure that the
iframe containing the IMA SDK script, the container page, and the video player
all reside on the same domain.

For example: check inside the iframe for access of the top window location.

```typescript
function hasAccessToTopWindow(): boolean {
  try {
    // 1. Check if the current context is already the top window.
    if (window === window.top) {
      return true;
    }

    // 2. Attempt a same-origin read on the top window location.
    // If cross-origin limits apply, this read will throw a DOMException.
    const topUrl = window.top.location.href;
    return true;
  } catch (error) {
    // 3. A SecurityError DOMException was thrown.
    // When this error happens, the SDK is isolated in a cross-origin iframe
    // and does not have direct access to the top-level window.
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error("Access to top-level window is blocked: ", errorMessage);
    return false;
  }
}

if (hasAccessToTopWindow()) {
  console.log("IMA SDK has access to the top-level window.");
} else {
  console.log("IMA SDK is isolated in a cross-origin iframe sandbox.");
}
```

This same-origin setup is required for the SDK to directly access the
`window.top` level, the video player element.

### Cross-origin iframe workaround

If you detect that the IMA SDK is loaded inside an iframe from a domain
different from the domain of the main page containing the video player, you must
provide the main page's URL to the SDK by setting the `adsRequest.pageUrl`
property.

Example code:

```typescript
const adsRequest: google.ima.AdsRequest = new google.ima.AdsRequest();
adsRequest.adTagUrl = 'YOUR_AD_TAG_URL';

// Manually set the page URL to the parent page's URL
adsRequest.pageUrl = 'https://<your_domain>/<path_to_your_page>';
```

Check the `sandbox` attribute of the iframe loading the IMA SDK to grant these
required capabilities:

*   Adding `allow-scripts` for executing the SDK JavaScript. Without this, the
    IMA SDK fails to load and initializes.
*   Adding `allow-same-origin` to let the loaded page read its own cookies.
*   Adding `allow-popups`, `allow-popups-to-escape-sandbox`,
    `allow-top-navigation-by-user-activation` to let the SDK open the
    advertiser's landing page.

```
<iframe sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation" src="PAGE_CONTAINING_IMA_SDK_SCRIPT_TAG">
</iframe>
```