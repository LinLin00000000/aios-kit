---
name: native-audio-understanding
description: Use when a local audio file should be understood by the selected model through an explicitly supported native media protocol; do not use for ordinary Hermes voice-message STT or when the host already injected the audio into the current turn.
version: 0.1.0
author: Ekko
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [audio, multimodal, transcription, provider-routing]
---

# Native Audio Understanding

Use the bundled helper to send one local audio file to a model through a declared media-input adapter. The Skill owns an explicit **second request** after the Agent has received a file path. It does not claim to retrofit the audio into the already-running chat turn.

## When to use

Use this Skill when:

- the user supplied an audio file and asks the model to transcribe, summarize, classify, or understand it;
- the host Agent exposed only a local path instead of native audio content; and
- the active Provider/model has a documented or previously verified audio-input protocol.

Do not use it when:

- Hermes gateway voice-message STT is the intended path — use the configured `stt.provider` flow instead;
- the current model already received the audio natively in the same turn;
- the Provider protocol is unknown, the selected model does not support audio, or the user has not authorized the file to leave the machine;
- a separate local/offline transcription engine is required.

## Common path

1. Resolve the exact local audio path supplied by the host and confirm the user wants it sent to the selected Provider.
2. Determine the current runtime identity: Provider, model, API mode, and any session override. A gateway's internal upstream channel is not observable unless the gateway exposes it; never guess it from the model name.
3. Pick an adapter from `references/protocols.md`. In `auto`, only native Google Gemini endpoints are inferred. Custom/aggregator Providers require a previously verified `--protocol`.
4. Preview the redacted request plan. In Hermes, `${HERMES_SKILL_DIR}` is substituted with the installed package directory. In other agents, run the command from the Skill directory or replace it with that directory's path:

   ```bash
   python3 "${HERMES_SKILL_DIR}/scripts/native_audio.py" send \
     --audio /absolute/path/to/audio.m4a \
     --prompt "Transcribe this audio accurately." \
     --runtime hermes --model CURRENT_MODEL \
     --protocol PROTOCOL --dry-run
   ```

   For a non-Hermes host, use `python3 scripts/native_audio.py ...` from this package directory and provide `--runtime explicit`.

5. If the plan names the intended Provider/model/protocol and the data boundary is acceptable, run the same command without `--dry-run` and add `--json` for machine-readable output.
6. Return the model's actual text. State that it came from a separate explicit media request, not from same-turn host injection.

## Interface

```text
native_audio.py adapters
native_audio.py send --audio PATH --prompt TEXT [runtime/options]
```

Important options:

- `--runtime hermes|explicit` — `hermes` resolves the active Profile's configured Provider; pass `--provider`/`--model` when the chat has a session override. `explicit` uses `--base-url`, `--model`, and `--api-key-env`.
- `--protocol auto|gemini-native-inline|openai-chat-input-audio|openai-chat-data-url` — `openai-chat-data-url` is a gateway compatibility adapter, not an OpenAI standard.
- `--api-key-env NAME` — reads a credential from an environment variable; the key value is never accepted as an argument.
- `--auth auto|bearer|x-goog-api-key` — choose only when the Provider documentation requires it.
- `--max-bytes N` — local upper bound before base64 expansion; default 12 MiB.
- `--dry-run` — validates input and prints a redacted plan without sending media bytes or printing credentials.
- `--json` — prints a stable result envelope. Without it, prints only the returned text.

## Boundaries and failure handling

- Never silently switch Provider, model, protocol, or cloud/local path after an error.
- Never retry a billable request merely because the model returned empty text. Report the sanitized response shape.
- `openai-chat-input-audio` accepts only WAV or MP3 input because those format labels are portable across known implementations; it does not transcode.
- `openai-chat-data-url` can carry any validated audio MIME but works only on gateways that explicitly support media data URLs in `image_url` parts.
- For large Gemini inputs, stop and advise a native host integration or Gemini Files API workflow; this helper intentionally keeps transient inline requests only.
- The Hermes resolver is a convenience adapter around the locally installed Hermes runtime. If its internal resolver is unavailable, use explicit mode rather than parsing arbitrary config as a fallback.

## Verification

Success requires all of:

- the command exits zero;
- JSON output has `success: true` when `--json` is used;
- `provider`, `model`, and `protocol` match the intended route;
- response text is non-empty;
- no credential, raw header, media bytes, or base64 appears in stdout/stderr.

If the content matters, compare one short known recording against its expected words. An HTTP 200 alone is not proof the Provider consumed the audio.
