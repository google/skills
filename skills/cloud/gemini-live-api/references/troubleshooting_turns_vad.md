# Turns, VAD, Barge-In, and Transcription Leaks

Root causes and concrete fixes for empty turns, premature completion, missing
`turnComplete`, VAD clipping on telephony audio, backchannel cutoffs, and
unspoken code or instruction leaks in `output_transcription`.

## Table of Contents

- [Premature generationComplete and Missing turnComplete](#premature-generationcomplete-and-missing-turncomplete): Lines 23-86
- [Post-toolResponse Zero-Audio Turns in Deep Contexts](#post-toolresponse-zero-audio-turns-in-deep-contexts): Lines 88-112
- [Empty Turns from proactiveAudio and Client Stall Nudges](#empty-turns-from-proactiveaudio-and-client-stall-nudges): Lines 114-149
- [Turn-1 Transcript Drops and Prompt Template Newlines](#turn-1-transcript-drops-and-prompt-template-newlines): Lines 151-170
- [Unspoken Markdown or Code Tail-Bursts in output_transcription](#unspoken-markdown-or-code-tail-bursts-in-output_transcription): Lines 172-201
- [Pre-Tool Filler Audible Leakage Without Transcripts](#pre-tool-filler-audible-leakage-without-transcripts): Lines 203-230
- [Massive Unscoped System Instruction Dumps](#massive-unscoped-system-instruction-dumps): Lines 232-252
- [Spoken Placeholder Tokens and Raw JSON Leaks](#spoken-placeholder-tokens-and-raw-json-leaks): Lines 254-282
- [Short Backchannel Cutoffs and Double-Interruption Silence](#short-backchannel-cutoffs-and-double-interruption-silence): Lines 284-309
- [Manual VAD Tail Clipping and 8 kHz Telephony Distortion](#manual-vad-tail-clipping-and-8-khz-telephony-distortion): Lines 311-336
- [Barge-In Playback Overlap and Background Noise Triggers](#barge-in-playback-overlap-and-background-noise-triggers): Lines 338-361

--------------------------------------------------------------------------------

## Premature generationComplete and Missing turnComplete

**Symptom:**

-   In multi-turn sequential readback or voice sessions, sending the next
    `clientContent` turn right after `generationComplete: true` triggers
    `interrupted: true` and cuts off playback.
-   After 3 or more turns (`ordinal >= 3`), turns occasionally stop after
    `~0.75s` of audio (or emit zero-audio / near-empty PCM turns) while
    `output_transcription` emits the full passage or a short fragment.
-   Occasionally `turnComplete: true` never arrives after a zero-audio turn,
    causing client timeouts.

**Root Cause:**

1.  **`generationComplete` vs. `turnComplete`:** `generationComplete` fires as
    soon as the server finishes synthesizing audio (faster than real time),
    while `turnComplete` waits for simulated real-time playback pacing. Sending
    the next `clientContent` turn before `turnComplete` is interpreted as a
    user barge-in.
2.  **Multi-turn history desynchronization (`ordinal >= 3`) + `<verbatim>`
    tags:** Accumulating past audio/text turns combined with `<verbatim>` XML
    tags causes the model to emit the entire text at once and predict
    end-of-turn after one audio block, or stall playback completion on a silent
    turn.

### Fix

1.  Wait for `serverContent.turnComplete == true` before sending the next
    sequential `clientContent` turn.
2.  Remove `<verbatim>` XML tags from `system_instruction` and user turns.
3.  For **stateless** turn-by-turn TTS/readback workloads reusing a warm
    WebSocket connection, configure `contextWindowCompression` with a sliding
    window (`triggerTokens >= 5000`) so completed turns do not accumulate
    unboundedly:

```json
{
  "setup": {
    "model": "projects/my-project-id/locations/us-central1/publishers/google/models/gemini-3.8-live",
    "generationConfig": {
      "responseModalities": ["AUDIO"],
      "speechConfig": {
        "languageCode": "en-US",
        "voiceConfig": {
          "prebuiltVoiceConfig": { "voiceName": "Aoede" }
        }
      }
    },
    "contextWindowCompression": {
      "triggerTokens": 10000,
      "slidingWindow": { "targetTokens": 1000 }
    },
    "outputAudioTranscription": {}
  }
}
```

4.  **Client defense-in-depth:** If `generationComplete` arrives and useful
    non-zero PCM audio bytes remain `0` for `>= 500 ms` (or `< 1.5s` of audio
    when expecting a multi-sentence readback), close/rotate the session and
    retry once rather than waiting indefinitely for `turnComplete`.

--------------------------------------------------------------------------------

## Post-toolResponse Zero-Audio Turns in Deep Contexts

**Symptom:** After a `toolResponse` in turn 5+ (`>14,000` context tokens), the
server emits `output_transcription` and `turnComplete: true` in `< 0.5s` with
`0` audio chunks (`AUDIO` tokens `0`, `TEXT` tokens `> 0`).

**Root Cause:** In long, text-heavy contexts containing XML state machines
(`<taskflow>`), large JSON payloads, or inline pronunciation guides inside
`system_instruction` or `toolResponse`, the voice reference tokens at the start
of the session are too far from the generation cursor. After `toolResponse`,
interleaved text-before-audio generation can enter a pure-text trajectory and
terminate without generating audio tokens.

### Fix

1.  Replace XML/JSON state machines in `system_instruction` with concise,
    natural-language prose (`< 2,000` tokens).
2.  Return only the minimal structured JSON needed from `toolResponse` — strip
    multi-paragraph formatting instructions or pronunciation dictionaries from
    tool outputs.
3.  Enable `contextWindowCompression` so prompt growth stays bounded across
    multi-turn tool loops (for example, `trigger_tokens=12000`,
    `target_tokens=6000`).

--------------------------------------------------------------------------------

## Empty Turns from proactiveAudio and Client Stall Nudges

**Symptom:** Frequent empty model turns (`output_audio=0`,
`output_transcription` empty or minimal), consecutive empty turns ("wedges"),
and `12-30s` of dead air.

**Root Cause:**

1.  **Proactive audio suppression:** On `gemini-live-2.5-flash-native-audio`
    when `setup.proactivity.proactiveAudio = true` (and by default on
    `gemini-3.8-live`), the model intentionally withholds audio output (`0`
    audio chunks) when it judges an utterance incomplete or background speech
    not directed at the assistant.
2.  **Client stall-watchdog self-interruption:** Client timers that fire
    `clientContent(turnComplete=True)` after `~3s` of silence immediately abort
    in-flight server generation or tool-call decoding and return `interrupted:
    true` with `0` audio.
3.  **Missed `interrupted` frames:** Clients often inspect `interrupted` only on
    the `turnComplete` message, missing the preceding `ServerMessage` where
    `serverContent.interrupted == true` actually arrived.

### Fix

1.  On `gemini-live-2.5-flash-native-audio`, set
    `setup.proactivity.proactiveAudio = false` (`proactivity={"proactive_audio":
    False}` in the SDK, or omit `proactivity`) during triage to verify whether
    intentional response suppression is causing silent turns. (On
    `gemini-3.8-live`, proactive audio is built-in by default — omit
    `setup.proactivity`.)
2.  Remove aggressive `3s` client `clientContent(turnComplete=True)` stall
    nudges (if needed as a last-resort timeout, wait `>= 10-15s` and ensure no
    tool call is in flight).
3.  Track `serverContent.interrupted` across **every** `ServerMessage` in the
    turn stream, not only on the frame carrying `turnComplete: true`.

--------------------------------------------------------------------------------

## Turn-1 Transcript Drops and Prompt Template Newlines

**Symptom:** Kicking off Turn 1 with `realtimeInput.text` while user microphone
PCM is muted intermittently drops Turn-1 `output_transcription` (`""`) and leaks
silence placeholders on call teardown.

**Root Cause:** Sending `realtimeInput.text` with zero voice activity under
`TURN_INCLUDES_ALL_INPUT` can desynchronize Turn-1 transcript emission. In
addition, concatenating interpolated prompt template sections onto a single
run-on line without `\n` separators makes multi-section instructions ambiguous.

### Fix

1.  Set `realtimeInputConfig.turnCoverage = "TURN_INCLUDES_ONLY_ACTIVITY"`,
    trigger scripted Turn-1 greetings with `clientContent(turnComplete=True)`,
    and close the WebSocket cleanly immediately after hangup tools complete.
2.  As general template hygiene, ensure interpolated sections and blocks in
    `system_instruction` are separated with explicit `\n` newlines.

--------------------------------------------------------------------------------

## Unspoken Markdown or Code Tail-Bursts in output_transcription

**Symptom:** The model speaks a normal voice answer, and right before
`generationComplete` an unrequested burst of Markdown (`##`, bullet lists) or
fenced Python/C++ code appears in `output_transcription` after spoken audio has
ceased.

**Root Cause:** Post-speech text tokens emitted after the final audio chunk can
flush as a trailing `output_transcription` update at `generationComplete`. While
within-session Live API history is managed server-side, rendering or persisting
those trailing code blocks in client UI bubbles or cross-session text replay
stores pollutes user transcripts and subsequent resumed sessions. This is
amplified by omitting `speech_config.language_code` and including Markdown
headings or code snippets in `system_instruction`.

### Fix

1.  Set `speech_config.language_code` explicitly to a supported session locale.
2.  Strip Markdown headers (`#`, `##`) and code fences from
    `system_instruction`, and add a plain-spoken instruction: *"Respond only in
    plain spoken prose. Never output Markdown formatting, bullet lists, or code
    blocks."*
3.  For UI rendering and client-persisted cross-session transcript stores, strip
    trailing fenced code blocks (` ```...``` `) or Markdown headers flushed at
    `generationComplete` after audio chunks have stopped (do not filter per
    WebSocket frame with `turn_audio_bytes > 0`, as `outputTranscription` and
    audio `inlineData` arrive on separate frames and prior speech in the same
    turn already sets cumulative `turn_audio_bytes > 0`).

--------------------------------------------------------------------------------

## Pre-Tool Filler Audible Leakage Without Transcripts

**Symptom:** Right before calling a tool, the voice assistant audibly recites
internal instructions, FAQ text, or tool-wrapper rules for `10-35s`, yet
**none** of the leaked words appear in `output_transcription` (only the opening
phrase like *"One moment while I check that"* is transcribed).

**Root Cause:** In native audio-to-audio sessions under heavy text context
(`>50,000-70,000` tokens from multi-domain fallbacks and imperative `"speak..."`
instructions inside `toolResponse`), speaking a pre-tool filler opens an audio
stream before emitting a `toolCall` message. Under heavy text dilution, the
audio decoder can drift and read nearby prompt/tool text aloud without emitting
interleaved text tokens—leaving `output_transcription` blind to the leak.

### Fix

1.  **Call tools silently:** Remove pre-tool spoken filler directives from
    `system_instruction` in deep-context agents and play any subtle waiting
    tone on the client UI instead.
2.  **Return pure data from `toolResponse`:** Strip `"say exactly..."` or
    imperative `"speak..."` wrapper prose from function responses.
3.  **Bound context size:** Fix domain-router fallbacks so only the active
    domain loads, and lower `contextWindowCompression` (for example,
    `trigger_tokens=32000`, `target_tokens=20000`).
4.  **Client circuit breaker:** Immediately mute/stop pre-tool audio playback
    the moment a `toolCall` message arrives.

--------------------------------------------------------------------------------

## Massive Unscoped System Instruction Dumps

**Symptom:** `output_transcription` suddenly streams thousands of characters of
the `system_instruction` verbatim (sometimes ending with `"""` code delimiters)
between two normal spoken sentences.

**Root Cause:** When a domain classifier falls back to loading all domains
(`>50,000` tokens), combining repeated `"Output ONLY ... VERBATIM"` rules,
triple-quote delimiters, and rules blocking tool calls on unsupported inputs
causes the model to scan the prompt and copy trailing SI text verbatim.

### Fix

1.  Never load all domain prompts on classifier fallback; route to a
    lightweight clarification prompt (`< 2,000` tokens).
2.  Remove `"Output VERBATIM"` rules and `"""` triple-quote delimiters from
    `system_instruction`.
3.  Validate unsupported inputs inside a typed tool response instead of
    forbidding tool calls in the prompt.

--------------------------------------------------------------------------------

## Spoken Placeholder Tokens and Raw JSON Leaks

**Symptom:** The model speaks `"No speech. Pause."` aloud, emits `<no speech>`,
`{pause}`, or `…` in `output_transcription`, or leaks raw JSON routing
objects (`{"state": "..."}`).

**Root Cause:**

1.  **Duplicate post-tool turn:** Returning a `FunctionResponse` on a
    `NON_BLOCKING` or side-effect tool (such as `hangup_call` or `log_metric`)
    without `scheduling="SILENT"` triggers a follow-up turn after the assistant
    already said goodbye; having nothing to say, it emits `<no speech>` or
    `{pause}`.
2.  **Bot self-echo:** Without acoustic echo cancellation (AEC), the model hears
    its own TTS output and tries to stay silent.
3.  **Forbidden state-transition loop:** State-machine prompts that forbid
    calling a routing tool for the current state cause the model to emit raw
    JSON or `…` when a caller repeats unintelligible fragments.

### Fix

1.  Set `scheduling="SILENT"` on transactional/side-effect `FunctionResponse`s,
    and set `behavior="BLOCKING"` on tools whose result the model must wait for
    before speaking.
2.  Enable client AEC and mute/gate echoed bot output.
3.  Bound unclear-input loops (for example, escalate after 2 unclear turns) and
    explicitly forbid emitting control placeholders or JSON in spoken turns.

--------------------------------------------------------------------------------

## Short Backchannel Cutoffs and Double-Interruption Silence

**Symptom:** Short user affirmations (`"Mm-hmm"`, `"Uh-huh"`, `"Got it"`) while
the assistant is speaking immediately trigger `serverContent.interrupted: true`,
cutting off the assistant and dropping the rest of its explanation. Brief pauses
mid-utterance (`"Wait, [pause]..."`) cause two rapid interrupts and a silent
(`0.0s`) stalled turn.

**Root Cause:** Server-side barge-in interrupts the active turn immediately on
acoustic start-of-speech before semantic intent or sentence completion can be
evaluated. Tuning `startOfSpeechSensitivity` to `START_SENSITIVITY_LOW` reduces
sensitivity slightly, but cannot reliably distinguish brief backchannels from
real questions.

### Fix

Implement a client-side voice activity gate for backchannels:

1.  Buffer short (`< 500 ms`) non-lexical affirmations locally without
    forwarding them as interrupting turns (or suppress client playback cutoff
    until sustained speech / lexical intent is detected).
2.  When strict uninterrupted storytelling or multi-step readouts are required,
    set `realtimeInputConfig.activityHandling = "NO_INTERRUPTION"` or manage
    barge-in boundaries manually on the client.

--------------------------------------------------------------------------------

## Manual VAD Tail Clipping and 8 kHz Telephony Distortion

**Symptom:** Critical numbers (postal codes, confirmation codes, account IDs)
are truncated in `input_transcription` (for example, `"98058"` transcribed as
`"98050"`), causing wrong tool arguments even though the full call recording
sounds clear.

**Root Cause:** Two factors compound on telephony streams:

1.  **Client manual VAD tail clipping:** When `automaticActivityDetection` is
    `disabled: true`, sending `activityEnd` immediately when local RMS drops
    (or bouncing on `< 400 ms` pauses) cuts off the last `200-300 ms` of
    final plosives (`/t/`, `/d/`).
2.  **8 kHz narrowband PSTN attenuation:** Telephone audio rolls off above
    `3.4-4 kHz`, making final consonants fragile if clipped even slightly.

### Fix

1.  Add `400-500 ms` of post-speech hangover padding before sending
    `activityEnd`, and debounce `< 400 ms` `activityStart`/`activityEnd`
    spikes (or use server-side VAD with `prefix_padding_ms=300`,
    `silence_duration_ms=600`, `end_of_speech_sensitivity="END_SENSITIVITY_LOW"`).
2.  For critical telephony fields (dates, confirmation codes, amounts), require
    an explicit spoken read-back confirmation before committing the transaction.

--------------------------------------------------------------------------------

## Barge-In Playback Overlap and Background Noise Triggers

**Symptom:**

-   After barge-in, the new assistant turn plays on top of the previous turn's
    buffered audio.
-   Background music or ambient noise causes the assistant to cut off
    mid-sentence or respond to noise.

**Root Cause:** Faster-than-realtime server generation can finish a turn before
the user interrupts; because the server turn already ended, no
`interrupted: true` event is emitted, so a client that only flushes on
`interrupted: true` plays old buffered audio underneath the new turn. Meanwhile,
missing AEC or discontinuous audio chunks trigger false server VAD events.

### Fix

1.  **Flush on new turn:** Clear the client audio playback queue both when
    `serverContent.interrupted == true` **and** whenever the first audio chunk
    of a new model turn arrives while prior audio is still playing.
2.  Enable hardware/software **AEC**, gate pure background music client-side,
    stream continuous 16 kHz 16-bit mono PCM frames (`audio/pcm;rate=16000`),
    and tune `automaticActivityDetection` (`start_of_speech_sensitivity`,
    `silence_duration_ms`).
