---
name: dpop-adoption
metadata:
  version: "1.0.1"
  category: Identity
description: >-
  Implement and debug OAuth 2.0 DPoP (RFC 9449) refresh token sender-constraining
  for WebCrypto, Node.js ES6, and browser runtimes integrating with Google's OAuth
  platform. Use when configuring non-extractable asymmetric key pairs (P-256),
  generating DPoP Proof JWTs for authorization code exchange and token refresh, or
  handling 400 use_dpop_nonce challenge retry loops at oauth2.googleapis.com/token.
  Don't use for unconstrained OAuth 2.0 flows (where refresh tokens are not bound
  to a client key pair), or for Google Cloud IAM / service account authentication.
---

# DPoP Adoption & Identity Security Architecture

Demonstrating Proof-of-Possession (DPoP, RFC 9449) secures OAuth 2.0 refresh
tokens against interception and replay attacks by cryptographically binding them
to a private key held exclusively by the client. In Google's OAuth 2.0 platform,
DPoP binds the refresh token at the token endpoint, while access tokens issued
for Google APIs are standard Bearer tokens (`token_type: "Bearer"`).

## 1. Core Cryptographic & Architectural Invariants

When implementing DPoP helpers or upgrading HTTP clients, you MUST adhere to the
following strict security invariants:

### A. Universal WebCrypto & Runtime Compatibility

-   In modern ES6 JavaScript (`"type": "module"` for Node 18+ and browsers),
    ALWAYS access `globalThis.crypto` directly after verifying the environment
    context.
-   **NEVER** import legacy CommonJS modules via `require('node:crypto')` or
    reference browser-scoped `window.crypto`, as these cause module
    initialization crashes across hybrid runtimes.

### B. Hardware-Backed Non-Extractable Key Persistence

-   Generate an Elliptic Curve key pair on the SECP256R1 (`P-256`) curve: `{
    name: 'ECDSA', namedCurve: 'P-256' }`.
-   **CRITICAL SECURITY GUARDRAIL:** The private key MUST be configured as
    **non-extractable** (`extractable: false`). This guarantees the private key
    can never leave the platform's cryptographic boundary (Secure Enclave,
    Android KeyStore, or JS sandbox memory), thwarting XSS and dependency token
    theft attacks.
-   **Runtime Persistence Scope:** In-memory WebCrypto (`extractable: false`)
    key generation applies to browser/IndexedDB contexts and single-process
    runtime harnesses; multi-instance or persistent server-side Node.js
    deployments should bind DPoP private keys via KMS/HSM/TPM so bound refresh
    tokens survive process restarts.
-   The public key MUST remain exportable (`extractable: true`) to allow
    emitting JSON Web Keys (JWKs).

### C. Public JWK Formatting Standards

-   When exporting public keys to attach to DPoP Proof JWT headers, construct a
    clean JWK dictionary containing strictly:
    -   `"kty": "EC"`
    -   `"crv": "P-256"`
    -   `"x"`: Base64URL-encoded x-coordinate without trailing equal sign
        padding (`=`).
    -   `"y"`: Base64URL-encoded y-coordinate without trailing equal sign
        padding (`=`).
-   **NEVER** expose private key parameters (`"d"`) or superfluous metadata.

### D. IEEE P1363 vs. ASN.1 DER Signature Disambiguation

-   DPoP Proof JWTs require raw concatenated coordinate signatures ($R \parallel
    S$, exactly 64 bytes for P-256) per IEEE P1363 and RFC 7518.
-   **WebCrypto Native Rule:** In standard WebCrypto (`crypto.subtle.sign`),
    ECDSA signatures are ALREADY emitted natively in raw IEEE P1363 format
    (concatenated 32-byte `r` and `s` buffers, 64 bytes total). **DO NOT**
    attempt DER-to-Raw conversion on `crypto.subtle.sign` outputs, as parsing a
    64-byte raw buffer as ASN.1 DER causes an immediate runtime exception
    (`Invalid DER sequence`). Directly base64url-encode the raw ArrayBuffer.
-   **Legacy API Fallback:** If and only if implementing in legacy Java/Android
    (`java.security.Signature`) or Node CommonJS (`crypto.createSign`), convert
    ASN.1 DER output to raw 64-byte IEEE P1363 format before base64url encoding.

### E. SPA & Backend-for-Frontend (BFF) Architecture

-   **Secretless SPAs Limitation:** Pure client-side single-page applications
    (SPAs) without a backend cannot use DPoP directly with Google APIs due to
    `client_secret` requirements on server endpoints and browser CORS
    limitations on the `DPoP-Nonce` response header.
-   **BFF Pattern:** To secure SPAs with DPoP, route authorization and token
    refresh requests through a Backend-for-Frontend (BFF) server-side client.
    The BFF sets `access_type=offline`, binds refresh tokens server-side using
    DPoP, and maintains secure session cookies with the frontend.

## 2. Implementation Rules & Mandatory Public API

When creating new modules, your module MUST explicitly export all functions
below to integrate cleanly with CI/CD verification harnesses and automated
probers. When inspecting or refactoring existing codebases, ensure equivalent
cryptographic and RFC 9449 logic is present. Obey strict claim derivation logic
in all cases:

### A. DPoP Proof JWT Claim Derivation Rules (`createDPoPProof`)

When generating the DPoP Proof JWT in `createDPoPProof`:

**1. JOSE Header (`typ`, `alg`, `jwk`):**
```javascript
// Header
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": await exportPublicJWK(publicKey)
}
```

**2. Payload Claims:**
-   `"htm"`: Uppercase HTTP Method (`"POST"` for token requests).
-   `"htu"`: Target URI stripped of query parameters and hash fragments using
    `sanitizeHTU(htu)`. For token requests, this is
    `https://oauth2.googleapis.com/token`.
-   `"iat"`: Current integer epoch timestamp in seconds
    (`Math.floor(Date.now() / 1000)`).
-   `"jti"` (Critical Invariant):
    1.  If an explicit `jti` argument is provided to `createDPoPProof`, use that
        exact string over all others.
    2.  Otherwise, if an `authCode` argument is provided (during initial code
        exchange), set `jti = await calculateAuthCodeJti(authCode)` where
        `calculateAuthCodeJti` computes `base64url(sha256(authCode))` to ensure
        the DPoP proof is cryptographically bound to the authorization code.
    3.  Only if neither `jti` nor `authCode` is provided, generate a fresh
        cryptographic random string via `generateRandomString()` (such as
        `crypto.getRandomValues(new Uint8Array(24))` base64url encoded).
-   `"ath"` (Optional): If an `accessToken` argument is provided for RFC 9449
    resource requests, compute `base64url(sha256(accessToken))` via
    `calculateATH(accessToken)` and inject it (RFC 9449 Section 6.1).
-   `"nonce"` (Optional): If a `nonce` argument is provided, inject it directly
    into the payload.

### B. Explicit Export Signatures

```javascript
// 1. Key generation & JWK export
export async function generateDPoPKeyPair() // -> { publicKey, privateKey } (private key extractable=false)
export async function exportPublicJWK(publicKey) // -> { kty: 'EC', crv: 'P-256', x, y }

// 2. Proof generation & validation
export async function createDPoPProof({ privateKey, publicKey, htm, htu, nonce, accessToken, authCode, jti }) // -> signed JWT string
export async function verifyDPoPProof(dpopProofJwt) // -> { isValid: boolean, header, payload, error }
export function sanitizeHTU(htu) // -> URL stripped of query and hash: const u = new URL(htu); return `${u.origin}${u.pathname}`;

// 3. Cryptographic & encoding utilities
export function base64UrlEncode(buffer) // -> Uint8Array/ArrayBuffer to base64url string without '=' padding
export function base64UrlDecode(str) // -> base64url string to Uint8Array/Buffer
export function stringToBase64Url(str) // -> UTF-8 string to base64url
export function base64UrlToString(str) // -> base64url to UTF-8 string
export function generateRandomString(byteLength = 32) // -> cryptographic random base64url string
export async function calculateATH(accessToken) // -> base64url(sha256(accessToken)) per RFC 9449 Sec 6.1
export async function calculateAuthCodeJti(code) // -> base64url(sha256(code))
export async function generatePKCE() // -> { codeVerifier (>=43 chars), codeChallenge, codeChallengeMethod: 'S256' }
```

## 3. Token Endpoint & Resource Request Workflow

When integrating with Google's OAuth 2.0 platform:

1.  **Token Endpoint Requests (`oauth2.googleapis.com/token`):**
    -   Attach the DPoP Proof JWT in the `DPoP` HTTP header:
        `` `DPoP: ${proofJwt}` `` when making `POST` requests for code exchange
        (`grant_type=authorization_code`) and token refresh
        (`grant_type=refresh_token`).
2.  **Resource API Requests:**
    -   Google's token endpoint returns `"token_type": "Bearer"`. Downstream
        requests to Google APIs (e.g. Calendar, Drive, Gmail) use standard
        `` `Authorization: Bearer ${accessToken}` `` headers without DPoP
        headers.
3.  **Single-Retry Nonce Challenge Loop & Workflow Isolation:**
    -   If Google's token endpoint returns HTTP `400 Bad Request` with
        `error: "use_dpop_nonce"` and a `"DPoP-Nonce"` response header:
        -   **Workflow Isolation:** Google's authorization server enforces
            workflow isolation between authorization code exchange and token
            refresh, returning an HTTP `400 use_dpop_nonce` challenge to
            establish a fresh nonce namespace. This is standard RFC-compliant
            protocol behavior, not a server failure.
        -   Cache the fresh nonce in client state (`this.dpopNonce`).
        -   Immediately synthesize a new DPoP Proof JWT incorporating the
            updated `nonce` claim and a fresh `jti`.
        -   Replay the failed token request **exactly once**. If the retried
            request fails, terminate immediately with an error to prevent
            infinite recursion.

## 4. Concise Agent Egress Protocol

When prompted to synthesize or output code deliverables under this skill,
prioritize returning clean, directly importable code blocks without redundant
conversational preambles or repetitive filler. For conceptual or architectural
inquiries, provide standard direct answers.

## 5. References & Supporting Documentation

### Developer Documentation (Google for Developers)
-   [DPoP Adoption Guide](https://developers.google.com/identity/protocols/oauth2/resources/dpop-adoption) —
    Official Google Identity guide for implementing DPoP across authorization
    code exchange and token refresh.
-   [Using OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server#offline) —
    Offline access, refresh tokens, and server-side authorization flows.
-   [OAuth 2.0 Best Practices: Sender-Constrain Tokens](https://developers.google.com/identity/protocols/oauth2/resources/best-practices#sender-constrain-tokens) —
    Recommendations for token storage, rotation, and sender-constraining.

### Developer Knowledge MCP Server
-   Agents equipped with Model Context Protocol (`MCP`) can query real-time
    Google Developer documentation using the
    [Google Developer Knowledge MCP Server](https://developers.google.com/knowledge/mcp)
    (`npx -y @google/mcp-developer-knowledge-server`) via
    `developer_knowledge:search_documents` and
    `developer_knowledge:get_documents`.

### Standards & RFC Specifications
-   [RFC 9449: OAuth 2.0 Demonstrating Proof-of-Possession (DPoP)](https://datatracker.ietf.org/doc/html/rfc9449)
-   [RFC 7519: JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519)
-   [RFC 7636: Proof Key for Code Exchange by OAuth Public Clients (PKCE)](https://datatracker.ietf.org/doc/html/rfc7636)
