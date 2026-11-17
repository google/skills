# Audio, Voice, Accent, and Quality Troubleshooting

Comprehensive root causes, config fixes, and synthetic examples for voice
gender swaps, accent/language drift, timbre mimicry, speech-rate anomalies,
amplitude collapse, tonal humming, and playback jitter.

## Table of Contents

- [Voice Gender Swaps](#voice-gender-swaps): Lines 20-66
- [Accent Reversion, Pitch Jumps, and Code-Mixed Switching](#accent-reversion-pitch-jumps-and-code-mixed-switching): Lines 68-117
- [Output Voice Mimics User Timbre](#output-voice-mimics-user-timbre): Lines 119-141
- [Multi-Turn Voice and Tone Drift](#multi-turn-voice-and-tone-drift): Lines 143-164
- [Fast Speech Rate and TTS Markup or IPA Leaks](#fast-speech-rate-and-tts-markup-or-ipa-leaks): Lines 166-200
- [Near-Zero Audio Amplitude Collapse](#near-zero-audio-amplitude-collapse): Lines 202-224
- [Tonal Humming Buzz (150-700 Hz) and Non-Terminating Greetings](#tonal-humming-buzz-150-700-hz-and-non-terminating-greetings): Lines 226-262
- [Choppy Playback and Audio Jitter](#choppy-playback-and-audio-jitter): Lines 264-278

--------------------------------------------------------------------------------

## Voice Gender Swaps

**Symptom:** The model speaks in the opposite gender from the configured voice
on Turn 1 or switches between male and female voices mid-conversation.

**Root Cause:** Pairing a male prebuilt voice with a female persona in
`system_instruction` (name, role/title, or pronouns), or pairing a female
prebuilt voice with a male persona, creates conflicting acoustic and text
conditioning.

### Prebuilt Voice Gender Reference

Match `prebuilt_voice_config.voice_name` to the `system_instruction` persona:

-   **Male prebuilt voices (16):** `Achird`, `Algenib`, `Algieba`, `Alnilam`,
    `Charon`, `Enceladus`, `Fenrir`, `Iapetus`, `Orus`, `Puck`, `Rasalgethi`,
    `Sadachbia`, `Sadaltager`, `Schedar`, `Umbriel`, `Zubenelgenubi`.
-   **Female prebuilt voices (14):** `Achernar`, `Aoede`, `Autonoe`,
    `Callirrhoe`, `Despina`, `Erinome`, `Gacrux`, `Kore`, `Laomedeia`, `Leda`,
    `Pulcherrima`, `Sulafat`, `Vindemiatrix`, `Zephyr`.

### Fix

Align either the configured voice or the persona name, title, and pronouns so
both share the same gender.

```python
# Bad: female preset voice paired with male persona
bad_config = {
    "voice_name": "Kore",  # Female
    "system_instruction": "You are Arjun, a travel booking specialist.",
}

# Good: male preset voice aligned with male persona
good_config = types.LiveConnectConfig(
    response_modalities=[types.Modality.AUDIO],
    speech_config=types.SpeechConfig(
        language_code="en-IN",
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
        ),
    ),
    system_instruction="You are Arjun, a travel booking specialist.",
)
```

--------------------------------------------------------------------------------

## Accent Reversion, Pitch Jumps, and Code-Mixed Switching

**Symptom:**

-   The assistant opens with an `en-US` accent or reverts to `en-US` after a
    non-English turn or barge-in, even though `system_instruction` specifies a
    regional accent such as Indian English (`en-IN`).
-   Pitch jumps sharply after switching languages mid-call.
-   Short code-mixed utterances (for example, English mixed with Tamil or Hindi)
    fail to trigger a language switch.

**Root Cause:**

1.  **Omitted `speech_config.language_code`:** While `language_code` is optional
    for dynamic multilingual auto-detection, omitting it defaults the initial
    voice reference to `en-US`. That acoustic reference competes with text
    accent rules in `system_instruction`, causing pitch overcompensation and
    snap-back to `en-US` on later turns.
2.  **Single-script verbatim prompt inertia:** Long `system_instruction` flows
    written verbatim in one non-Latin script (for example, multi-paragraph
    Devanagari templates) bias the model against switching when a user speaks a
    short, fast code-mixed phrase in another regional language.

### Fix

1.  Set `speech_config.language_code` explicitly to a supported BCP-47 locale
    from the Live API language table (such as `"en-IN"` for Indian English; see
    [Configure Language and Voice](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/configure-language-voice.md.txt)).
2.  Keep `system_instruction` concise, written in neutral goal-oriented English
    rather than multi-paragraph single-script scripts, and add explicit
    code-switching triggers.

```python
config = types.LiveConnectConfig(
    response_modalities=[types.Modality.AUDIO],
    speech_config=types.SpeechConfig(
        language_code="en-IN",  # Supported locale prevents en-US fallback
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
        ),
    ),
    system_instruction=(
        "You are Priya, a Bengaluru hotel concierge. Speak in natural Indian "
        "English. If the guest switches to Hindi or Tamil, reply in that "
        "language seamlessly."
    ),
)
```

--------------------------------------------------------------------------------

## Output Voice Mimics User Timbre

**Symptom:** The model momentarily adopts the user's voice timbre and speaks in
first person as if continuing the user's sentence, then recovers on the next
turn.

**Root Cause:** In native audio-to-audio models, user input audio remains in the
active context window alongside the system voice reference. When role boundaries
blur (for example, after a trailing user pause or ambiguous context), decoder
attention can lock onto the user's recent audio tokens instead of the system
voice reference. Text prompts attempting to describe vocal timbre do not prevent
this and can worsen role confusion.

### Fix

1.  Upgrade to `gemini-3.8-live` if running an older preview model.
2.  State assistant-vs-user role boundaries crisply in `system_instruction`, and
    remove text instructions that attempt to dictate acoustic timbre or pitch.
3.  Monitor `serverContent.outputTranscription` for first-person role confusion
    and open a fresh session if role leakage occurs so the polluted turn does
    not remain in context.

--------------------------------------------------------------------------------

## Multi-Turn Voice and Tone Drift

**Symptom:** Over long sessions (many turns), a prebuilt voice drifts in pitch,
cadence, or perceived gender even though audio playback and client settings are
unchanged.

**Root Cause:** Model-side discrete audio-token conditioning degrades
gradually as turn history grows far past the initial voice reference tokens at
the start of the session. Client-side playback speed or synthesizer settings are
not the cause.

### Fix

1.  Ensure `speech_config.language_code` is set explicitly and remove any
    text-based timbre/voice-acting instructions from `system_instruction`.
2.  Configure `contextWindowCompression` with a sliding window (for example,
    `trigger_tokens=24000`, `target_tokens=12000`) to prevent unbounded history
    growth.
3.  Rotate or reconnect long sessions periodically at natural conversation
    boundaries (with a concise text summary if continuity is required).

--------------------------------------------------------------------------------

## Fast Speech Rate and TTS Markup or IPA Leaks

**Symptom:**

-   Spoken turns on `gemini-live-2.5-flash-native-audio` race past 240-300 WPM
    on long single-breath disclosures regardless of prompt instructions like
    *"speak slowly"*.
-   On `gemini-3.8-live`, `output_transcription` leaks raw IPA slashes
    (`/ˌmɛdɪˈkeɪʃən/`) or the model opens with off-script broadcast-style prose.

**Root Cause:**

1.  `gemini-live-2.5-flash-native-audio` does not expose a `speaking_rate`
    parameter; combining fast-cadence voices (such as `Callirrhoe`) with
    `setup.generationConfig.enableAffectiveDialog = true` and dense 50-word
    clauses accelerates speech.
2.  Copying Gemini-TTS headers (`# Audio Profile`, `# Director's Notes`) or raw
    IPA `/.../` pronunciation notation into a Live API `system_instruction`
    causes literal IPA leakage into transcripts and destabilizes conversational
    prosody.

### Fix

1.  Upgrade to `gemini-3.8-live`, which speaks naturally at a steadier
    conversational pace (~180-205 WPM; affective dialog is built-in by default,
    so omit `enableAffectiveDialog` on `gemini-3.8-live`).
2.  If remaining on `gemini-live-2.5-flash-native-audio`, break long disclosures
    into 1-2 short sentences per turn, disable
    `setup.generationConfig.enableAffectiveDialog`, and test steadier voices
    such as `Aoede` or `Puck`.
3.  Remove `# Audio Profile` / `# Director's Notes` headers and replace IPA
    slashes with plain phonetic respellings (for example, write
    `"ah-SET-uh-MIN-oh-fen"` instead of IPA notation).

--------------------------------------------------------------------------------

## Near-Zero Audio Amplitude Collapse

**Symptom:** Full-length responses arrive with intact `output_transcription` and
normal turn duration, but the 24 kHz PCM waveform is nearly silent (`~ -34` to
`-44 dBFS`, with peak amplitudes under `3%` of normal full-scale speech).

**Root Cause:** Attaching massive `tools` declarations (`>40,000` tokens or
`100+` functions) or embedding pure-text rolling dialogue history blocks inside
`system_instruction` pushes the voice reference tokens tens of thousands of
tokens away from generation. Attention to the voice reference collapses,
producing near-zero-energy audio tokens while text generation remains intact.

### Fix

1.  Prune `tools` in `BidiGenerateContentSetup` to only the active domain or
    workflow step (keep total tool schema size well under `40,000` tokens,
    ideally `<20` functions per session).
2.  Keep `system_instruction` concise (`<2,000` tokens) and never inject
    pure-text multi-turn conversation logs inside `system_instruction`.
3.  If multi-domain routing is needed, route in application code or expose a
    compact retrieval tool instead of attaching an entire catalog of schemas.

--------------------------------------------------------------------------------

## Tonal Humming Buzz (150-700 Hz) and Non-Terminating Greetings

**Symptom:**

-   On numeric readbacks (phone numbers, verification codes) or opening
    greetings, the model emits a sustained `150-700 Hz` harmonic hum or endless
    silence without sending `turnComplete: true`.
-   Audio output token counts spike `50x-600x` relative to text tokens.
-   Cancelling the stuck turn and sending a follow-up text nudge on the **same**
    WebSocket connection reproduces the hum >90% of the time.
-   If the client locks the user microphone until the first bot `turnComplete`,
    the call deadlocks permanently.

**Root Cause:** On `gemini-live-2.5-flash-native-audio`, setting low
`temperature` (`<= 0.3`) alongside
`setup.generationConfig.enableAffectiveDialog = true` traps the discrete audio
sampler in a low-entropy token-repetition attractor that never emits an
end-of-turn token. Because `temperature <= 0.3` is near-deterministic and the
partial humming turn stays in session history, nudging on the same connection
replays the attractor.

### Fix

1.  Keep `temperature >= 0.7` (default `1.0` is recommended; never set
    `temperature <= 0.3` on native-audio sessions).
2.  On `gemini-live-2.5-flash-native-audio`, disable
    `setup.generationConfig.enableAffectiveDialog` (`enable_affective_dialog` in
    the SDK) during triage and when reading structured digits/codes. (On
    `gemini-3.8-live`, affective dialog is built-in by default — omit the flag.)
3.  On any stalled or humming turn, **close and open a new WebSocket session**
    (or reconnect with a clean history) rather than nudging on the stalled
    connection.
4.  Never lock the user microphone indefinitely waiting for the first
    `turnComplete`; add a short client timeout (`3-5s`) and avoid overly low
    VAD barge-in sensitivity (`START_SENSITIVITY_LOW`) on greeting gates.

--------------------------------------------------------------------------------

## Choppy Playback and Audio Jitter

**Symptom:** `output_transcription` is clean and complete, but spoken playback
sounds choppy with `0.1-0.5s` dropouts between short bursts.

**Root Cause:** The server streams raw 24 kHz 16-bit PCM frames as they are
decoded, which can arrive in small or unevenly timed chunks (`2-20+` bytes at
turn boundaries or under network jitter). Playing each WebSocket frame
immediately starves the client audio device buffer.

### Fix

Add a `~200 ms` client-side jitter buffer before starting playback for each
turn, concatenating incoming `inlineData` PCM chunks (`audio/pcm;rate=24000`)
into the audio ring buffer before draining to the speaker.
