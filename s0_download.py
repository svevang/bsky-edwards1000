#!/usr/bin/env python3
"""Stage 0: download the tagged posts -> entries/<rkey>/post.yaml

Usage: s0_download.py <handle-or-did> <tag-without-#>

post.yaml is only rewritten when the post changed. An entry whose post is missing from the
download is marked deleted with deleted.yaml (and skipped by every stage); if it comes back,
the marker is removed. A download with no posts at all is refused rather than deleting everything.
"""
import sys
import entries
import stage
from bsky_tag_dl import fetch, rkey


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    posts = fetch(sys.argv[1], sys.argv[2])
    if not posts:
        sys.exit("download returned no posts; not marking any entries deleted")
    seen, written, back = set(), 0, 0
    for p in posts:
        rk = rkey(p["uri"])
        seen.add(rk)
        if entries.read(rk, "post") != p:
            entries.write(rk, "post", p)
            written += 1
        if entries.deleted(rk):
            entries.set_deleted(rk, False)
            back += 1
    gone = [rk for rk in entries.list_entries() if rk not in seen and not entries.deleted(rk)]
    for rk in gone:
        entries.set_deleted(rk, True)
    print(f"{len(posts)} posts: {written} new/changed, {back} back from deleted, {len(gone)} newly deleted",
          file=sys.stderr)
    if gone:
        print(f"  deleted: {gone}", file=sys.stderr)
    stage.finish("download")


if __name__ == "__main__":
    main()
