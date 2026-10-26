#!/usr/bin/env python3
"""
Сборщик бесплатных IPTV-каналов из открытых источников.

Источники по умолчанию: проект iptv-org (https://github.com/iptv-org/iptv) —
публичные плейлисты каналов, которые вещают в открытом доступе.

Примеры:
    python iptv_collector.py                      # российские каналы по категориям
    python iptv_collector.py --check              # то же, но только рабочие
    python iptv_collector.py --country ru ua --check
    python iptv_collector.py --category news movies --output news_movies.m3u
    python iptv_collector.py --source https://example.com/list.m3u --check --workers 50
    python iptv_collector.py --search "euronews" --check

Зависимости: pip install requests
"""

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import requests

IPTV_ORG_BASE = "https://iptv-org.github.io/iptv"
DEFAULT_SOURCES = [f"{IPTV_ORG_BASE}/countries/ru.m3u"]  # только российские каналы
USER_AGENT = "Mozilla/5.0 (compatible; iptv-collector/1.0)"

ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


@dataclass
class Channel:
    name: str
    url: str
    attrs: dict = field(default_factory=dict)

    @property
    def group(self) -> str:
        return self.attrs.get("group-title", "")

    def to_m3u(self) -> str:
        attrs = " ".join(f'{k}="{v}"' for k, v in self.attrs.items())
        return f"#EXTINF:-1 {attrs},{self.name}\n{self.url}\n"


def fetch_text(url: str, timeout: int = 30) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    return resp.text


def parse_m3u(text: str) -> list[Channel]:
    channels: list[Channel] = []
    current: Channel | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            head, _, name = line.partition(",")
            attrs = dict(ATTR_RE.findall(head))
            current = Channel(name=name.strip() or attrs.get("tvg-name", "Unknown"),
                              url="", attrs=attrs)
        elif line.startswith("#"):
            continue
        elif current is not None:
            current.url = line
            channels.append(current)
            current = None
    return channels


def build_sources(args) -> list[str]:
    sources = list(args.source) if args.source else []
    for c in args.country or []:
        sources.append(f"{IPTV_ORG_BASE}/countries/{c.lower()}.m3u")
    for c in args.category or []:
        sources.append(f"{IPTV_ORG_BASE}/categories/{c.lower()}.m3u")
    for lang in args.language or []:
        sources.append(f"{IPTV_ORG_BASE}/languages/{lang.lower()}.m3u")
    return sources or DEFAULT_SOURCES


def check_channel(ch: Channel, timeout: int) -> bool:
    """Лёгкая проверка: отвечает ли сервер и похож ли ответ на поток/плейлист."""
    headers = {"User-Agent": USER_AGENT}
    try:
        with requests.get(ch.url, headers=headers, timeout=timeout,
                          stream=True, allow_redirects=True) as r:
            if r.status_code >= 400:
                return False
            chunk = next(r.iter_content(chunk_size=1024), b"")
            return len(chunk) > 0
    except requests.RequestException:
        return False


def filter_alive(channels: list[Channel], workers: int, timeout: int) -> list[Channel]:
    alive: list[Channel] = []
    total = len(channels)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_channel, ch, timeout): ch for ch in channels}
        for fut in as_completed(futures):
            done += 1
            if fut.result():
                alive.append(futures[fut])
            if done % 100 == 0 or done == total:
                print(f"  проверено {done}/{total}, рабочих: {len(alive)}", end="\r")
    print()
    # сохраняем исходный порядок
    order = {id(ch): i for i, ch in enumerate(channels)}
    alive.sort(key=lambda c: order[id(c)])
    return alive


def deduplicate(channels: list[Channel]) -> list[Channel]:
    seen: set[str] = set()
    result = []
    for ch in channels:
        key = ch.url.split("?")[0].rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            result.append(ch)
    return result


CATEGORY_RU = {
    "News": "Новости", "Movies": "Кино", "Series": "Сериалы", "Entertainment": "Развлекательные",
    "Music": "Музыка", "Sports": "Спорт", "Kids": "Детские", "Animation": "Мультфильмы",
    "Documentary": "Документальные", "General": "Общие", "Education": "Образование",
    "Comedy": "Комедия", "Culture": "Культура", "Family": "Семейные", "Lifestyle": "Лайфстайл",
    "Religious": "Религия", "Science": "Наука", "Travel": "Путешествия", "Weather": "Погода",
    "Business": "Бизнес", "Cooking": "Кулинария", "Auto": "Авто", "Outdoor": "Природа",
    "Relax": "Релакс", "Classic": "Классика", "Legislative": "Парламентские",
    "Public": "Общественные", "Shop": "Телемагазины", "Undefined": "Без категории",
}


def assign_category(ch: Channel) -> None:
    """Выбираем одну категорию из group-title (в iptv-org их может быть несколько через ';').
    Если среди них есть Public, канал попадает в «Общественные», иначе берётся первая."""
    cats = [c.strip() for c in ch.group.split(";") if c.strip()]
    if "Public" in cats:
        first = "Public"
    else:
        first = cats[0] if cats else "Undefined"
    ch.attrs["group-title"] = CATEGORY_RU.get(first, first)


def sort_by_category(channels: list[Channel]) -> list[Channel]:
    for ch in channels:
        assign_category(ch)
    last = CATEGORY_RU["Undefined"]
    return sorted(channels, key=lambda c: (c.group == last, c.group.lower(), c.name.lower()))


def save_m3u(channels: list[Channel], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for ch in channels:
            f.write(ch.to_m3u())


def main() -> int:
    p = argparse.ArgumentParser(description="Сбор бесплатных IPTV-каналов из открытых M3U-источников")
    p.add_argument("--source", nargs="*", help="свои URL M3U-плейлистов")
    p.add_argument("--country", nargs="*", help="коды стран iptv-org (ru, ua, us, de ...)")
    p.add_argument("--category", nargs="*", help="категории iptv-org (news, movies, sports, kids ...)")
    p.add_argument("--language", nargs="*", help="коды языков iptv-org (rus, eng ...)")
    p.add_argument("--search", help="оставить только каналы, в названии/группе которых есть эта подстрока")
    p.add_argument("--check", action="store_true", help="проверить доступность потоков")
    p.add_argument("--workers", type=int, default=30, help="потоков для проверки (по умолчанию 30)")
    p.add_argument("--timeout", type=int, default=8, help="таймаут проверки, сек (по умолчанию 8)")
    p.add_argument("--output", default="channels.m3u", help="выходной файл (по умолчанию channels.m3u)")
    args = p.parse_args()

    all_channels: list[Channel] = []
    for url in build_sources(args):
        print(f"Загрузка: {url}")
        try:
            chs = parse_m3u(fetch_text(url))
        except requests.RequestException as e:
            print(f"  ошибка: {e}", file=sys.stderr)
            continue
        print(f"  найдено каналов: {len(chs)}")
        all_channels.extend(chs)

    if not all_channels:
        print("Каналы не найдены.", file=sys.stderr)
        return 1

    all_channels = deduplicate(all_channels)
    print(f"После удаления дубликатов: {len(all_channels)}")

    if args.search:
        q = args.search.lower()
        all_channels = [c for c in all_channels if q in c.name.lower() or q in c.group.lower()]
        print(f"После фильтра '{args.search}': {len(all_channels)}")

    if args.check and all_channels:
        print("Проверка доступности потоков...")
        all_channels = filter_alive(all_channels, args.workers, args.timeout)
        print(f"Рабочих каналов: {len(all_channels)}")

    all_channels = sort_by_category(all_channels)

    save_m3u(all_channels, args.output)
    print(f"Сохранено {len(all_channels)} каналов в {args.output}")
    counts: dict[str, int] = {}
    for ch in all_channels:
        counts[ch.group] = counts.get(ch.group, 0) + 1
    for group, n in counts.items():
        print(f"  {group}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
