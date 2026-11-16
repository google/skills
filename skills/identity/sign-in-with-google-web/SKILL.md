---
name: sign-in-with-google-web
metadata:
  category: Identity
  version: "1.0.1"
description: >-
  Implement, configure, and secure Sign In With Google (SiwG) using Google Identity
  Services (GIS / `https://accounts.google.com/gsi/client`) across web architectures.
  Use when creating Google sign-in buttons, implementing Google One Tap with FedCM,
  integrating GIS in React/Next.js/Angular/HTML, verifying ID tokens on backend
  runtimes (Python/Node.js/Go/Java), enforcing Google Workspace domain restrictions
  (`hd`), securing client-side ID tokens via WebCrypto nonces or encrypted IndexedDB,
  embedding in cross-origin iframes via the Intermediate Iframe API
  (`https://accounts.google.com/gsi/intermediate`), configuring Content Security
  Policy (CSP), COOP, and Permissions Policy (`identity-credentials-get`) headers,
  or handling sign-out and revocation. Don't use for legacy Google Sign-In (`gapi.auth2`),
  Google Cloud IAM service accounts, or Android/iOS native Credential Manager.
---

# Sign In With Google (SiwG) Integration & Security Architecture

This skill provides normative architectural guidelines, secure implementation
contracts, and failure-prevention protocols for integrating Sign In With Google
via the Google Identity Services (GIS) Web SDK
(`https://accounts.google.com/gsi/client`).

## 1. IETF Architecture Taxonomy & Hierarchy (RECOMMEND BFF / TMB FIRST)

All Sign In With Google implementations MUST align with the
[IETF OAuth 2.0 for Browser-Based Applications (`draft-ietf-oauth-browser-based-apps`)](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-browser-based-apps#name-application-architecture-pa)
taxonomy.

> [!IMPORTANT] **Primary Recommendation:** Always recommend backend-mediated
> patterns (**Pattern A: Backend For Frontend** or **Pattern B: Token-Mediating
> Backend / Redirect Mode**) as the most secure, robust, and industry-standard
> architectures whenever an application has a backend server. Fall back to
> client-only browser patterns (Patterns C & D) only when constrained by
> serverless static hosting or offline-first PWA requirements.

<!-- mdformat off(reason: preserve ASCII architecture diagram width) -->
```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                          IETF ARCHITECTURE HIERARCHY & SELECTION                        │
├──────────────────────────┬──────────────────────────┬───────────────────────────────────┤
│ Pattern A (RECOMMENDED): │ Pattern B (RECOMMENDED): │ Patterns C & D (Fallbacks):       │
│ Backend For Frontend     │ Token-Mediating Backend  │ Browser-Based OAuth Client        │
│ (BFF - IETF § 6.1)       │ (TMB / Redirect § 6.2)   │ (JavaScript-Only - IETF § 6.3)    │
├──────────────────────────┼──────────────────────────┼───────────────────────────────────┤
│ 🏆 GOLD STANDARD         │ 🚀 NATIVE FORM REDIRECT  │ ⚡ STATIC SPA / 💾 OFFLINE PWA    │
│ • Full-stack SPA + API   │ • Server-rendered & apps │ • Pure client-side or offline PWAs│
│ • Client JS fetch to API │ • GIS HTTP POST login_uri│ • C: Ephemeral in-memory closure  │
│ • HttpOnly session cookie│ • Direct server redirect │ • D: WebCrypto Encrypted IndexedDB│
│ • Tokens never in browser│ • Tokens never in JS     │ • Strict WebCrypto nonces / keys  │
└──────────────────────────┴──────────────────────────┴───────────────────────────────────┘
```
<!-- mdformat on -->

### 🏆 Pattern A: Backend For Frontend (BFF - IETF § 6.1) — STRONGLY RECOMMENDED

*   **Why it is the Gold Standard**: ID tokens (JWTs) and access tokens are
    never exposed to browser JavaScript across page reloads. This provides
    complete architectural immunity against XSS token harvesting.

*   **Architecture**: The browser frontend loads the GIS SDK, captures the
    credential in JavaScript callback (`callback: handleCredentialResponse`),
    and immediately forwards the ID token (JWT) via `fetch('/api/auth/google', {
    method: 'POST' })` to the backend.

*   **Backend Responsibilities**: The backend validates the JWT cryptographic
    signature against Google's public JWKs
    (`google.oauth2.id_token.verify_oauth2_token`), checks the `aud`, `hd`, and
    `nonce` claims against server session state, creates a server session, and
    issues a first-party `HttpOnly; Secure; SameSite=Lax` session cookie.

*   See full implementation in
    [references/bff_fastapi_verification.md](references/bff_fastapi_verification.md).

### 🚀 Pattern B: Token-Mediating Backend via `login_uri` Redirect (IETF § 6.2) — Server-Rendered & Form POST

*   **Why it is Highly Secure**: Bypasses client-side JavaScript credential
    handling entirely by instructing GIS to perform an HTTP POST directly to the
    backend's `login_uri`.

*   **Architecture**: Configured via `google.accounts.id.initialize({ client_id,
    login_uri: "https://example.com/api/auth/callback", ux_mode: "redirect" })`
    or HTML attributes (`data-login_uri="https://example.com/api/auth/callback"`
    and `data-ux_mode="redirect"`).

*   **Backend Responsibilities**: The backend receives the ID token as a form
    POST body (`credential` parameter), validates the double-submit
    `g_csrf_token` cookie against the `g_csrf_token` POST body field,
    cryptographically verifies the ID token server-side, establishes a session
    cookie, and returns a standard HTTP 302/303 redirect.

*   See full implementation in
    [references/tmb_login_uri_redirect.md](references/tmb_login_uri_redirect.md).

### Pattern C: Browser-Based OAuth Client — Ephemeral In-Memory (IETF § 6.3) — Fallback for Static SPAs

*   **Scope**: Use ONLY when deployment is strictly serverless/static (e.g.,
    GitHub Pages, Firebase static hosting) with no backend component.

*   **Storage Invariant**: The ID token is held strictly in private JavaScript
    memory/closures during the active tab session. **Never store raw tokens in
    `localStorage` or `sessionStorage`**.

*   **Session Renewal**: Uses GIS One Tap / FedCM auto-select (`auto_select:
    true`) to transparently re-acquire fresh ID tokens into memory on page
    reload without persistent browser storage.

*   **XSS & Replay Protection**: Generate a cryptographic `nonce` via
    `window.crypto.getRandomValues()` and pass it directly to
    `google.accounts.id.initialize({ client_id, nonce: clientNonce })`. Validate
    that `payload.nonce === clientNonce` before trusting claims in memory.

*   See full implementation in
    [references/in_memory_spa_nonce.md](references/in_memory_spa_nonce.md).

### Pattern D: Browser-Based OAuth Client — WebCrypto Encrypted IndexedDB (IETF § 6.3) — Fallback for Offline PWAs

*   **Scope**: Use ONLY for offline-first Progressive Web Apps (PWAs) where user
    authentication proof must survive tab refreshes when disconnected from the
    network.

*   **Storage Invariant**: **NEVER store raw plaintext ID tokens in
    `localStorage`**. Encrypt the ID token payload using WebCrypto `AES-GCM`
    with a non-extractable session key (`extractable: false`) before writing
    ciphertext and IV to `IndexedDB`.

*   See full implementation in
    [references/offline_pwa_encryption.md](references/offline_pwa_encryption.md).

--------------------------------------------------------------------------------

## 2. Mandatory Security Directives & Browser Policies

To avoid multi-turn repair loops and browser security exceptions, provide all
required CSP, COOP, and user activation directives in the initial deliverable:

### A. Content Security Policy (CSP) Directives

```http
Content-Security-Policy:
  script-src 'self' https://accounts.google.com/gsi/client;
  frame-src https://accounts.google.com/gsi/;
  connect-src https://accounts.google.com/gsi/;
```

If using strict nonce-based CSP, attach the nonce to the GIS script tag:
`<script src="https://accounts.google.com/gsi/client" async defer
nonce="{{NONCE}}"></script>`.

### B. Cross-Origin Opener Policy (COOP)

To allow GIS popup dialogs to communicate credentials back to the parent window
via `postMessage`:

```http
Cross-Origin-Opener-Policy: same-origin-allow-popups
```

*(Serving `same-origin` without `allow-popups` breaks GIS popups and results in
silent failures).*

### C. Automatic Selection, FedCM, & Sign-Out Lifecycle (`disableAutoSelect`)

When enabling automatic zero-click return sign-in with Google One Tap (FedCM is
enabled by default in GIS):

*   Set `auto_select: true` in `google.accounts.id.initialize({...})` (do not
    pass the deprecated `use_fedcm_for_prompt` parameter).

*   **Deprecated Library Warning**: NEVER mix deprecated `gapi.auth2`
    (`gapi.auth2.init`, `gapi.auth2.getAuthInstance().signOut()`) with Google
    Identity Services (GIS). `gapi.auth2` is completely retired; use GIS methods
    exclusively.

*   **Sign-Out Protocol**: When the user explicitly logs out of your
    application, you **MUST** call `google.accounts.id.disableAutoSelect()`:

    ```javascript
    function handleUserLogout() {
      // 1. Disable automatic One Tap / FedCM re-authentication
      google.accounts.id.disableAutoSelect();

      // 2. Clear application session state / server cookie
      fetch('/api/auth/logout', { method: 'POST' }).then(() => {
        window.location.href = '/login';
      });
    }
    ```

*   *(Failing to call `disableAutoSelect()` causes an immediate automatic
    re-login loop on the next page visit after intentional user logout).*

### D. Reliable Dynamic Script Loading & Framework Lifecycle (React, Next.js, SPAs)

When mounting Sign In With Google in Single Page Applications (React, Next.js,
Vue, Angular):

*   Modern SPAs execute component lifecycles asynchronously. Attempting to
    access `window.google.accounts.id` before `<script
    src="https://accounts.google.com/gsi/client">` has finished loading causes
    `ReferenceError: google is not defined`.

*   **NEVER use `gapi` or polling (`setInterval`)**: Use deterministic dynamic
    script loading with `onload` / `addEventListener('load')` event listeners.

*   **Dynamic Script Loader Pattern**:

    ```tsx
    import React, { useEffect, useState } from 'react';

    export function useGoogleIdentityScript() {
      const [isLoaded, setIsLoaded] = useState(false);

      useEffect(() => {
        if (window.google?.accounts?.id) {
          setIsLoaded(true);
          return;
        }

        const existingScript = document.querySelector(
          'script[src="https://accounts.google.com/gsi/client"]'
        );
        if (existingScript) {
          existingScript.addEventListener('load', () => setIsLoaded(true));
          return;
        }

        const script = document.createElement('script');
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        script.onload = () => setIsLoaded(true);
        document.head.appendChild(script);
      }, []);

      return isLoaded;
    }
    ```

*   *(Always use deterministic `onload` event listeners or framework `<Script
    strategy="afterInteractive">` rather than brittle `setInterval` polling).*

### E. Embedded Iframes & Permissions Policy (`identity-credentials-get`)

When embedding Sign In With Google or One Tap inside cross-origin `<iframe>`
elements or widget integrations, modern browser security models and FedCM
require explicit Permissions Policy delegation on the container frame:

```html
<iframe
  src="https://example.com/embed"
  allow="identity-credentials-get 'src' https://accounts.google.com">
</iframe>
```

*(Omitting `allow="identity-credentials-get"` blocks FedCM / One Tap
initialization inside embedded or cross-origin contexts).* See full integration
guide in [references/intermediate_iframe.md](references/intermediate_iframe.md).

--------------------------------------------------------------------------------

## 3. Implementation Contracts & Anti-Pattern Bans

### A. Strict Ban on Legacy GAPI (`gapi.auth2`)

*   **NEVER** import or reference `gapi.auth2`, `gapi.auth2.init`,
    `gapi.auth2.getAuthInstance()`, or `gapi.signin2`. Always warn that
    `gapi.auth2` is deprecated and decommissioned.

*   GIS (`google.accounts.id.*` and `google.accounts.oauth2.*`) is completely
    stateless. It replaces all legacy GAPI authentication libraries.

--------------------------------------------------------------------------------

## 4. Implementation Recipes (Progressive Disclosure)

Load the specific reference file matching your target architecture when
generating implementation code:

*   **Recipe 1 — Pattern A (Backend For Frontend with Python / FastAPI)
    [RECOMMENDED]**: Load
    [references/bff_fastapi_verification.md](references/bff_fastapi_verification.md)
    for custom UI button prompting, `google.oauth2.id_token.verify_oauth2_token`
    cryptographic verification, `nonce` replay checks, Google Workspace `hd`
    domain enforcement, and `HttpOnly; Secure; SameSite=Lax` session cookie
    issuance.

*   **Recipe 2 — Pattern B (Token-Mediating Backend with `login_uri` Form POST
    Redirect) [RECOMMENDED]**: Load
    [references/tmb_login_uri_redirect.md](references/tmb_login_uri_redirect.md)
    for `data-login_uri` / `ux_mode: 'redirect'` frontend setup and FastAPI
    double-submit `g_csrf_token` cookie vs. form-body validation.

*   **Recipe 3 — Pattern C (Browser-Based Ephemeral In-Memory SPA with Native
    GIS Nonce) [Fallback]**: Load
    [references/in_memory_spa_nonce.md](references/in_memory_spa_nonce.md) for
    WebCrypto `nonce` generation (`google.accounts.id.initialize({ client_id,
    nonce: clientNonce })`), UTF-8 safe Base64URL JWT decoding, and private
    closure token management.

*   **Recipe 4 — Pattern D (Browser-Based WebCrypto Encrypted IndexedDB for
    Offline PWAs) [Fallback]**: Load
    [references/offline_pwa_encryption.md](references/offline_pwa_encryption.md)
    for non-extractable (`extractable: false`) `AES-GCM` `CryptoKey` generation
    and encrypted `IndexedDB` storage.

*   **Recipe 5 — Embedded Cross-Origin Contexts (`gsi/intermediate`)**: Load
    [references/intermediate_iframe.md](references/intermediate_iframe.md) for
    `<div id="g_id_intermediate_iframe">`, `allow="identity-credentials-get"`,
    and strict `window.postMessage` origin verification.

--------------------------------------------------------------------------------

## 5. Sign-Out & Account Revocation Across All Patterns

```javascript
export function handleSignOut(userEmail) {
  // 1. Disable client-side One Tap auto-selection
  google.accounts.id.disableAutoSelect();

  // 2. Revoke OAuth grant if user disconnected account
  if (userEmail) {
    google.accounts.id.revoke(userEmail, () => {
      console.log('User grant revoked');
    });
  }

  // 3. Clear storage / session
  AuthManager.clear(); // Pattern C
  fetch('/api/auth/logout', { method: 'POST' }); // Pattern A
}
```

--------------------------------------------------------------------------------

## 6. References & Normative Standards

*   [RFC 7519: JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519)
    — Standard claims (`iss`, `sub`, `aud`, `exp`, `iat`, `nonce`), formatting,
    and processing rules.

*   [RFC 7515: JSON Web Signature (JWS)](https://datatracker.ietf.org/doc/html/rfc7515)
    — Cryptographic signature verification against Google's public JWK certs
    (`https://www.googleapis.com/oauth2/v3/certs`).

*   [RFC 4648 § 5: Base64url Encoding](https://datatracker.ietf.org/doc/html/rfc4648#section-5)
    — URL-safe Base64 encoding without padding used across JWT segments.

*   [IETF OAuth 2.0 Browser-Based Applications](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-browser-based-apps)
    — Normative architecture standards (§ 6.1 BFF, § 6.2 TMB, § 6.3
    Client-side).

*   [Google Identity Services Web Reference](https://developers.google.com/identity/gsi/web/reference/js-reference)
    — Official GIS API reference.

*   [Intermediate Iframe API Reference](https://developers.google.com/identity/gsi/web/amp/nonamp-reference)
    — Cross-origin iframe embedding guide.

*   [Verify ID Tokens Server-Side](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
    — Server-side token verification protocols.

*   [W3C Federated Credential Management API (FedCM)](https://www.w3.org/TR/fedcm-1/)
    — Browser identity credential mediation standard.

*   [W3C Web Cryptography API](https://www.w3.org/TR/WebCryptoAPI/) —
    Non-extractable key generation (`extractable: false`) and AES-GCM standards.
