from pathlib import Path
import re
from faster_whisper import WhisperModel
from opencc import OpenCC

INPUT = Path("input")
OUTPUT = Path("generated-srt")
OUTPUT.mkdir(exist_ok=True)
CC = OpenCC("s2twp")

PROMPTS = {
    "從角色、世界觀到分鏡！一套工作流完成整個故事宇宙": "角色、世界觀、分鏡、故事宇宙、提示詞、角色一致性、Gemini、Flow、生成式 AI。",
    "AI_自動字幕不夠準？KTV_字幕大師課：從生成到專業手動校正": "KTV 字幕、卡拉 OK、SRT、ASS、Aegisub、剪映、FFmpeg、Whisper、時間軸、逐字變色。",
    "別再亂花錢！AI_影片生成模型性價比排行榜": "AI 影片生成模型、Veo、Sora、Runway、Kling、可靈、Hailuo、海螺、Seedance、Pika、Luma、性價比、訂閱制、點數。",
}


def timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def clean(text: str) -> str:
    text = CC.convert(text.strip())
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff，。！？；：、])", "", text)
    text = re.sub(r"(?<=[，。！？；：、])\s+(?=[\u3400-\u9fff])", "", text)
    return text.strip()


def visible_length(text: str) -> int:
    return len(text.replace(" ", ""))


def wrap(text: str, limit: int = 22) -> str:
    if visible_length(text) <= limit:
        return text
    midpoint = len(text) // 2
    breaks = [
        index + 1
        for index, character in enumerate(text)
        if character in "，。！？；：、" and 7 <= index <= len(text) - 7
    ]
    split_at = min(breaks, key=lambda index: abs(index - midpoint)) if breaks else midpoint
    return text[:split_at].strip() + "\n" + text[split_at:].strip()


def build_cues(segments):
    raw_cues = []
    punctuation = set("，。！？；：")
    for segment in segments:
        words = list(segment.words or [])
        if not words:
            text = clean(segment.text)
            if text:
                raw_cues.append([float(segment.start), float(segment.end), wrap(text)])
            continue

        parts, start, end = [], None, None
        for word in words:
            token = clean(word.word)
            if not token:
                continue
            if start is None:
                start = float(word.start if word.start is not None else segment.start)
            end = float(word.end if word.end is not None else segment.end)
            parts.append(token)
            text = clean("".join(parts))
            should_break = (
                (visible_length(text) >= 18 and text[-1:] in punctuation)
                or visible_length(text) >= 28
                or end - start >= 6.0
            )
            if should_break:
                raw_cues.append([start, max(end, start + 0.35), wrap(text)])
                parts, start, end = [], None, None
        if parts:
            text = clean("".join(parts))
            raw_cues.append([start, max(end, start + 0.35), wrap(text)])

    final = []
    for start, end, text in raw_cues:
        if final and text == final[-1][2]:
            final[-1][1] = max(final[-1][1], end)
            continue
        if final and start < final[-1][1]:
            boundary = max(final[-1][0] + 0.25, (final[-1][1] + start) / 2)
            final[-1][1] = boundary
            start = boundary
        final.append([start, max(end, start + 0.35), text])
    return final


print("Loading faster-whisper medium model...", flush=True)
MODEL = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=4, num_workers=1)

for video in sorted(INPUT.glob("*.mp4")):
    print(f"Transcribing {video.name}", flush=True)
    segments, info = MODEL.transcribe(
        str(video),
        language="zh",
        task="transcribe",
        beam_size=5,
        best_of=5,
        temperature=0.0,
        condition_on_previous_text=True,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 200},
        initial_prompt=video.stem + "。" + PROMPTS.get(video.stem, ""),
        hallucination_silence_threshold=2.0,
    )
    cues = build_cues(segments)
    destination = OUTPUT / f"{video.stem}.srt"
    with destination.open("w", encoding="utf-8-sig", newline="\n") as handle:
        for number, (start, end, text) in enumerate(cues, 1):
            handle.write(f"{number}\n{timestamp(start)} --> {timestamp(end)}\n{text}\n\n")
    print(f"Created {destination.name}: {len(cues)} cues; language={info.language}", flush=True)

files = sorted(OUTPUT.glob("*.srt"))
if len(files) != 3:
    raise RuntimeError(f"Expected 3 SRT files, got {len(files)}")
for file in files:
    content = file.read_text(encoding="utf-8-sig")
    if "-->" not in content or len(content) < 500:
        raise RuntimeError(f"Invalid SRT output: {file}")
