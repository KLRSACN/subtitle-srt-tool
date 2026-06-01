#!/usr/bin/env python3
"""
Video/audio to SRT subtitle converter using Google Gemini.

The module is intentionally split into reusable functions so the command line
tool, GUI, and future song-specific pipeline can share the same core.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


API_BASE = "https://generativelanguage.googleapis.com"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_LANGUAGE = "Traditional Chinese, Taiwan usage"

ProgressCallback = Callable[[str], None]


class SubtitleError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConvertOptions:
    video_path: Path
    output_path: Path
    api_key: str
    topic: str = ""
    language: str = DEFAULT_LANGUAGE
    glossary_path: Path | None = None
    mode: str = "general"
    model: str = DEFAULT_MODEL
    max_chars: int = 22


MODES: dict[str, dict[str, str]] = {
    "general": {
        "label": "一般影片",
        "focus": "Produce accurate subtitles while preserving the speaker's intent.",
    },
    "broadcast": {
        "label": "廣播講話聲音",
        "focus": "Produce clean Traditional Chinese subtitles for spoken-word audio such as broadcasts, narration, interviews, lectures, meetings, and podcasts.",
    },
    "teaching": {
        "label": "教學/主題影片",
        "focus": "Prioritize terminology, logical flow, and topic-specific wording.",
    },
    "plant": {
        "label": "植物照顧",
        "focus": "Prioritize plant names, care terms, fertilizer, propagation, pests, and horticulture wording.",
    },
    "song": {
        "label": "歌曲/歌詞",
        "focus": "Create lyric-style SRT. Preserve repeated choruses, line breaks, rhythm, English phrases, and poetic wording. Do not over-normalize lyrics.",
    },
}


def log(progress: ProgressCallback | None, message: str) -> None:
    if progress:
        progress(message)


def request_json(url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{url}?key={urllib.parse.quote(api_key)}",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SubtitleError(f"API request failed: HTTP {exc.code}\n{detail}") from exc


def start_resumable_upload(path: Path, api_key: str, mime_type: str) -> str:
    metadata = {"file": {"display_name": path.name}}
    body = json.dumps(metadata).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/upload/v1beta/files?key={urllib.parse.quote(api_key)}",
        data=body,
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(path.stat().st_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            upload_url = response.headers.get("X-Goog-Upload-URL")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SubtitleError(f"Could not start file upload: HTTP {exc.code}\n{detail}") from exc

    if not upload_url:
        raise SubtitleError("Google API did not return an upload URL.")
    return upload_url


def upload_file(path: Path, api_key: str, mime_type: str) -> dict[str, Any]:
    upload_url = start_resumable_upload(path, api_key, mime_type)
    data = path.read_bytes()
    req = urllib.request.Request(
        upload_url,
        data=data,
        headers={
            "Content-Length": str(len(data)),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
            "Content-Type": mime_type,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SubtitleError(f"Could not upload file: HTTP {exc.code}\n{detail}") from exc

    file_info = result.get("file")
    if not file_info:
        raise SubtitleError(f"Unexpected upload response: {json.dumps(result, ensure_ascii=False)}")
    return file_info


def get_file(api_key: str, file_name: str) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{API_BASE}/v1beta/{file_name}?key={urllib.parse.quote(api_key)}",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SubtitleError(f"Could not read file state: HTTP {exc.code}\n{detail}") from exc


def wait_until_active(api_key: str, file_name: str) -> dict[str, Any]:
    for _ in range(60):
        info = get_file(api_key, file_name)
        state = info.get("state")
        if state == "ACTIVE":
            return info
        if state == "FAILED":
            raise SubtitleError("Google API failed to process the uploaded file.")
        time.sleep(3)
    raise SubtitleError("Timed out while waiting for Google API to process the file.")


def load_terms(path: Path | None) -> list[str]:
    if not path:
        return []
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        if not isinstance(data, list):
            raise SubtitleError("Glossary JSON must be a list of strings.")
        return [str(item).strip() for item in data if str(item).strip()]
    return [line.strip() for line in raw.splitlines() if line.strip() and not line.startswith("#")]


def build_prompt(topic: str, language: str, terms: list[str], max_chars: int, mode: str) -> str:
    mode_info = MODES.get(mode, MODES["general"])
    term_block = "\n".join(f"- {term}" for term in terms) if terms else "- None"
    song_rules = ""
    if mode == "song":
        song_rules = """
Song-specific rules:
- Output lyric subtitles, not a prose transcript.
- Keep repeated choruses and repeated lines when they are sung.
- Preserve meaningful English phrases, names, rhymes, and emotional wording.
- Use shorter subtitle chunks when timing follows musical phrases.
- If a lyric is unclear, prefer the most plausible lyric from context instead of inventing new content.
"""

    return f"""
You are a professional subtitle editor, transcription proofreader, and Traditional Chinese language editor.

Task: Generate a standard SRT subtitle file from the uploaded media.

Output language: {language}
Mode: {mode_info["label"]}
Mode focus: {mode_info["focus"]}
Topic/context: {topic or "Not specified. Infer it from the media."}

Glossary and preferred terms:
{term_block}

Quality rules:
1. Output only valid SRT content. Do not output Markdown, notes, summaries, or explanations.
2. Keep accurate timestamps and do not drift away from the media.
3. Each subtitle should usually be 1 to 2 lines. Keep each line around {max_chars} Chinese characters when possible.
4. Use the title/context to infer the subject, then correct homophone errors, domain terminology, names, brands, and foreign loanwords.
5. Use context to choose the right meaning for Chinese polyphonic or ambiguous characters, including 行, 重, 長, 著, 樂, 便, 只, 數, 種, 藏, 薄, 降, 給.
6. Improve readability by removing obvious filler words when it does not change the meaning.
7. Preserve necessary English terms in mixed Chinese/English speech.
8. Never add facts, captions, speaker labels, or explanations that are not in the media.
9. For spoken-word subtitles, prefer breaking a subtitle at the first full stop-like punctuation mark. If no full stop is available, break at a comma-like punctuation mark. Keep each subtitle within {max_chars} Chinese characters when practical.
{song_rules}
SRT example:
1
00:00:00,000 --> 00:00:02,000
字幕文字
""".strip()


def generate_srt(api_key: str, model: str, file_uri: str, mime_type: str, prompt: str) -> str:
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                    {"text": prompt},
                ],
            }
        ],
        "generationConfig": {"temperature": 0.15, "topP": 0.8},
    }
    result = request_json(f"{API_BASE}/v1beta/models/{model}:generateContent", api_key, payload)
    candidates = result.get("candidates", [])
    if not candidates:
        raise SubtitleError(f"No subtitle candidate returned: {json.dumps(result, ensure_ascii=False)}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise SubtitleError("The API returned an empty subtitle.")
    return clean_srt(text)


def clean_srt(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:srt)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip() + "\n"


def validate_srt(text: str) -> list[str]:
    warnings: list[str] = []
    if "-->" not in text:
        warnings.append("No SRT timestamp arrow was found. Please inspect the output.")
    if not re.search(r"\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}", text):
        warnings.append("The timestamp format does not look like standard SRT.")
    return warnings


def guess_mime_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type:
        return mime_type
    if path.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac", ".aac"}:
        return "audio/mpeg"
    return "video/mp4"


def convert_video_to_srt(options: ConvertOptions, progress: ProgressCallback | None = None) -> list[str]:
    if not options.video_path.exists():
        raise SubtitleError(f"Input file does not exist: {options.video_path}")
    if not options.api_key:
        raise SubtitleError("Missing GOOGLE_API_KEY or GEMINI_API_KEY.")

    mime_type = guess_mime_type(options.video_path)
    terms = load_terms(options.glossary_path)
    prompt = build_prompt(options.topic, options.language, terms, options.max_chars, options.mode)

    log(progress, "Uploading media to Gemini...")
    file_info = upload_file(options.video_path, options.api_key, mime_type)
    log(progress, "Waiting for media processing...")
    active_file = wait_until_active(options.api_key, file_info["name"])
    log(progress, "Generating SRT subtitles...")
    srt = generate_srt(
        api_key=options.api_key,
        model=options.model,
        file_uri=active_file["uri"],
        mime_type=mime_type,
        prompt=prompt,
    )
    options.output_path.parent.mkdir(parents=True, exist_ok=True)
    options.output_path.write_text(srt, encoding="utf-8")
    warnings = validate_srt(srt)
    log(progress, f"Done: {options.output_path}")
    return warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert video/audio into topic-aware SRT subtitles.")
    parser.add_argument("video", help="Input video or audio file path, for example ./input.mp4")
    parser.add_argument("-o", "--output", help="Output SRT path. Defaults to the same name as input.")
    parser.add_argument("--topic", default="", help="Topic/context, for example plant care tutorial")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="Subtitle language")
    parser.add_argument("--glossary", help="Glossary file. Supports .txt one term per line or .json string list")
    parser.add_argument("--mode", choices=sorted(MODES), default="general", help="Subtitle mode")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model. Default: {DEFAULT_MODEL}")
    parser.add_argument("--max-chars", type=int, default=22, help="Recommended max Chinese characters per line")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
    video_path = Path(args.video).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else video_path.with_suffix(".srt")
    glossary_path = Path(args.glossary).expanduser().resolve() if args.glossary else None

    options = ConvertOptions(
        video_path=video_path,
        output_path=output_path,
        api_key=api_key,
        topic=args.topic,
        language=args.language,
        glossary_path=glossary_path,
        mode=args.mode,
        model=args.model,
        max_chars=args.max_chars,
    )

    try:
        warnings = convert_video_to_srt(options, progress=print)
        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        return 0
    except SubtitleError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
