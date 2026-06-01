# GitHub + Render 部署說明

這是通用影片 / 音訊轉 SRT 字幕工具的 Web 版部署說明。

## 重要觀念

GitHub 是放程式碼的地方，不是執行影片轉字幕的伺服器。

要讓你用網址上傳影片、產生字幕、下載 SRT，需要把 GitHub 程式部署到 Render、Railway、Fly.io 或自己的主機。

## 建議先用 Render

Render 可以直接連接 GitHub repository，部署後會給你一個網址。

## 要上傳 GitHub 的檔案

請上傳 `02_上傳GitHub部署Web版` 裡面的全部檔案，包含：

```text
.gitignore
.python-version
DEPLOY.md
GitHub上傳_先看我.txt
README.md
glossary_plant.example.txt
runtime.txt
video_to_subtitles.py
web_server.py
```

## Render 設定

Build Command:

```bash
echo "no build needed"
```

Start Command:

```bash
python web_server.py
```

Instance Type:

```text
Free
```

## Render 環境變數

請在 Render 的 Environment Variables 加上：

```text
GOOGLE_API_KEY=你的 Google API Key
HOST=0.0.0.0
PYTHON_VERSION=3.12.8
MAX_UPLOAD_MB=300
```

Render 免費方案記憶體較小。若影片上傳後出現 502，建議先把 `MAX_UPLOAD_MB` 設成 `120` 或更低，並用較短影片測試。

`PYTHON_VERSION=3.12.8` 很重要。Render 目前可能預設使用 Python 3.14，但 Python 3.14 移除了 `cgi`，會造成目前這版程式啟動失敗。

專案也放了 `.python-version`，內容是：

```text
3.12.8
```

這是第二層保險。

## 重新部署

更新 GitHub 後，到 Render 按：

```text
Manual Deploy
Deploy latest commit
```

如果還是抓到舊版本，可以改按：

```text
Clear build cache & deploy
```

## 成功的 Log

成功時應該會看到類似：

```text
Using Python version 3.12.8
Running 'python web_server.py'
Subtitle web app running at http://0.0.0.0:8000
```

## 免費方案提醒

Render 免費方案閒置後會休眠，第一次打開可能慢 50 秒以上。這不是錯誤。
