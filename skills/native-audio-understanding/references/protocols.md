# Audio input protocol adapters

Load this reference when choosing or debugging `--protocol`. Provider/model capability must come from current documentation, a trusted runtime descriptor, or a focused positive test. Model-name guessing is not a capability check.

## Adapter matrix

| Protocol | Endpoint | Content shape | Auth default | Safe use |
|---|---|---|---|---|
| `gemini-native-inline` | `models/{model}:generateContent` | Gemini `inlineData {mimeType,data}` | `x-goog-api-key` | Google AI Studio native base URLs, or another endpoint explicitly documenting the same schema. |
| `openai-chat-input-audio` | `chat/completions` | `input_audio {data,format}` | bearer | Only endpoints that document OpenAI-style `input_audio`; helper limits labels to WAV/MP3. |
| `openai-chat-data-url` | `chat/completions` | `image_url.url = data:audio/...` | bearer | Compatibility-only for gateways explicitly verified to reinterpret media data URLs. Not an OpenAI standard. |

## Gemini native inline

The helper sends:

```json
{
  "contents": [{
    "role": "user",
    "parts": [
      {"text": "..."},
      {"inlineData": {"mimeType": "audio/mp4", "data": "<base64>"}}
    ]
  }]
}
```

Google documents inline audio for small, transient requests and recommends the Files API when the total request exceeds the current inline limit or the file will be reused. This Skill deliberately omits Files API lifecycle management to keep the common path small and stateless.

Official reference: https://ai.google.dev/gemini-api/docs/generate-content/audio

## OpenAI-style input_audio

The helper sends:

```json
{
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "..."},
      {"type": "input_audio", "input_audio": {"data": "<base64>", "format": "wav"}}
    ]
  }]
}
```

API implementations differ on accepted formats and supported model families. The helper does not transcode; it accepts WAV/MP3 only for this adapter. If a Provider requires another schema or a dedicated transcription endpoint, do not force it through this adapter.

## Gateway data-URL compatibility

The helper sends an audio data URL in an `image_url` content part. Some aggregators preserve arbitrary data URLs and convert them to an upstream native media part. Other OpenAI-compatible servers validate the content type strictly or silently drop it.

A successful HTTP status is insufficient. Verify with a recording whose words are known and require the model to quote them. Keep this adapter explicit; `auto` never selects it.

## `auto` resolution

`auto` selects `gemini-native-inline` only when the base URL is the native Google Generative Language endpoint and does not end in `/openai`. It refuses all other endpoints. This conservative rule prevents custom gateways from being classified by model-name substring.

## Authentication

- `bearer`: `Authorization: Bearer <key>`
- `x-goog-api-key`: `x-goog-api-key: <key>`
- `auto`: Gemini native uses `x-goog-api-key`; other adapters use bearer.

The helper reads key values from the environment variable selected by `--api-key-env` or from the installed Hermes runtime resolver. It never prints the value.
