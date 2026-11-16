# Intermediate Iframe API Integration Guide (`gsi/intermediate`)

When Google One Tap or Sign In With Google must be embedded inside cross-origin
iframes or embedded widgets (where top-level direct script execution is
restricted), use the Intermediate Iframe helper pattern
(`https://developers.google.com/identity/gsi/web/amp/nonamp-reference`).

## 1. Intermediate Frame Markup & Script (`intermediate.html` on publisher origin)

```html
<!DOCTYPE html>
<html>
<head>
  <!-- Dedicated intermediate helper library -->
  <script src="https://accounts.google.com/gsi/intermediate"></script>
</head>
<body>
  <div id="g_id_intermediate_iframe"
       data-src="https://publisher.example.com/onetap_inner.html">
  </div>
</body>
</html>
```

## 2. Intermediate JavaScript Initialization & Secure PostMessage Relay

```javascript
// Inside the intermediate iframe helper script
window.google?.accounts?.id?.initialize({
  client_id: 'YOUR_CLIENT_ID.apps.googleusercontent.com',
  allowed_parent_origin: 'https://publisher.example.com',
  callback: (response) => {
    if (response.credential) {
      // Securely forward credential to trusted top-level parent window only
      const trustedParentOrigin = 'https://publisher.example.com';
      window.parent.postMessage(
        { type: 'GSI_CREDENTIAL', credential: response.credential },
        trustedParentOrigin // Explicit target origin prevents exfiltration
      );
    }
  }
});
```

## 3. Top-Level Parent Frame Event Listener with Strict Origin Assertion

```javascript
// On the top-level parent window
window.addEventListener('message', (event) => {
  // 1. Strict Origin Validation - MANDATORY
  if (event.origin !== 'https://publisher.example.com') {
    return; // Reject untrusted cross-origin messages
  }

  if (event.data?.type === 'GSI_CREDENTIAL') {
    const idToken = event.data.credential;
    // Process token via Pattern A (BFF backend forward) or Pattern C (In-memory)
    console.log('Received authenticated credential from intermediate iframe');
  }
});
```
