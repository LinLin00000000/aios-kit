from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "native_audio.py"


def write_wav(path: Path) -> None:
    # Minimal signature-valid WAV fixture; the helper validates container magic,
    # while the fake Provider validates request construction rather than audio decoding.
    path.write_bytes(
        b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt "
        + (16).to_bytes(4, "little") + b"\x01\x00\x01\x00"
        + (8000).to_bytes(4, "little") + (16000).to_bytes(4, "little")
        + b"\x02\x00\x10\x00data" + (0).to_bytes(4, "little")
    )


class CaptureHandler(BaseHTTPRequestHandler):
    request_json = None
    request_headers = None

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        type(self).request_json = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).request_headers = dict(self.headers.items())
        body = json.dumps(
            {"choices": [{"message": {"content": "known fixture transcript"}}]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


class GeminiCaptureHandler(BaseHTTPRequestHandler):
    request_json = None
    request_headers = None
    request_path = None

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        type(self).request_json = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).request_headers = dict(self.headers.items())
        type(self).request_path = self.path
        body = json.dumps(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "known Gemini transcript"}]}}
                ]
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


class EchoErrorHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        request_json = json.loads(self.rfile.read(length).decode("utf-8"))
        body = json.dumps(
            {
                "error": {
                    "message": "rejected payload",
                    "authorization": self.headers.get("Authorization"),
                    "request": request_json,
                }
            }
        ).encode("utf-8")
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


class NativeAudioTests(unittest.TestCase):
    def run_cli(self, *args: str, env: dict[str, str] | None = None):
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged,
            timeout=20,
            check=False,
        )

    def test_adapters_are_listed(self):
        result = self.run_cli("adapters")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        names = {item["name"] for item in payload["protocols"]}
        self.assertEqual(
            names,
            {
                "gemini-native-inline",
                "openai-chat-input-audio",
                "openai-chat-data-url",
            },
        )

    def test_explicit_dry_run_is_redacted_and_conservative(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            write_wav(audio)
            result = self.run_cli(
                "send",
                "--audio", str(audio),
                "--prompt", "Transcribe",
                "--runtime", "explicit",
                "--base-url", "https://example.invalid/v1",
                "--model", "example-audio-model",
                "--api-key-env", "TEST_NATIVE_AUDIO_KEY",
                "--protocol", "openai-chat-input-audio",
                "--dry-run",
                env={"TEST_NATIVE_AUDIO_KEY": "super-secret-fixture"},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("super-secret-fixture", result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["request_sent"])
        self.assertEqual(payload["protocol"], "openai-chat-input-audio")

    def test_unknown_auto_protocol_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            write_wav(audio)
            result = self.run_cli(
                "send",
                "--audio", str(audio),
                "--prompt", "Transcribe",
                "--runtime", "explicit",
                "--base-url", "https://example.invalid/v1",
                "--model", "example-audio-model",
                "--api-key-env", "TEST_NATIVE_AUDIO_KEY",
                "--dry-run",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conservative", result.stderr)

    def test_data_url_adapter_sends_audio_and_returns_json(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio = Path(tmp) / "sample.wav"
                write_wav(audio)
                result = self.run_cli(
                    "send",
                    "--audio", str(audio),
                    "--prompt", "Transcribe",
                    "--runtime", "explicit",
                    "--base-url", f"http://127.0.0.1:{server.server_port}/v1",
                    "--model", "example-audio-model",
                    "--api-key-env", "TEST_NATIVE_AUDIO_KEY",
                    "--protocol", "openai-chat-data-url",
                    "--json",
                    env={"TEST_NATIVE_AUDIO_KEY": "super-secret-fixture"},
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("super-secret-fixture", result.stdout + result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["text"], "known fixture transcript")
        request = CaptureHandler.request_json
        self.assertEqual(request["model"], "example-audio-model")
        media = request["messages"][0]["content"][1]
        self.assertEqual(media["type"], "image_url")
        self.assertTrue(media["image_url"]["url"].startswith("data:audio/wav;base64,"))
        self.assertEqual(
            CaptureHandler.request_headers.get("Authorization"),
            "Bearer super-secret-fixture",
        )

    def test_gemini_native_adapter_sends_inline_data(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), GeminiCaptureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio = Path(tmp) / "sample.wav"
                write_wav(audio)
                result = self.run_cli(
                    "send",
                    "--audio", str(audio),
                    "--prompt", "Transcribe",
                    "--runtime", "explicit",
                    "--base-url", f"http://127.0.0.1:{server.server_port}/v1beta",
                    "--model", "gemini-3.6-flash",
                    "--api-key-env", "TEST_NATIVE_AUDIO_KEY",
                    "--protocol", "gemini-native-inline",
                    "--json",
                    env={"TEST_NATIVE_AUDIO_KEY": "super-secret-fixture"},
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["text"], "known Gemini transcript")
        self.assertIn("/models/gemini-3.6-flash:generateContent", GeminiCaptureHandler.request_path)
        self.assertEqual(
            {key.lower(): value for key, value in GeminiCaptureHandler.request_headers.items()}.get("x-goog-api-key"),
            "super-secret-fixture",
        )
        media = GeminiCaptureHandler.request_json["contents"][0]["parts"][1]
        self.assertIn("inlineData", media)
        self.assertEqual(media["inlineData"]["mimeType"], "audio/wav")
        self.assertTrue(media["inlineData"]["data"])

    def test_input_audio_adapter_sends_standard_shape(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio = Path(tmp) / "sample.wav"
                write_wav(audio)
                result = self.run_cli(
                    "send",
                    "--audio", str(audio),
                    "--prompt", "Transcribe",
                    "--runtime", "explicit",
                    "--base-url", f"http://127.0.0.1:{server.server_port}/v1",
                    "--model", "example-audio-model",
                    "--api-key-env", "TEST_NATIVE_AUDIO_KEY",
                    "--protocol", "openai-chat-input-audio",
                    env={"TEST_NATIVE_AUDIO_KEY": "super-secret-fixture"},
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        media = CaptureHandler.request_json["messages"][0]["content"][1]
        self.assertEqual(media["type"], "input_audio")
        self.assertEqual(media["input_audio"]["format"], "wav")
        self.assertTrue(media["input_audio"]["data"])

    def test_provider_error_does_not_echo_credentials_or_audio_data(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), EchoErrorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio = Path(tmp) / "sample.wav"
                write_wav(audio)
                result = self.run_cli(
                    "send",
                    "--audio", str(audio),
                    "--prompt", "Transcribe",
                    "--runtime", "explicit",
                    "--base-url", f"http://127.0.0.1:{server.server_port}/v1",
                    "--model", "example-audio-model",
                    "--api-key-env", "TEST_NATIVE_AUDIO_KEY",
                    "--protocol", "openai-chat-data-url",
                    env={"TEST_NATIVE_AUDIO_KEY": "super-secret-fixture"},
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertNotEqual(result.returncode, 0)
        visible = result.stdout + result.stderr
        self.assertNotIn("super-secret-fixture", visible)
        self.assertNotIn("data:audio/wav;base64,", visible)
        self.assertIn("[REDACTED]", visible)
        self.assertIn("[REDACTED_DATA_URL]", visible)

    def test_input_audio_rejects_m4a_without_transcoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.m4a"
            audio.write_bytes(b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 24)
            result = self.run_cli(
                "send",
                "--audio", str(audio),
                "--prompt", "Transcribe",
                "--runtime", "explicit",
                "--base-url", "http://127.0.0.1:9/v1",
                "--model", "example-audio-model",
                "--auth", "none",
                "--protocol", "openai-chat-input-audio",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only WAV or MP3", result.stderr)


if __name__ == "__main__":
    unittest.main()
