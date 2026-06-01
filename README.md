# 通用影片 / 音訊轉 SRT 字幕工具

這個工具可以把各種類型的影片或音訊轉成 `.srt` 字幕，並用主題、術語表、上下文語意來修正辨識結果。

支援兩種操作方式：

- GUI 操控面板：適合日常使用
- 命令列：適合批次處理、未來接到其他系統
- Web 上傳頁面：適合部署成網址使用

目前已預留擴充模式，之後可以針對歌曲做更細的歌詞時間軸、重複副歌、KTV 字幕等功能。

## 功能

- 影片或音訊轉 `.srt`
- 通用影片字幕
- 特定主題強化，例如課程、訪談、產品介紹、會議、植物照顧
- 專有名詞 / 術語表修正
- 破音字、多音字、同音字語意修正
- 歌曲 / 歌詞模式預留
- GUI 操控面板
- 命令列批次處理
- 網頁上傳與下載 SRT

## 安全提醒

如果 API key 曾經貼到聊天、文件或公開地方，建議重新產生一把新的金鑰，並停用舊金鑰。

程式不會把金鑰寫進檔案。GUI 可以手動貼上金鑰，也可以讀取環境變數。

## 開啟 GUI

最簡單的方式是雙擊：

```text
start_subtitle_gui.bat
```

PowerShell：

```powershell
python subtitle_gui.py
```

如果你的電腦找不到 `python`，可以使用 Codex 內建 Python：

```powershell
& "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" subtitle_gui.py
```

GUI 裡可以設定：

- 影片或音訊檔
- 輸出 `.srt` 位置
- 術語表
- 模式：一般影片、教學/主題影片、植物照顧、歌曲/歌詞
- 主題
- 字幕語言
- Gemini 模型
- Google API Key

## 命令列用法

先設定 Google API Key：

```powershell
$env:GOOGLE_API_KEY="你的 Google API Key"
```

基本轉字幕：

```powershell
python video_to_subtitles.py "C:\影片\example.mp4"
```

一般影片：

```powershell
python video_to_subtitles.py "C:\影片\example.mp4" --mode general --topic "課程教學，內容是資料分析與報表製作"
```

植物照顧影片：

```powershell
python video_to_subtitles.py "C:\影片\plant.mp4" --mode plant --topic "植物照顧教學，包含施肥、繁殖、澆水與病蟲害" --glossary glossary_plant.example.txt
```

歌曲 / 歌詞模式：

```powershell
python video_to_subtitles.py "C:\音樂\song.mp3" --mode song --topic "流行歌曲歌詞，保留副歌重複與英文片語"
```

指定輸出檔：

```powershell
python video_to_subtitles.py "C:\影片\plant.mp4" -o "C:\影片\plant_subtitle.srt"
```

## 術語表格式

可以建立 `.txt`，一行一個詞：

```text
龜背芋
虎尾蘭
黃金葛
鹿角蕨
介質
緩釋肥
液肥
扦插
分株
葉插
介殼蟲
紅蜘蛛
爛根
```

也支援 `.json`：

```json
["龜背芋", "虎尾蘭", "黃金葛", "扦插", "分株"]
```

## 模式設計

目前模式在 `video_to_subtitles.py` 的 `MODES` 裡：

- `general`：一般影片
- `teaching`：教學 / 主題影片
- `plant`：植物照顧
- `song`：歌曲 / 歌詞

之後如果要接新功能，例如法律、醫療、財經、Podcast、逐字稿，可以新增模式，不需要重寫整套程式。

## 關於 STL

你一開始提到 `stl`，一般剪輯與影音平台最常用的是 `.srt`。目前先輸出 `.srt`，最適合 YouTube、剪映、Premiere、DaVinci Resolve 等工具。

如果你確定需要廣播系統用的 EBU `.stl`，之後可以再加一個輸出轉換器。

## Web 版

本機測試：

```powershell
$env:GOOGLE_API_KEY="你的 Google API Key"
python web_server.py
```

打開：

```text
http://127.0.0.1:8000
```

部署到公開網址請看 [DEPLOY.md](DEPLOY.md)。
