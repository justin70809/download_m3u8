#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enhanced download_m3u8.py with retry, detailed error reporting,
optional TS→MP4 conversion with progress bar via ffprobe & ffmpeg
Supports multiple downloads in one run and YouTube video-only format handling,
and uses a GUI dialog to select output path.
"""
import os
import sys
import json
import re
import argparse
import time
import logging
import subprocess
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import cloudscraper
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm
from yt_dlp import YoutubeDL
import tkinter as tk
from tkinter.filedialog import asksaveasfilename

# Custom exception
class DownloadError(Exception):
    pass

# Regex for .m3u8
M3U8_RE = re.compile(r"\.m3u8($|\?)")

# YouTube detection domains
ytdl_domains = ('youtube.com', 'youtu.be')

# Initialize cloudscraper session
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/114.0.0.0 Safari/537.36'
    ),
}
session = cloudscraper.create_scraper()
session.headers.update(HEADERS)


def choose_from_list(items, prompt_msg):
    """Prompt user to choose one item from a list."""
    for i, it in enumerate(items, 1):
        print(f"  [{i}] {it}")
    while True:
        sel = input(f"{prompt_msg} (1-{len(items)}): ").strip()
        if sel.isdigit() and 1 <= int(sel) <= len(items):
            return items[int(sel) - 1]
        print("Invalid selection, try again.")


def get_m3u8_via_perflog(page_url: str, timeout: int = 20) -> str:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    opts.add_argument(f"user-agent={HEADERS['User-Agent']}")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(page_url)
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        time.sleep(1)
        logs = driver.get_log('performance')
    except Exception as e:
        raise DownloadError(f"Failed to load page: {e}")
    finally:
        driver.quit()

    candidates = []
    for entry in logs:
        msg = json.loads(entry['message'])['message']
        if msg.get('method') == 'Network.responseReceived':
            url = msg['params']['response']['url']
            if M3U8_RE.search(url) and url not in candidates:
                candidates.append(url)

    if not candidates:
        raise DownloadError("No .m3u8 URLs found in performance logs.")
    if len(candidates) > 1:
        return choose_from_list(candidates, "Multiple .m3u8 found, select one")
    return candidates[0]


def parse_variant_playlist(text, base_url):
    lines = text.splitlines()
    streams = []
    for i, l in enumerate(lines):
        if l.startswith('#EXT-X-STREAM-INF') and i + 1 < len(lines):
            info = l.split(':', 1)[1]
            uri = lines[i + 1].strip()
            streams.append((info, urljoin(base_url, uri)))
    if streams:
        choices = [f"{info} → {uri}" for info, uri in streams]
        sel = choose_from_list(choices, "Select variant stream")
        idx = choices.index(sel)
        _, sel_uri = streams[idx]
        resp = session.get(sel_uri); resp.raise_for_status()
        new_base = sel_uri.rsplit('/', 1)[0] + '/'
        return resp.text.splitlines(), new_base
    return lines, base_url


def download_segment(idx, seg_url, retries=3, backoff=1):
    for attempt in range(1, retries + 1):
        try:
            r = session.get(seg_url, stream=True)
            r.raise_for_status()
            return idx, r.content
        except Exception as e:
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
            else:
                raise DownloadError(f"Segment {idx} failed: {e}")


def download_and_merge(m3u8_url: str, output_path: str,
                       concurrency: int = 5, live_duration: int = None,
                       retries: int = 3):
    resp = session.get(m3u8_url); resp.raise_for_status()
    base = m3u8_url.rsplit('/', 1)[0] + '/'
    lines, base = parse_variant_playlist(resp.text, base)
    segments = [urljoin(base, l.strip()) for l in lines if l and not l.startswith('#')]
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    results = {}
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {ex.submit(download_segment, i+1, seg): i+1 for i, seg in enumerate(segments)}
        for f in tqdm(as_completed(futures), total=len(futures), desc="Segments"):
            idx, data = f.result()
            results[idx] = data
    with open(output_path, 'wb') as fw:
        for i in range(1, len(segments)+1): fw.write(results[i])
    logging.info("Merge complete.")


def get_media_duration(path):
    try:
        cmd = ['ffprobe','-v','error','-show_entries','format=duration','-of','json',path]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(json.loads(res.stdout)['format']['duration'])
    except:
        return None


def convert_ts_to_mp4(ts_path, mp4_path):
    duration = get_media_duration(ts_path)
    cmd = ['ffmpeg','-i',ts_path,'-c','copy','-movflags','+faststart',mp4_path,'-progress','pipe:1']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if duration:
        pbar = tqdm(total=int(duration), unit='sec', desc='Converting')
        for line in proc.stdout:
            if 'out_time_ms' in line:
                pbar.update(int(int(line.split('=')[1])/1e6) - pbar.n)
        pbar.close()
    proc.wait()


def main():
    parser = argparse.ArgumentParser(
        description="Download HLS (.m3u8) and merge segments, or YouTube videos via yt-dlp"
    )
    parser.add_argument('url', nargs='?', help='Page URL, .m3u8 link, or YouTube URL')
    parser.add_argument('--output','-o', default='output.ts', help='Output filename')
    parser.add_argument('--concurrency', type=int, default=8, help='Concurrent downloads')
    parser.add_argument('--live-duration', type=int, help='Live capture duration (s)')
    parser.add_argument('--retries', type=int, default=3, help='Retry attempts')
    parser.add_argument('--no-convert', action='store_true', help='Skip TS→MP4 conversion')
    parser.add_argument('--verbose', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    lvl = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(format='[%(levelname)s] %(message)s', level=lvl)

    while True:
        # GUI dialog for output path each loop
        root = tk.Tk()
        root.withdraw()
        default_ext = os.path.splitext(args.output)[1] or ''
        out_path = asksaveasfilename(title="選擇輸出路徑",
                                     initialfile=os.path.basename(args.output),
                                     defaultextension=default_ext,
                                     filetypes=[("All Files", "*.*")])
        root.destroy()
        if not out_path:
            print("未選擇保存路徑，退出。")
            sys.exit(0)
        args.output = out_path

        try:
            url = args.url or input('Enter page URL, .m3u8 link, or YouTube URL: ').strip()

            # YouTube handling
            if any(d in url for d in ytdl_domains):
                subprocess.run(['yt-dlp','--list-formats','--no-playlist',url], check=True)
                fmt_code = input("請輸入 format_id（如48、bestvideo+bestaudio）: ").strip()
                info = YoutubeDL({'quiet':True}).extract_info(url, download=False)
                fmt = next((f for f in info['formats'] if str(f['format_id']) == fmt_code), None)
                if fmt and fmt.get('acodec') == 'none':
                    if input("Video-only格式，是否下載並合併最佳音訊？(y/n): ").strip().lower() == 'y':
                        fmt_code += "+bestaudio"
                ydl_opts = {'format': fmt_code, 'outtmpl': args.output, 'retries': args.retries, 'noplaylist': True}
                YoutubeDL(ydl_opts).download([url])

                if input("下載完成，繼續下一個？(y/n): ").strip().lower() != 'y':
                    break
                args.url = None
                continue

            # HLS logic
            m3u8 = url if url.lower().endswith('.m3u8') else get_m3u8_via_perflog(url)
            download_and_merge(m3u8, args.output, args.concurrency, args.live_duration, args.retries)

            if not args.no_convert and args.output.lower().endswith('.ts'):
                mp4_path = os.path.splitext(args.output)[0] + '.mp4'
                try:
                    convert_ts_to_mp4(args.output, mp4_path)
                    logging.info(f"Converted to MP4: {mp4_path}")
                except Exception as e:
                    logging.error(f"Convert failed: {e}")

            if input("下載完成，繼續下一個？(y/n): ").strip().lower() != 'y':
                break
            args.url = None

        except DownloadError as e:
            logging.error(e)
            if input("發生錯誤，繼續下一個？(y/n): ").strip().lower() != 'y':
                sys.exit(1)
            args.url = None

if __name__ == '__main__':
    main()
