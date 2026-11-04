#!/usr/bin/env python3
"""
Rebuild World.m3u from the iptv-org country-grouped index, pruning
channels that are definitively dead.

Each run:
  * pulls the latest country-grouped index (new channels appear here)
  * tests every stream URL
  * drops only CLEARLY dead ones (host gone / DNS fail / 404-410-451)
  * keeps geo-blocked (403) and slow/timeout ones -- they may work from
    your region even if the US-based runner can't reach them
  * writes World.m3u, preserving each entry's country group + logo

Env:
  WORLD_TEST_LIMIT=<n>   test only the first n entries (local debugging)

Standard library only.
"""

import concurrent.futures as cf
import os
import sys
import urllib.error
import urllib.request

SOURCE = "https://iptv-org.github.io/iptv/index.country.m3u"
OUT = "World.m3u"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

HEADER = [
    "# ---------------------------------------------------------",
    "# World Live TV  -  all countries  (auto-updated)",
    "# Source: iptv-org public index (country-grouped).",
    "# Dead hosts (gone / 404 / DNS fail) are pruned each run.",
    "# Geo-blocked channels are kept (may work from your region).",
    "# ---------------------------------------------------------",
]

# hard-dead HTTP codes (resource really gone)
DEAD_CODES = {404, 410, 451, 400}
# substrings in a connection error that mean the host itself is gone
DEAD_NET = (
    "name or service not known", "getaddrinfo", "no address associated",
    "nodename nor servname", "connection refused", "no route to host",
    "name resolution", "certificate verify failed", "unknown url type",
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def parse(text: str):
    """Yield (extinf_line, url) pairs, preserving the original EXTINF."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF"):
            url = ""
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if nxt and not nxt.startswith("#"):
                    url = nxt
                    break
                j += 1
            if url:
                yield line, url
            i = j + 1
        else:
            i += 1


def is_dead(url: str) -> bool:
    """True only when the stream is definitively gone."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Range": "bytes=0-2047"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status in DEAD_CODES
    except urllib.error.HTTPError as e:
        return e.code in DEAD_CODES          # 403/401/5xx -> keep
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e)).lower()
        return any(k in reason for k in DEAD_NET)   # timeout -> keep
    except Exception as e:
        return any(k in str(e).lower() for k in DEAD_NET)


def main() -> int:
    try:
        raw = fetch(SOURCE)
    except Exception as e:
        print(f"ERROR: could not fetch source: {e}", file=sys.stderr)
        return 1

    entries = list(parse(raw))
    if len(entries) < 1000:
        print("Source too small; keeping existing file.", file=sys.stderr)
        return 0

    limit = int(os.environ.get("WORLD_TEST_LIMIT", "0") or "0")
    if limit > 0:
        entries = entries[:limit]
    print(f"entries to test: {len(entries)}")

    kept = []
    dead = 0
    with cf.ThreadPoolExecutor(max_workers=60) as ex:
        flags = ex.map(lambda e: is_dead(e[1]), entries)
        for (extinf, url), bad in zip(entries, flags):
            if bad:
                dead += 1
            else:
                kept.append((extinf, url))

    print(f"kept: {len(kept)}   pruned (dead): {dead}")

    # safety: never nuke the list on a bad run
    if len(kept) < len(entries) * 0.4:
        print("Too many pruned (>60%); keeping existing file.", file=sys.stderr)
        return 0

    out = ["#EXTM3U"] + HEADER
    for extinf, url in kept:
        out.append(extinf)
        out.append(url)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(f"wrote {OUT} with {len(kept)} channels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
