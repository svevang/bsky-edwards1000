#!/usr/bin/env python3
"""Download all posts by a Bluesky user carrying a given hashtag.

Usage: python3 bsky_tag_dl.py <handle-or-did> <tag-without-#> [outfile.json]
s0_download.py uses fetch() to write entries/ instead.

Walks the user's public repo (com.atproto.repo.listRecords) and filters
locally, so it doesn't depend on the search index being complete.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

UA = "bsky-tag-downloader/1.0"


def get(url, ua=UA, **params):
    """GET url?params as JSON, retrying with backoff (honouring 429 Retry-After); None on 404."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == 4:
                raise
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 0) or 0) or 15 * (attempt + 1)
                print(f"  429, sleeping {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"  retry ({e})", file=sys.stderr)
        except Exception as e:
            if attempt == 4:
                raise
            print(f"  retry ({e})", file=sys.stderr)
        time.sleep(2 * (attempt + 1))


def resolve(actor):
    """handle/DID -> (did, pds_endpoint)"""
    if not actor.startswith("did:"):
        actor = get("https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
                    handle=actor)["did"]
    if actor.startswith("did:plc:"):
        doc = get(f"https://plc.directory/{actor}")
    else:  # did:web:example.com
        host = actor[len("did:web:"):]
        doc = get(f"https://{urllib.parse.unquote(host)}/.well-known/did.json")
    pds = next(s["serviceEndpoint"] for s in doc["service"]
               if s["type"] == "AtprotoPersonalDataServer")
    return actor, pds.rstrip("/")


def tags_of(record):
    """Hashtags from facets plus any #tag literals in the text."""
    out = set()
    for facet in record.get("facets") or []:
        for f in facet.get("features") or []:
            if f.get("$type") == "app.bsky.richtext.facet#tag":
                out.add(f["tag"])
    out.update(record.get("tags") or [])
    for word in record.get("text", "").split():
        if word.startswith("#") and len(word) > 1:
            out.add(word[1:].strip(".,!?;:)\"'"))
    return {t.lower() for t in out}


def fetch(actor, tag):
    """All of actor's posts carrying #tag, oldest first."""
    tag = tag.lstrip("#").lower()
    did, pds = resolve(actor)
    print(f"{actor} -> {did} @ {pds}", file=sys.stderr)

    matches, cursor, scanned = [], None, 0
    while True:
        page = get(f"{pds}/xrpc/com.atproto.repo.listRecords",
                   repo=did, collection="app.bsky.feed.post", limit=100,
                   **({"cursor": cursor} if cursor else {}))
        for rec in page.get("records", []):
            scanned += 1
            if tag in tags_of(rec["value"]):
                rkey = rec["uri"].rsplit("/", 1)[-1]
                matches.append({
                    "uri": rec["uri"],
                    "cid": rec["cid"],
                    "url": f"https://bsky.app/profile/{did}/post/{rkey}",
                    "createdAt": rec["value"].get("createdAt"),
                    "text": rec["value"].get("text", ""),
                    "record": rec["value"],
                })
        cursor = page.get("cursor")
        print(f"  scanned {scanned}, matched {len(matches)}", file=sys.stderr)
        if not cursor:
            break
        time.sleep(0.2)

    matches.sort(key=lambda m: m["createdAt"] or "")
    return matches


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    actor, tag = sys.argv[1], sys.argv[2].lstrip("#").lower()
    outfile = sys.argv[3] if len(sys.argv) > 3 else f"{tag}.json"
    matches = fetch(actor, tag)
    with open(outfile, "w") as f:
        json.dump(matches, f, indent=2, ensure_ascii=False)
    print(f"\n{len(matches)} posts with #{tag} -> {outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
