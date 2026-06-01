#!/usr/bin/env python3
"""
Minimal web app for uploading media and downloading generated SRT subtitles.

For public production use, put it behind HTTPS and set GOOGLE_API_KEY as a
server-side environment variable.
"""

from __future__ import annotations

import cgi
import os
import shutil
import tempfile
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from video_to_subtitles import (
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
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
  <title>Lidiya 實驗室專用字幕平台</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07090f;
      --panel: rgba(16, 20, 31, 0.94);
      --text: #eef3f8;
      --muted: #94a3b8;
      --line: rgba(120, 141, 170, 0.34);
      --accent: #62c7e8;
      --accent-2: #8f7cff;
      --ad: rgba(148, 163, 184, 0.28);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: system-ui, -apple-system, "Microsoft JhengHei", "Segoe UI", sans-serif;
      background:
        linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px),
        radial-gradient(circle at 20% 10%, rgba(98,199,232,0.12), transparent 25%),
        radial-gradient(circle at 80% 5%, rgba(143,124,255,0.10), transparent 24%),
        linear-gradient(135deg, #07090f 0%, #0d1220 52%, #080b12 100%);
      background-size: 44px 44px, 44px 44px, auto, auto, auto;
      color: var(--text);
    }}
    .page {{
      width: min(1320px, calc(100% - 28px));
      margin: 24px auto;
      display: grid;
      grid-template-columns: minmax(140px, 1fr) minmax(420px, 760px) minmax(140px, 1fr);
      gap: 18px;
      align-items: start;
    }}
    .ad {{
      min-height: 620px;
      border: 1px dashed var(--ad);
      border-radius: 8px;
      color: #64748b;
      display: grid;
      place-items: center;
      background: rgba(15, 23, 42, 0.35);
      font-size: 14px;
    }}
    main {{ min-width: 0; }}
    h1 {{
      margin: 0 0 8px;
      font-size: 32px;
      line-height: 1.25;
      letter-spacing: 0;
      text-shadow: 0 0 18px rgba(98,199,232,0.22);
    }}
    p {{
      margin: 0 0 18px;
      color: var(--muted);
      line-height: 1.7;
    }}
    form {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
      box-shadow: 0 16px 48px rgba(0,0,0,0.42), 0 0 36px rgba(98,199,232,0.08);
      backdrop-filter: blur(10px);
    }}
    .grid {{
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 14px 16px;
      align-items: center;
    }}
    label {{
      font-weight: 700;
      color: #dbe7f3;
    }}
    input, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      background: rgba(6, 10, 24, 0.84);
      color: var(--text);
      outline: none;
    }}
    input:focus, select:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(98,199,232,0.12);
    }}
    .hint {{
      grid-column: 2;
      margin-top: -8px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }}
    .actions {{
      display: flex;
      justify-content: flex-end;
      margin-top: 20px;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      color: #071018;
      font: inherit;
      font-weight: 800;
      padding: 12px 18px;
      cursor: pointer;
      box-shadow: 0 0 20px rgba(98,199,232,0.18), 0 0 20px rgba(143,124,255,0.10);
    }}
    button:hover {{ filter: brightness(1.1); }}
    .status {{
      margin-top: 16px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--muted);
      background: rgba(16, 22, 41, 0.72);
      line-height: 1.6;
    }}
    @media (max-width: 900px) {{
      .page {{ grid-template-columns: 1fr; }}
      .ad {{ min-height: 96px; }}
    }}
    @media (max-width: 620px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .hint {{ grid-column: 1; }}
      .actions {{ justify-content: stretch; }}
      button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <aside class="ad">左側廣告欄位</aside>
    <main>
      <h1>Lidiya 實驗室專用字幕平台</h1>
      <p>上傳影片或音訊，系統會依標題判斷內容，輸出繁體中文 SRT 字幕。</p>
      <form method="post" action="/convert" enctype="multipart/form-data">
        <div class="grid">
          <label for="media">影片或音訊</label>
          <input id="media" name="media" type="file" accept="video/*,audio/*" required>

          <label for="title">標題</label>
          <input id="title" name="title" type="text" placeholder="例如：AI 課程錄影、會議紀錄、流行歌曲翻唱" required>
          <div class="hint">標題會用來判斷主題、專有名詞與破音字。</div>

          <label for="mode">模式</label>
          <select id="mode" name="mode">
            <option value="broadcast" selected>廣播講話聲音</option>
            <option value="song">歌曲</option>
          </select>

          <label for="max_chars">每行字數</label>
          <input id="max_chars" name="max_chars" type="number" min="8" max="40" value="22">
          <div class="hint">預設 22 字以內。優先用句點斷句；沒有句點時，用逗點斷句。</div>
        </div>
        <div class="actions">
          <button type="submit">產生並下載 SRT</button>
        </div>
      </form>
      <div class="status">大型影片可能需要幾分鐘。請保持頁面開啟，完成後瀏覽器會下載字幕檔。</div>
    </main>
    <aside class="ad">右側廣告欄位</aside>
  </div>
</body>
</html>
"""


def safe_filename(name: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name).strip()
    return cleaned or fallback


def render_index() -> bytes:
    return INDEX_HTML.encode("utf-8")


class SubtitleWebHandler(BaseHTTPRequestHandler):
    server_version = "SubtitleWeb/0.2"

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
        if media_item is None or not getattr(media_item, "filename", ""):
            raise SubtitleError("Please upload a video or audio file.")

        job_dir = WORK_DIR / uuid.uuid4().hex
        job_dir.mkdir(parents=True, exist_ok=True)
        try:
            original_name = safe_filename(media_item.filename, "input.mp4")
            input_path = job_dir / original_name
            with input_path.open("wb") as target:
                shutil.copyfileobj(media_item.file, target)

            output_path = job_dir / f"{input_path.stem}.srt"
            mode = self.get_field(form, "mode") or "broadcast"
            if mode not in {"broadcast", "song"}:
                mode = "broadcast"

            max_chars_text = self.get_field(form, "max_chars") or "22"
            try:
                max_chars = max(8, min(40, int(max_chars_text)))
            except ValueError:
                max_chars = 22

            title = self.get_field(form, "title").strip()
            if not title:
                title = input_path.stem

            options = ConvertOptions(
                video_path=input_path,
                output_path=output_path,
                api_key=api_key,
                topic=f"Title: {title}",
                language=DEFAULT_LANGUAGE,
                glossary_path=None,
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
