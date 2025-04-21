#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enhanced download_m3u8.py with retry, detailed error reporting,
optional TS→MP4 conversion with progress bar via ffprobe & ffmpeg

Features:
1) Explicit wait instead of fixed sleep
2) Retry mechanism for segment downloads
3) Detailed error reporting (URL, HTTP status, segment index)
4) ThreadPoolExecutor for concurrent segment downloads
5) Master playlist selection and optional live-stream capture
6) tqdm progress bars and standard logging
7) Exceptions instead of sys.exit for better structure
8) Post-process conversion from .ts to .mp4 via ffmpeg
   with accurate conversion progress using ffprobe

Usage:
  python download_m3u8.py <page_url_or_m3u8> [--output OUTPUT]
                            [--concurrency N] [--live-duration SECS]
                            [--retries R] [--no-convert] [--verbose]

If no URL provided, prompts interactively.
Always prompts user to choose output path after parsing arguments.
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

# Custom exception
class DownloadError(Exception):
    pass

# Regex for .m3u8
M3U8_RE = re.compile(r"\.m3u8($|\?)")

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
    """
    Use Selenium performance log to capture network responses for .m3u8 URLs.
    Explicitly wait for page ready and then grab logs.
    """
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

    logging.info(f"Auto-selected m3u8 URL: {candidates[0]}")
    return candidates[0]


def parse_variant_playlist(text, base_url):
    """
    If master playlist, prompt user to select a variant stream.
    Returns tuple(lines, new_base_url).
    """
    lines = text.splitlines()
    streams = []
    for i, l in enumerate(lines):
        if l.startswith('#EXT-X-STREAM-INF') and i + 1 < len(lines):
            info = l[len('#EXT-X-STREAM-INF:'):].strip()
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
    """
    Download a single segment with retry mechanism.
    """
    for attempt in range(1, retries + 1):
        try:
            r = session.get(seg_url, stream=True)
            r.raise_for_status()
            return idx, r.content
        except Exception as e:
            status = getattr(e, 'response', None)
            code = status.status_code if status else 'N/A'
            logging.warning(
                f"Segment {idx}: attempt {attempt}/{retries} failed: URL={seg_url} HTTP={code} Error={e}"
            )
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
            else:
                raise DownloadError(
                    f"Segment {idx} download failed after {retries} attempts: URL={seg_url} Error={e}"
                )


def download_and_merge(
    m3u8_url: str,
    output_path: str,
    concurrency: int = 5,
    live_duration: int = None,
    retries: int = 3
):
    start = time.time()
    try:
        resp = session.get(m3u8_url); resp.raise_for_status()
    except Exception as e:
        raise DownloadError(f"Failed to fetch playlist: URL={m3u8_url} Error={e}")

    base = m3u8_url.rsplit('/', 1)[0] + '/'
    lines = resp.text.splitlines()
    lines, base = parse_variant_playlist(resp.text, base)

    seen, segments = set(), []
    def fetch():
        pl = session.get(m3u8_url); pl.raise_for_status()
        curr_lines = pl.text.splitlines()
        _, curr_base = parse_variant_playlist(pl.text, base)
        return curr_base, [l.strip() for l in curr_lines if l and not l.startswith('#')]

    if live_duration:
        logging.info(f"Live mode: capturing for {live_duration}s")
        while time.time() - start < live_duration:
            base, segs = fetch()
            for s in segs:
                full = urljoin(base, s)
                if full not in seen:
                    seen.add(full)
                    segments.append(full)
            time.sleep(1)
    else:
        segments = [urljoin(base, l.strip()) for l in lines if l and not l.startswith('#')]

    if not segments:
        raise DownloadError("No segments found.")

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    logging.info(f"Downloading {len(segments)} segments to {output_path}")

    results = {}
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {
            ex.submit(download_segment, i, seg_url, retries): i
            for i, seg_url in enumerate(segments, 1)
        }
        for f in tqdm(as_completed(futures), total=len(futures), desc="Segments"):
            try:
                idx, data = f.result()
                results[idx] = data
            except DownloadError as e:
                logging.error(e)

    missing = set(range(1, len(segments) + 1)) - set(results.keys())
    if missing:
        raise DownloadError(f"Missing {len(missing)} segments: indexes {sorted(missing)}")

    with open(output_path, 'wb') as fw:
        for i in range(1, len(segments) + 1):
            fw.write(results[i])
    logging.info("Merge complete.")


def get_media_duration(path):
    """Get media duration in seconds via ffprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json', path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        info = json.loads(res.stdout)
        return float(info['format']['duration'])
    except Exception:
        return None


def convert_ts_to_mp4(ts_path, mp4_path):
    """Convert TS container to MP4 with progress bar."""
    duration = get_media_duration(ts_path)
    cmd = [
        'ffmpeg', '-i', ts_path,
        '-c', 'copy', mp4_path,
        '-progress', 'pipe:1', '-nostats'
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if duration:
        pbar = tqdm(total=int(duration), unit='sec', desc='Converting')
        for line in proc.stdout:
            if line.startswith('out_time_ms='):
                out_ms = int(line.strip().split('=')[1])
                seconds = out_ms / 1e6
                pbar.n = int(seconds)
                pbar.refresh()
        proc.wait()
        pbar.close()
    else:
        proc.wait()


def main():
    parser = argparse.ArgumentParser(
        description="Download HLS (.m3u8) and merge segments"
    )
    parser.add_argument('url', nargs='?', help='Page URL or .m3u8 link')
    parser.add_argument('--output', '-o', default='output.ts', help='Output filename')
    parser.add_argument('--concurrency', type=int, default=8, help='Concurrent downloads')
    parser.add_argument('--live-duration', type=int, help='Live capture duration (s)')
    parser.add_argument('--retries', type=int, default=3, help='Retry attempts for segment download')
    parser.add_argument('--no-convert', action='store_true', help='Skip TS→MP4 conversion')
    parser.add_argument('--verbose', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    lvl = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(format='[%(levelname)s] %(message)s', level=lvl)

    default_out = args.output
    user_out = input(
        f"請輸入輸出路徑（含檔名），直接 Enter 使用預設 '{default_out}'(例如:D:\\video.ts): "
    ).strip()
    if user_out:
        args.output = user_out

    try:
        url = args.url or input('Enter page URL or .m3u8 link: ').strip()
        m3u8 = url if url.lower().endswith('.m3u8') else get_m3u8_via_perflog(url)
        download_and_merge(
            m3u8, args.output, args.concurrency, args.live_duration, args.retries
        )

        if not args.no_convert and args.output.lower().endswith('.ts'):
            mp4_path = os.path.splitext(args.output)[0] + '.mp4'
            try:
                convert_ts_to_mp4(args.output, mp4_path)
                logging.info(f"Converted to MP4: {mp4_path}")
            except Exception as e:
                logging.error(f"Failed to convert to MP4: {e}")

    except DownloadError as e:
        logging.error(e)
        sys.exit(1)

if __name__ == '__main__':
    main()
