#!/usr/bin/env python3
"""
Minimal web app for uploading media and downloading generated SRT subtitles.

This server intentionally uses only Python's standard library so it is easy to
run locally or on a small hosting service. For public production use, put it
behind HTTPS and set GOOGLE_API_KEY as a server-side environment variable.
"""

from __future__ import annotations

import cgi
import html
import os
import shutil
import tempfile
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from video_to_subtitles import (
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    MODES,
    ConvertOptions,
    SubtitleError,
    convert_video_to_srt,
)


HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "300"))
WORK_DIR = Path(os.environ.get("WORK_DIR", Path(tempfile.gettempdir()) / "subtitle_web_jobs")).resolve()


INDEX_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>影片 / 歌曲轉 SRT 字幕</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f4;
      --text: #1e2620;
      --muted: #607063;
      --line: #d9ded7;
      --accent: #2d6a4f;
      --accent-dark: #1f513b;
      --panel: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: system-ui, -apple-system, "Microsoft JhengHei", "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    main {{
      width: min(920px, calc(100% - 32px));
      margin: 32px auto;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      line-height: 1.2;
    }}
    p {{
      margin: 0 0 22px;
      color: var(--muted);
      line-height: 1.7;
    }}
    form {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
      box-shadow: 0 12px 30px rgba(30, 38, 32, 0.08);
    }}
    .grid {{
      display: grid;
      grid-template-columns: 160px 1fr;
      gap: 14px 16px;
      align-items: center;
    }}
    label {{
      font-weight: 650;
      color: #27362c;
    }}
    input, select, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      background: #fff;
      color: var(--text);
    }}
    textarea {{
      min-height: 96px;
      resize: vertical;
      line-height: 1.6;
    }}
    .hint {{
      grid-column: 2;
      margin-top: -8px;
      color: var(--muted);
      font-size: 14px;
    }}
    .actions {{
      display: flex;
      justify-content: flex-end;
      margin-top: 20px;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 700;
      padding: 12px 18px;
      cursor: pointer;
    }}
    button:hover {{ background: var(--accent-dark); }}
    .status {{
      margin-top: 16px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--muted);
      background: #fbfcfa;
    }}
    @media (max-width: 700px) {{
      main {{ margin: 20px auto; }}
      .grid {{ grid-template-columns: 1fr; }}
      .hint {{ grid-column: 1; }}
      .actions {{ justify-content: stretch; }}
      button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>影片 / 歌曲轉 SRT 字幕</h1>
    <p>上傳任何影片或音訊，選擇最接近的模式並描述主題，完成後直接下載 SRT 字幕檔。API key 放在伺服器端，不會出現在網頁裡。</p>
    <form method="post" action="/convert" enctype="multipart/form-data">
      <div class="grid">
        <label for="media">影片或音訊</label>
        <input id="media" name="media" type="file" accept="video/*,audio/*" required>

        <label for="mode">模式</label>
        <select id="mode" name="mode">
          {mode_options}
        </select>

        <label for="topic">主題</label>
        <textarea id="topic" name="topic">請簡短描述影片主題，例如：課程教學、訪談、產品介紹、會議紀錄、旅遊 Vlog、歌曲歌詞</textarea>
        <div class="hint">主題越清楚，專有名詞和同音字修正通常越準。歌曲可填：流行歌曲歌詞，保留副歌重複與英文片語。</div>

        <label for="glossary">術語表</label>
        <textarea id="glossary" name="glossary" placeholder="一行一個詞，例如：龜背芋&#10;緩釋肥&#10;扦插"></textarea>

        <label for="language">字幕語言</label>
        <input id="language" name="language" value="{language}">

        <label for="max_chars">每行字數</label>
        <input id="max_chars" name="max_chars" type="number" min="12" max="40" value="22">
      </div>
      <div class="actions">
        <button type="submit">產生並下載 SRT</button>
      </div>
    </form>
    <div class="status">大型影片可能需要幾分鐘。送出後請保持網頁開啟，完成時瀏覽器會下載字幕檔。</div>
  </main>
</body>
</html>
"""


def safe_filename(name: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name).strip()
    return cleaned or fallback


def render_index() -> bytes:
    options = "\n".join(
        f'<option value="{html.escape(key)}"{" selected" if key == "general" else ""}>{html.escape(info["label"])}</option>'
        for key, info in MODES.items()
    )
    return INDEX_HTML.format(mode_options=options, language=html.escape(DEFAULT_LANGUAGE)).encode("utf-8")


class SubtitleWebHandler(BaseHTTPRequestHandler):
    server_version = "SubtitleWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(render_index())
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/convert":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        try:
            self.handle_convert()
        except SubtitleError as exc:
            self.send_text_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self.send_text_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Unexpected error: {exc}")

    def handle_convert(self) -> None:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
        if not api_key:
            raise SubtitleError("Server is missing GOOGLE_API_KEY or GEMINI_API_KEY.")

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > MAX_UPLOAD_MB * 1024 * 1024:
            raise SubtitleError(f"Upload is too large. Current limit is {MAX_UPLOAD_MB} MB.")

        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        media_item = form["media"] if "media" in form else None
        if not media_item or not getattr(media_item, "filename", ""):
            raise SubtitleError("Please upload a video or audio file.")

        job_dir = WORK_DIR / uuid.uuid4().hex
        job_dir.mkdir(parents=True, exist_ok=True)
        try:
            original_name = safe_filename(media_item.filename, "input.mp4")
            input_path = job_dir / original_name
            with input_path.open("wb") as target:
                shutil.copyfileobj(media_item.file, target)

            glossary_text = self.get_field(form, "glossary")
            glossary_path = None
            if glossary_text.strip():
                glossary_path = job_dir / "glossary.txt"
                glossary_path.write_text(glossary_text, encoding="utf-8")

            output_path = job_dir / f"{input_path.stem}.srt"
            mode = self.get_field(form, "mode") or "general"
            if mode not in MODES:
                mode = "general"
            max_chars_text = self.get_field(form, "max_chars") or "22"
            try:
                max_chars = max(12, min(40, int(max_chars_text)))
            except ValueError:
                max_chars = 22

            options = ConvertOptions(
                video_path=input_path,
                output_path=output_path,
                api_key=api_key,
                topic=self.get_field(form, "topic"),
                language=self.get_field(form, "language") or DEFAULT_LANGUAGE,
                glossary_path=glossary_path,
                mode=mode,
                model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
                max_chars=max_chars,
            )
            convert_video_to_srt(options)
            self.send_file(output_path, download_name=output_path.name)
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    @staticmethod
    def get_field(form: cgi.FieldStorage, name: str) -> str:
        if name not in form:
            return ""
        item = form[name]
        if isinstance(item, list):
            item = item[0]
        value = item.value
        return value if isinstance(value, str) else ""

    def send_file(self, path: Path, download_name: str) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-subrip; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(data)

    def send_text_error(self, status: HTTPStatus, message: str) -> None:
        body = f"{status.value} {status.phrase}\n\n{message}\n".encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), SubtitleWebHandler)
    print(f"Subtitle web app running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
