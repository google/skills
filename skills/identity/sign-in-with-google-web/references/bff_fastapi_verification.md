# Pattern A: Backend For Frontend (BFF) Verification Recipe (Python / FastAPI)

This reference provides the complete implementation recipe for **Pattern A
(Backend For Frontend — IETF `draft-ietf-oauth-browser-based-apps` § 6.1)**, the
recommended gold-standard architecture for full-stack SPAs and web applications.

--------------------------------------------------------------------------------

## 1. Custom UI Button & Programmatic Prompting Pattern (Frontend)

When triggering Google Identity Services (GIS) from a custom application button
(rather than `renderButton`):

```typescript
export function setupCustomGoogleSignIn(
  buttonEl: HTMLElement,
  clientId: string,
  onCredentialReceived: (credential: string) => void
) {
  // 1. Initialize GIS with callback and popup configuration
  google.accounts.id.initialize({
    client_id: clientId,
    callback: (res: { credential: string }) => {
      if (res.credential) {
        onCredentialReceived(res.credential);
      }
    },
    ux_mode: 'popup',
    auto_select: false,
  });

  // 2. Programmatically trigger One Tap / popup prompt on user click
  buttonEl.addEventListener('click', () => {
    google.accounts.id.prompt();
  });
}
```

--------------------------------------------------------------------------------

## 2. FastAPI BFF Token Verification & Session Issuance (Backend)

```python
from fastapi import Cookie, FastAPI, HTTPException, Response
from google.auth.transport import requests
from google.oauth2 import id_token
from pydantic import BaseModel

app = FastAPI()
GOOGLE_CLIENT_ID = "YOUR_CLIENT_ID.apps.googleusercontent.com"
ALLOWED_WORKSPACE_DOMAIN = "mycompany.com"  # Optional hd restriction


class AuthRequest(BaseModel):
  credential: str


@app.post("/api/auth/google")
async def authenticate_google(
    auth_req: AuthRequest,
    response: Response,
    auth_nonce_cookie: str | None = Cookie(None, alias="auth_nonce"),
):
  try:
    # 1. Cryptographically verify signature and audience against Google Public JWKs
    id_info = id_token.verify_oauth2_token(
        auth_req.credential, requests.Request(), GOOGLE_CLIENT_ID
    )

    # 2. Verify nonce strictly against server session/HTTP-only cookie state (Replay Protection)
    if auth_nonce_cookie and id_info.get("nonce") != auth_nonce_cookie:
      raise HTTPException(
          status_code=401, detail="Nonce mismatch / token replay detected"
      )

    # 3. Verify Google Workspace Hosted Domain claim if enforcing domain lock
    if (
        ALLOWED_WORKSPACE_DOMAIN
        and id_info.get("hd") != ALLOWED_WORKSPACE_DOMAIN
    ):
      raise HTTPException(
          status_code=403, detail="Unauthorized workspace domain"
      )

    user_sub = id_info["sub"]
    user_email = id_info["email"]

    # 4. Create session & set secure HttpOnly cookie
    response.set_cookie(
        key="session_id",
        value=create_server_session(user_sub, user_email),
        httponly=True,
        secure=True,
        samesite="lax",
    )
    # Clear temporary nonce cookie after successful verification
    response.delete_cookie("auth_nonce")
    return {"status": "authenticated", "email": user_email}

  except ValueError as e:
    raise HTTPException(status_code=401, detail="Invalid token") from e
```
