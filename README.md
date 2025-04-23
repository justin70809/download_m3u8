# download_m3u8
> **HLS／YouTube 影音下載 + 轉檔** — 以 Python 實作，支援自動擷取 `.m3u8`、並行下載、TS→MP4 重封裝，以及互動式格式選擇。

## 特色

| 功能 | 說明 |
|------|------|
| **HLS 自動偵測** | 透過 *headless* Chrome 分析 *Performance Log*，自動抓取隱藏在網頁中的 `.m3u8` 連結，並支援多碼率主播放清單手動挑選。 |
| **YouTube 下載** | 內建 `yt‑dlp`，單支影片或播放清單皆可。可一次抓「最佳視訊＋音訊」，或逐支影片互動選擇 `format_id`。 |
| **多執行緒下載** | 片段以 *ThreadPoolExecutor* 並行下載，內建重試與指數退避；`tqdm` 進度條即時顯示。 |
| **TS → MP4 快速封裝** | 下載完成後自動以 `ffmpeg -c copy` 重封裝並加上 `+faststart`，再刪除暫存 TS。 |
| **圖形化檔案對話框** | 透過 `tkinter` 讓使用者選擇輸出位置，減少 CLI 參數記憶負擔。 |
| **一鍵打包** | 使用 PyInstaller `--onefile`，可將 `chromedriver / ffmpeg / ffprobe` 一併內嵌，成品在乾淨電腦上可直接執行。 |

---

## 立即體驗

```bash
# 1. 下載原始碼
$ git clone https://github.com/justin70809/download_m3u8.git
$ cd download_m3u8

# 2. 建立虛擬環境並安裝相依
$ python -m venv .venv
$ source .venv/bin/activate   # Windows 改用 .venv\Scripts\Activate.ps1
$ pip install -r requirements.txt

# 3. 執行
$ python download_m3u8.py <URL 或 .m3u8 或 YouTube>
```

:::details 常見步驟流程
1. **輸入網址**：支援一般網頁、直接 `.m3u8`、YouTube 影片／播放清單。
2. **互動式選擇**：
   - HLS：若偵測到多變體播放清單，顯示列表供選擇。
   - YouTube：列出可用格式，允許 `bestvideo+bestaudio` 或自定 `format_id`。
3. **選擇輸出路徑**：跳出檔案（或資料夾）對話框。
4. **並行下載**：終端顯示進度條。
5. **自動轉檔**：下載完成後自動封裝 MP4，並刪除 TS。
6. **是否繼續**：可連續下載多個網址。
:::

---

## CLI 參數

| 參數 | 預設 | 說明 |
|------|------|------|
| `url` | – | 目標網址，可省略並於互動提示輸入。 |
| `--concurrency` | `8` | 片段下載並行數。 |
| `--live-duration` | – | 直播錄製秒數（HLS live）。 |
| `--retries` | `3` | 單片段下載重試次數。 |
| `--no-convert` | `False` | 跳過 TS→MP4 重封裝。 |
| `--verbose` | `False` | 顯示除錯訊息。 |

---

## 打包成單一可執行檔

```powershell
# Windows PowerShell 範例
(.venv) PS> pyinstaller --onefile --console ^
            --add-binary "bin\chromedriver.exe;." ^
            --add-binary "bin\ffmpeg.exe;." ^
            --add-binary "bin\ffprobe.exe;." ^
            download_m3u8.py
```

- 打包後的可執行檔將會放在 [`exe`](exe)` 資料夾。
- 內嵌 ChromeDriver、FFmpeg、FFprobe，不需另行安裝。
- 若你在原始碼目錄執行程式，請確保以下外部執行檔已放入 `bin/` 或加入系統 PATH：
  - `chromedriver.exe`
  - `ffmpeg.exe`
  - `ffprobe.exe`

---

## 相依

- Python 3.8+
- Google Chrome ＆ 對應版本的 ChromeDriver
- FFmpeg / FFprobe

> 若使用上方 *one‑file* 版本，可忽略 ChromeDriver 與 FFmpeg 之安裝。

### `requirements.txt`

```
cloudscraper
selenium
tqdm
yt_dlp
tk
```

---

## 疑難排解

| 情況 | 解決方案 |
|-------|-----------|
| ChromeDriver 版本錯誤 | 透過 `chrome://version` 取得瀏覽器版本，再前往 <https://chromedriver.chromium.org/downloads> 下載對應版本。 |
| `.m3u8` 未偵測到 | 部分站點需於載入前先啟動瀏覽器錄製；請重新執行並直接貼入目標頁面 URL。 |
| FFmpeg 找不到 | 確定已在 PATH，或於打包時使用 `--add-binary "ffmpeg.exe;."` 內嵌。 |

---

## 授權

本專案採用 **GNU General Public License v3.0**。詳見 [`LICENSE`](LICENSE)。
本專案使用了若干第三方二進位和函式庫，詳見 [THIRD-PARTY.md](THIRD-PARTY.md)。
---

## 致謝

- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) — YouTube 下載核心
- Selenium & ChromeDriver — HLS 擷取
- `tqdm` — 終端進度條
- `cloudscraper` — Cloudflare 防護繞過

> 本工具僅供個人學術研究與合法用途。使用者應自行負責遵守各平臺之使用條款及著作權規範。

