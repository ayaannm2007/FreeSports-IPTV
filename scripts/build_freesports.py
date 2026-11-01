#!/usr/bin/env python3
"""
Rebuild FreeSports.m3u from the public iptv-org "sports" category.

What it does each run:
  * pulls the latest sports category playlist from iptv-org
  * keeps only genuinely FREE / FAST sports brands (ALLOW list below)
  * tests every candidate URL -> drops dead ones (so links stay working)
  * auto-adds any NEW feed of an allowed brand that appears upstream
  * writes a clean, grouped FreeSports.m3u

Only legal free-to-air / FAST public streams. No paid/DRM channels.
Standard library only (runs on a bare GitHub Actions runner).
"""

import concurrent.futures as cf
import re
import sys
import urllib.request

SOURCE = "https://iptv-org.github.io/iptv/categories/sports.m3u"
OUT = "FreeSports.m3u"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# --- genuinely free / FAST sports brands we keep -------------------------
# (lower-case substrings matched against the channel display name)
# Add a brand here and its channels start appearing automatically.
ALLOW = [
    "fifa+", "fifa plus",
    "red bull",
    "bein sports xtra",
    "real madrid",
    "inter tv",
    "nfl channel",
    "stadium",
    "fubo sports",
    "bellator",
    "world poker", "wpt",
    "acc digital",
    "american ninja warrior",
    "dazn women", "dazn ringside", "dazn rise", "dazn combat", "dazn fast",
    "l'equipe", "lequipe",
    "the ocho",
    "fast&fun", "fast & fun",
    "edge sport",
    "fuel tv",
    "motorvision",
    "glory kickboxing",
    "unbeaten",
    "swerve",
    "surf", "surfline",
    "pokergo free", "poker central",
    "tennis channel pickleball",
    "olympic", "olympics",
    "nba tv rewind", "nba tv classic",
    "trt spor",
    "sport tv +",  # free promo rings only
    "sporting news",
]

# --- brands we explicitly refuse even if the name slips past ALLOW -------
DENY = [
    "sky", "premier", "espn+", "bt sport", "tnt sport", "star sports",
    "willow", "fancode", "ten sports", "astro", "supersport pay",
    "canal+", "movistar", "optus", "stan sport", "setanta",
]

# --- nice group names ----------------------------------------------------
def group_for(name: str) -> str:
    n = name.lower()
    if "fifa" in n:
        return "Football (FIFA+)"
    if any(k in n for k in ("real madrid", "inter tv", " cf", " fc", "madrid tv")):
        return "Football Clubs"
    if "bein" in n:
        return "beIN XTRA"
    if any(k in n for k in ("bellator", "mma", "kickbox", "glory", "wrestl", "combat")):
        return "Combat / MMA"
    if any(k in n for k in ("poker", "wpt")):
        return "Poker"
    if "dazn" in n:
        return "DAZN Free"
    if any(k in n for k in ("red bull", "surf", "moto", "edge sport",
                            "the ocho", "extreme", "fuel tv", "ninja")):
        return "Action / Extreme"
    if any(k in n for k in ("nfl", "nba", "mlb", "nhl", "acc ", "fubo",
                            "stadium", "unbeaten")):
        return "US Sports"
    return "Sports"


ATTR = re.compile(r'(\w[\w-]*)="([^"]*)"')


def extinf_name(line: str) -> str:
    """Display name = text after the first comma that is outside quotes."""
    in_q = False
    for idx, ch in enumerate(line):
        if ch == '"':
            in_q = not in_q
        elif ch == "," and not in_q:
            return line[idx + 1:].strip()
    return "Unknown"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(playlist: str):
    """Yield (name, attrs_dict, url) for each entry."""
    lines = playlist.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            attrs = dict(ATTR.findall(line))
            name = extinf_name(line)
            url = ""
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if nxt and not nxt.startswith("#"):
                    url = nxt
                    break
                j += 1
            if url:
                yield name, attrs, url
            i = j + 1
        else:
            i += 1


def allowed(name: str) -> bool:
    n = name.lower()
    if any(d in n for d in DENY):
        return False
    return any(a in n for a in ALLOW)


def alive(url: str) -> bool:
    """True if the URL serves a real HLS manifest."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Range": "bytes=0-4095"})
        with urllib.request.urlopen(req, timeout=12) as r:
            if r.status not in (200, 206):
                return False
            head = r.read(4096).decode("utf-8", "replace")
            return "#EXTM3U" in head or ".m3u8" in head or ".ts" in head
    except Exception:
        return False


def main() -> int:
    try:
        raw = fetch(SOURCE)
    except Exception as e:
        print(f"ERROR: could not fetch source: {e}", file=sys.stderr)
        return 1

    # collect allowed candidates, dedupe by URL
    seen = set()
    candidates = []
    for name, attrs, url in parse(raw):
        if url in seen or not allowed(name):
            continue
        seen.add(url)
        candidates.append((name, attrs, url))

    print(f"candidates after allow-filter: {len(candidates)}")

    # reachability test in parallel
    live = []
    with cf.ThreadPoolExecutor(max_workers=24) as ex:
        results = ex.map(lambda c: (c, alive(c[2])), candidates)
        for (name, attrs, url), ok in results:
            if ok:
                live.append((name, attrs, url))
            else:
                print(f"  dead -> {name}")

    # sort by group then name
    live.sort(key=lambda c: (group_for(c[0]), c[0].lower()))
    print(f"live channels: {len(live)}")

    if len(live) < 10:
        print("Too few live channels; keeping existing file.", file=sys.stderr)
        return 0  # don't overwrite a good file with a bad run

    out = []
    out.append("#EXTM3U")
    out.append("# ---------------------------------------------------------")
    out.append("# Legal FREE Sports & Live playlist  (auto-updated)")
    out.append("# Source: iptv-org public sports category, free/FAST only.")
    out.append("# Dead links are removed and new free feeds added each run.")
    out.append("# ---------------------------------------------------------")
    for name, attrs, url in live:
        tvg_id = attrs.get("tvg-id", "")
        logo = attrs.get("tvg-logo", "")
        grp = group_for(name)
        out.append(
            f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" '
            f'group-title="{grp}",{name}')
        out.append(url)

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(f"wrote {OUT} with {len(live)} channels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
