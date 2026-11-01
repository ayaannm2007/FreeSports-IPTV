#!/usr/bin/env python3
"""
Refresh World.m3u from the iptv-org country-grouped index.

iptv-org maintains this list (adds new public channels, drops ones that
go private/DRM), so refreshing it gives new channels and sheds removed
ones automatically. Only a lightweight header is added on top.
"""

import sys
import urllib.request

SOURCE = "https://iptv-org.github.io/iptv/index.country.m3u"
OUT = "World.m3u"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

HEADER = [
    "# ---------------------------------------------------------",
    "# World Live TV  -  all countries  (auto-updated)",
    "# Source: iptv-org public index (country-grouped).",
    "# ---------------------------------------------------------",
]


def main() -> int:
    try:
        req = urllib.request.Request(SOURCE, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"ERROR: could not fetch source: {e}", file=sys.stderr)
        return 1

    lines = text.splitlines()
    if not lines or not lines[0].startswith("#EXTM3U"):
        print("Unexpected source format; keeping existing file.", file=sys.stderr)
        return 0
    if len(lines) < 1000:
        print("Source too small; keeping existing file.", file=sys.stderr)
        return 0

    body = lines[1:]  # drop the original #EXTM3U, we re-add it
    out = ["#EXTM3U"] + HEADER + body
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(f"wrote {OUT} with ~{len(body)} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
