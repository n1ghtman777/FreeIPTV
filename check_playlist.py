#!/usr/bin/env python3
"""
Проверка M3U-плейлиста: оставляет только рабочие потоки.

Примеры:
    python check_playlist.py channels.m3u
    python check_playlist.py channels.m3u --output alive.m3u --dead dead.txt
    python check_playlist.py channels.m3u --workers 80 --timeout 10 --retries 2

Лежит рядом с iptv_collector.py (использует его парсер).
Зависимости: pip install requests
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from iptv_collector import USER_AGENT, Channel, parse_m3u, save_m3u


def is_alive(url: str, timeout: int, retries: int) -> bool:
    """Поток считается рабочим, если сервер отвечает без ошибки и отдаёт данные.
    Для HLS (.m3u8) дополнительно проверяется, что ответ начинается с #EXTM3U,
    а HTML-страницы (заглушки, ошибки, редиректы на сайт) отбрасываются."""
    headers = {"User-Agent": USER_AGENT}
    for _ in range(retries + 1):
        try:
            with requests.get(url, headers=headers, timeout=timeout,
                              stream=True, allow_redirects=True) as r:
                if r.status_code >= 400:
                    continue
                ctype = r.headers.get("Content-Type", "").lower()
                if "text/html" in ctype:
                    continue
                chunk = next(r.iter_content(chunk_size=4096), b"")
                if not chunk:
                    continue
                is_hls = ".m3u8" in url.lower().split("?")[0] or "mpegurl" in ctype
                if is_hls and not chunk.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"#EXTM3U"):
                    continue
                return True
        except (requests.RequestException, OSError):
            continue
    return False


def check_all(channels: list[Channel], workers: int, timeout: int, retries: int):
    results: dict[int, bool] = {}
    total = len(channels)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(is_alive, ch.url, timeout, retries): i
                   for i, ch in enumerate(channels)}
        for n, fut in enumerate(as_completed(futures), 1):
            results[futures[fut]] = fut.result()
            if n % 50 == 0 or n == total:
                alive = sum(results.values())
                print(f"  проверено {n}/{total}, рабочих: {alive}", end="\r", flush=True)
    print()
    alive = [ch for i, ch in enumerate(channels) if results.get(i)]
    dead = [ch for i, ch in enumerate(channels) if not results.get(i)]
    return alive, dead


def main() -> int:
    p = argparse.ArgumentParser(description="Проверка M3U-плейлиста на рабочие потоки")
    p.add_argument("input", help="входной .m3u файл")
    p.add_argument("--output", help="куда сохранить рабочие (по умолчанию <input>_alive.m3u)")
    p.add_argument("--dead", help="сохранить список нерабочих каналов в этот текстовый файл")
    p.add_argument("--workers", type=int, default=50, help="потоков (по умолчанию 50)")
    p.add_argument("--timeout", type=int, default=8, help="таймаут запроса, сек (по умолчанию 8)")
    p.add_argument("--retries", type=int, default=1, help="повторных попыток (по умолчанию 1)")
    args = p.parse_args()

    with open(args.input, encoding="utf-8") as f:
        channels = parse_m3u(f.read())
    if not channels:
        print("В плейлисте нет каналов.", file=sys.stderr)
        return 1

    print(f"Каналов к проверке: {len(channels)}")
    alive, dead = check_all(channels, args.workers, args.timeout, args.retries)

    out = args.output or args.input.rsplit(".", 1)[0] + "_alive.m3u"
    save_m3u(alive, out)
    print(f"Рабочих: {len(alive)}, нерабочих: {len(dead)} -> {out}")

    if args.dead:
        with open(args.dead, "w", encoding="utf-8") as f:
            for ch in dead:
                f.write(f"{ch.group}\t{ch.name}\t{ch.url}\n")
        print(f"Список нерабочих: {args.dead}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
