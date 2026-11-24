#!/usr/bin/env python3
"""Check that downloaded files are the originals published on GitHub.

Put this file in the same folder as the files you downloaded and run:

    python3 verify.py

It downloads the SHA256SUMS list that the publisher attached to their GitHub release, then checks
that every downloaded file listed there has exactly the same fingerprint (SHA-256). It needs only
Python 3. Nothing is installed or changed, and the only address it contacts is github.com.

Options:   python3 verify.py [--repo OWNER/REPO] [--tag vX.Y.Z] [FILE ...]
Exit code: 0 = every file matches, 1 = a file differs or is missing, 2 = could not reach GitHub.

Vundu Studio fills in REPO and TAG for you when it builds a release. If you use this file as a
template by hand, replace them below or pass --repo and --tag.
"""
import hashlib
import os
import re
import sys
import urllib.error
import urllib.request

REPO = "OWNER/REPO"
TAG = "v0.0.0"
BASE = "https://github.com"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(repo, tag):
    """The SHA256SUMS text of a GitHub release. Tries the tag as given, then without a leading v."""
    for t in dict.fromkeys([tag, tag[1:] if tag.startswith("v") else tag]):
        url = f"{BASE}/{repo}/releases/download/{t}/SHA256SUMS"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "verify.py"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read(1_000_000).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                sys.exit(f"GitHub answered {e.code} for {url}")
        except OSError as e:
            print(f"Could not reach GitHub: {e}")
            sys.exit(2)
    print(f"GitHub has no release tagged {tag} with a SHA256SUMS file in {repo}.")
    sys.exit(1)


def main(argv):
    repo, tag, files = REPO, TAG, []
    it = iter(argv)
    for a in it:
        if a == "--repo":
            repo = next(it, "")
        elif a == "--tag":
            tag = next(it, "")
        else:
            files.append(a)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or repo == "OWNER/REPO" or not re.fullmatch(r"[\w.+~-]+", tag):
        sys.exit("Set REPO and TAG at the top of this file, or run:  python3 verify.py --repo OWNER/REPO --tag vX.Y.Z")
    published = {}
    for line in fetch(repo, tag).splitlines():
        m = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line.strip())
        if m:
            published[m.group(2)] = m.group(1).lower()
    here = os.path.dirname(os.path.abspath(__file__))
    names = files or [n for n in published if os.path.isfile(os.path.join(here, n))]
    if not names:
        sys.exit("None of the files listed on GitHub were found next to this script. Put the downloaded files in the same folder.")
    bad = 0
    for n in names:
        path = n if os.path.isfile(n) else os.path.join(here, n)
        want = published.get(os.path.basename(n))
        if not os.path.isfile(path):
            print(f"MISSING   {n}")
            bad += 1
        elif want is None:
            print(f"UNKNOWN   {n}  (GitHub does not list this file)")
            bad += 1
        elif sha256(path) == want:
            print(f"OK        {n}")
        else:
            print(f"DIFFERENT {n}  (does NOT match {repo} {tag}. Do not use it.)")
            bad += 1
    print("\nAll files match the originals on GitHub." if not bad else f"\n{bad} problem(s). Do not trust these files.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
