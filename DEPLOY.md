# 放到 GitHub 並用網址轉字幕

可以把通用影片 / 音訊轉 SRT 工具放到 GitHub，但要注意：

GitHub 本身只是存放程式碼。若要讓使用者用網址上傳影片、等待轉字幕、下載 SRT，需要部署到「會執行 Python 的伺服器」。

## 不建議只用 GitHub Pages

GitHub Pages 適合靜態網頁，不適合這個工具，原因是：

- 不能安全保存 Google API Key
- 不能在伺服器端接收大型影片
- 不能執行 Python 轉字幕流程
- 不能長時間等待 Gemini 處理影片

## 建議部署方式

比較簡單的選擇：

- Render
- Railway
- Fly.io
- 自己的 VPS / 雲端主機

這些平台可以從 GitHub 讀取程式碼，然後啟動 `web_server.py`。

## 需要設定的環境變數

在部署平台後台設定：

```text
GOOGLE_API_KEY=你的 Google API Key
HOST=0.0.0.0
PORT=8000
MAX_UPLOAD_MB=300
```

如果平台會自動提供 `PORT`，就使用平台提供的值。

## 啟動指令

```bash
python web_server.py
```

## Python 版本

專案包含 `runtime.txt`，請讓部署平台使用：

```text
python-3.12.8
```

Render 如果使用 Python 3.14，會因為標準函式庫移除 `cgi` 而啟動失敗。

或在 Windows 本機測試：

```powershell
$env:GOOGLE_API_KEY="你的 Google API Key"
python web_server.py
```

然後打開：

```text
http://127.0.0.1:8000
```

## GitHub 上傳流程

1. 建立 GitHub repository。
2. 把這個資料夾裡的程式推上去。
3. 到 Render / Railway / Fly.io 建立新服務。
4. 連接 GitHub repository。
5. 設定環境變數 `GOOGLE_API_KEY`。
6. 啟動指令填 `python web_server.py`。
7. 部署完成後平台會給你一個網址。

## 現有 Web 功能

- 開網址看到上傳表單
- 上傳影片或音訊
- 選模式：一般影片、教學/主題影片、植物照顧、歌曲/歌詞
- 填主題
- 填術語表
- 產生並下載 `.srt`

## 之後建議加強

公開上線前，建議再加：

- 登入權限
- 單次上傳大小限制
- 使用次數限制
- 任務排隊與進度條
- 轉檔完成後暫存下載連結
- 自動刪除影片與字幕
- API 使用量控管

如果這個網址只給自己用，可以先用目前版本部署；如果要開放給很多人用，建議先加登入與用量限制。
