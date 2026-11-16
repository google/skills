# Region Availability Check for Publisher Endpoints

> [!NOTE] **Skip this section** if the user is deploying an open-weights model
> from Model Garden (Gemma, Llama, DeepSeek, Qwen, or any user-supplied weights)
> or a Gemini-tuned model — i.e. anything served via `gcloud ai model-garden
> models deploy` (§3) onto a dedicated endpoint. These have no per-region
> publisher endpoint restriction.
> The real failure modes for an unusual region are (a) the requested
> accelerator/machine type isn't offered in that region, or (b) the project has
> no quota — both surface as a clean error at deploy time before any resources
> are provisioned (§3's cost-confirm gate catches them). Go straight to §3.
>
> **Apply this section** only if the user is asking to serve a first-party
> managed Gemini model (`google/gemini-*`) via a publisher endpoint whose
> regional availability varies.

> [!WARNING] **Retired Legacy Models (Do NOT Probe or Recommend)**: Legacy
> Gemini 2.5 models (such as `gemini-2.5-flash`, `gemini-2.5-pro`, and
> `gemini-2.5-flash-lite`) are retired. If the user asks to deploy or check
> regional availability (including for a LoRA adapter) on a retired
> `gemini-2.5-*` base model, **STOP immediately — do NOT run any
> `:generateContent` or `gcloud` probe against the retired model and do NOT
> recommend it**. Instead, inform the user that the requested `gemini-2.5-*`
> model is retired and suggest active supported models such as
> `gemini-3.8-flash` or `gemini-3.5-flash-lite`.

Before responding to any deploy request that names a specific region for an
active first-party managed Gemini model (`google/gemini-*`), you **MUST** verify
the model is actually available in that region by making a live API call. Do not
rely on Google Search, training-corpus knowledge, or publisher documentation for
availability claims — regional availability changes frequently and grounded text
can be stale or wrong.

Probe only the exact model and region the user asked about. Do not probe other
models as a "control" — you cannot infer anything about model A's availability
from model B's status, because a different model may itself be unavailable in
the reference region for unrelated reasons.

For first-party publisher models (`google/*`), probe with a real
`:generateContent` call using a minimal valid payload. This probe is
agent-executed in the sandbox — do not ask the user to run it manually:

```bash

curl -sS -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    "https://${LOCATION_ID}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION_ID}/publishers/google/${MODEL_ID}:generateContent" \
    -d "{\"contents\":{\"role\":\"user\",\"parts\":{\"text\":\"${PROBE_TEXT:-hi}\"}}}"

```

For LoRA adapters deployed on top of a first-party Gemini base model, probe the
**base model** in the target region using the same `:generateContent` call above
with `${MODEL_ID}` set to the base (e.g. `gemini-3.8-flash`). The adapter cannot
serve in a region where its base model isn't available. This does not apply to
Gemini Tuning models, which are deployed via a different path and have no
publisher-endpoint region restriction.

Interpret the probe result and act:

-   **200** — model is available in that region. Proceed with the deploy.
-   **404** — model is not available in that region. STOP. Tell the user plainly
    that the model isn't offered in that region and list the regions where it is
    available (from `gcloud ai model-garden models list
    --filter="name~${MODEL_NAME}"` without `--region`). Do not silently switch
    regions. Do not proceed to write deploy code or SDK initialization for the
    unsupported region. Do not run additional "control" probes to double-check
    the 404 — the target-region probe is authoritative.
-   **Any other outcome** (permission denied, quota, transient failure, etc.) —
    do not conclude the model is available or unavailable. Explain the
    underlying cause in plain language (e.g. "your account doesn't have access
    to this project's Vertex AI API — enable it in the console or switch
    projects") and the concrete next action.
