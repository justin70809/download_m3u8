# download_m3u8

一款功能完善的 Python 腳本，用於下載 HLS（`.m3u8`）串流影片，合併片段，並可選擇將生成的 Transport Stream（`.ts`）轉封裝為 MP4，且在轉檔過程中顯示實時進度。

## 功能一覽

- **串流擷取**：透過 Selenium 性能日誌自動捕捉網頁中的 `.m3u8` 連結
- **多執行緒下載**：使用 `ThreadPoolExecutor` 並行下載片段，加速整體下載時間
- **重試機制**：片段下載失敗後自動重試，並採用指數退避
- **詳細日誌**：錯誤時輸出片段 URL、HTTP 狀態碼與索引，方便除錯
- **主播放清單支援**：自動偵測多碼率播放清單，並提示使用者選擇變體串流
- **直播錄製**：可指定錄製時長，將直播片段持續抓取
- **下載進度條**：以 `tqdm` 顯示片段下載進度
- **TS→MP4 轉檔**：下載完成後，使用 `ffprobe` 取得媒體長度，再用 `ffmpeg` 轉封裝為 MP4，並顯示轉檔進度條

## 環境需求

- Python 3.x
- **套件依賴**（見 `requirements.txt`）：
  ```text
  cloudscraper
  selenium
  tqdm
  ```  
- **外部工具**：
  - Google Chrome 瀏覽器 及 相符版本的 ChromeDriver
  - FFmpeg (`ffmpeg`) 與 FFprobe (`ffprobe`)，並已加入系統 PATH

## 安裝步驟

1. 從 GitHub 克隆專案：
   ```bash
   git clone https://github.com/你的帳號/download_m3u8.git
   cd download_m3u8
   ```
2. 安裝 Python 套件：
   ```bash
   pip install -r requirements.txt
   ```
3. 確認 FFmpeg 與 FFprobe 可用：
   ```bash
   ffmpeg -version
   ffprobe -version
   ```

## 使用說明

執行主程式：
```bash
python download_m3u8.py <頁面網址或.m3u8 連結> [選項]
```

### 常用選項

- `-o, --output <檔名>`：輸出檔案名稱（預設 `output.ts`）
- `--concurrency <數字>`：同時下載片段的執行緒數（預設 8）
- `--live-duration <秒數>`：錄製直播時長（秒）
- `--retries <數字>`：片段下載重試次數（預設 3）
- `--no-convert`：下載完成後不做 TS→MP4 轉檔
- `--verbose`：顯示除錯級別日誌

### 使用範例

1. 下載固定播放清單並自動轉 MP4：
   ```bash
   python download_m3u8.py https://example.com/stream.m3u8 -o myvideo.ts
   ```

2. 錄製直播 60 秒：
   ```bash
   python download_m3u8.py https://example.com/live -o live.ts --live-duration 60
   ```

3. 只下載 TS，不轉 MP4：
   ```bash
   python download_m3u8.py https://example.com/stream.m3u8 -o raw.ts --no-convert
   ```

4. 開啟詳細日誌並使用 16 執行緒：
   ```bash
   python download_m3u8.py ... --verbose --concurrency 16
   ```

## 運作原理

1. **性能日誌擷取**：Selenium 以 headless 模式啟動 Chrome，並讀取瀏覽器的 Network logs 抓取 `.m3u8` URL
2. **播放清單解析**：自動處理主播放清單與媒體播放清單，若為多碼率則提示選擇
3. **片段下載**：收集所有 `.ts` 分段網址，去重後並行下載，失敗時重試
4. **檔案合併**：將下載的所有片段按順序寫入單一 `.ts` 檔
5. **封裝轉換**（可選）：用 `ffprobe` 取得影片總時長，再呼叫 `ffmpeg` 做容器重包裝，並以進度條顯示轉檔進度

## 貢獻指南

歡迎提出 issue 或 Pull Request：

1. Fork 專案
2. 建立分支：`git checkout -b feature/your-feature`
3. 提交修改：`git commit -m "Add your feature"`
4. 推送分支：`git push origin feature/your-feature`
5. 在 GitHub 上發起 PR

## 授權許可

本專案採用 MIT 授權，詳見 [LICENSE](LICENSE)。
