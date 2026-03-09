#!/usr/bin/env python3
"""
gh-releases: Track GitHub releases across multiple repos.
Pure Python, zero dependencies. Uses GitHub API (no auth needed for public repos).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

DATA_DIR = Path(os.environ.get("GH_RELEASES_DIR", Path.home() / ".gh-releases"))
REPOS_FILE = DATA_DIR / "repos.json"
CACHE_DIR = DATA_DIR / "cache"

def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def load_repos() -> dict:
    if REPOS_FILE.exists():
        return json.loads(REPOS_FILE.read_text())
    return {"repos": [], "last_check": None}

def save_repos(data: dict):
    REPOS_FILE.write_text(json.dumps(data, indent=2))

def gh_api(path: str, token: str = None) -> dict:
    url = f"https://api.github.com{path}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "gh-releases/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def fetch_releases(owner_repo: str, token: str = None, limit: int = 5) -> list:
    try:
        data = gh_api(f"/repos/{owner_repo}/releases?per_page={limit}", token)
        return [{
            "tag": r["tag_name"],
            "name": r.get("name") or r["tag_name"],
            "published": r["published_at"],
            "prerelease": r["prerelease"],
            "url": r["html_url"],
            "body": (r.get("body") or "")[:500],
        } for r in data]
    except HTTPError as e:
        if e.code == 404:
            # Try tags instead (some repos don't use releases)
            return fetch_tags(owner_repo, token, limit)
        raise
    except Exception:
        return []

def fetch_tags(owner_repo: str, token: str = None, limit: int = 5) -> list:
    try:
        data = gh_api(f"/repos/{owner_repo}/tags?per_page={limit}", token)
        return [{
            "tag": t["name"],
            "name": t["name"],
            "published": None,
            "prerelease": False,
            "url": f"https://github.com/{owner_repo}/releases/tag/{t['name']}",
            "body": "",
        } for t in data]
    except Exception:
        return []

def cmd_add(args):
    ensure_dirs()
    data = load_repos()
    repo = args.repo.strip("/")
    if "/" not in repo:
        print(f"Error: use owner/repo format (e.g., 'vercel/next.js')")
        return
    
    for r in data["repos"]:
        if r["repo"] == repo:
            print(f"Already tracking: {repo}")
            return
    
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    print(f"Fetching latest release for {repo}...")
    releases = fetch_releases(repo, token, 1)
    
    entry = {
        "repo": repo,
        "added": datetime.now(timezone.utc).isoformat(),
        "last_seen_tag": releases[0]["tag"] if releases else None,
        "last_check": datetime.now(timezone.utc).isoformat(),
    }
    data["repos"].append(entry)
    save_repos(data)
    
    if releases:
        r = releases[0]
        print(f"✅ Tracking {repo} (latest: {r['tag']})")
    else:
        print(f"✅ Tracking {repo} (no releases found yet)")

def cmd_remove(args):
    ensure_dirs()
    data = load_repos()
    before = len(data["repos"])
    data["repos"] = [r for r in data["repos"] if r["repo"] != args.repo]
    if len(data["repos"]) < before:
        save_repos(data)
        print(f"✅ Removed: {args.repo}")
    else:
        print(f"Not found: {args.repo}")

def cmd_list(args):
    ensure_dirs()
    data = load_repos()
    if not data["repos"]:
        print("No repos tracked. Use 'add owner/repo' to start.")
        return
    
    fmt = getattr(args, 'format', 'text')
    if fmt == 'json':
        print(json.dumps(data["repos"], indent=2))
        return
    
    for i, r in enumerate(data["repos"], 1):
        tag = r.get("last_seen_tag") or "unknown"
        print(f"{i}. {r['repo']} — latest: {tag}")

def cmd_check(args):
    ensure_dirs()
    data = load_repos()
    if not data["repos"]:
        print("No repos tracked.")
        return
    
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    new_releases = []
    errors = []
    
    repos_to_check = data["repos"]
    if args.repo:
        repos_to_check = [r for r in data["repos"] if r["repo"] == args.repo]
    
    for entry in repos_to_check:
        repo = entry["repo"]
        try:
            releases = fetch_releases(repo, token, 5)
            entry["last_check"] = datetime.now(timezone.utc).isoformat()
            
            if not releases:
                continue
            
            old_tag = entry.get("last_seen_tag")
            latest = releases[0]
            
            if old_tag and latest["tag"] != old_tag:
                # Find all new releases since last seen
                new = []
                for r in releases:
                    if r["tag"] == old_tag:
                        break
                    new.append(r)
                new_releases.extend([(repo, r) for r in new])
                entry["last_seen_tag"] = latest["tag"]
            elif not old_tag:
                entry["last_seen_tag"] = latest["tag"]
                
        except Exception as e:
            errors.append((repo, str(e)))
        
        time.sleep(0.5)  # Rate limit courtesy
    
    save_repos(data)
    
    fmt = getattr(args, 'format', 'text')
    if fmt == 'json':
        result = {
            "new_releases": [{"repo": repo, **rel} for repo, rel in new_releases],
            "errors": [{"repo": r, "error": e} for r, e in errors],
        }
        print(json.dumps(result, indent=2))
        return
    
    if new_releases:
        print(f"🆕 {len(new_releases)} new release(s):\n")
        for repo, rel in new_releases:
            pre = " ⚠️ pre-release" if rel["prerelease"] else ""
            pub = ""
            if rel["published"]:
                pub = f" ({rel['published'][:10]})"
            print(f"  📦 {repo} → {rel['tag']}{pre}{pub}")
            if rel["body"]:
                # First meaningful line of body
                for line in rel["body"].split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        print(f"     {line[:120]}")
                        break
            print(f"     {rel['url']}")
            print()
    else:
        print("✅ No new releases.")
    
    if errors:
        for repo, err in errors:
            print(f"❌ {repo}: {err}")

def cmd_releases(args):
    """Show recent releases for a specific repo."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    n = args.limit or 5
    releases = fetch_releases(args.repo, token, n)
    
    if not releases:
        print(f"No releases found for {args.repo}")
        return
    
    fmt = getattr(args, 'format', 'text')
    if fmt == 'json':
        print(json.dumps(releases, indent=2))
        return
    
    print(f"📦 Recent releases for {args.repo}:\n")
    for r in releases:
        pre = " ⚠️ pre" if r["prerelease"] else ""
        pub = f" ({r['published'][:10]})" if r["published"] else ""
        print(f"  {r['tag']}{pre}{pub}")
        if r["body"]:
            lines = [l.strip() for l in r["body"].split("\n") if l.strip() and not l.startswith("#")]
            for line in lines[:2]:
                print(f"    {line[:120]}")
        print(f"    {r['url']}")
        print()

def main():
    parser = argparse.ArgumentParser(prog="gh-releases", description="Track GitHub releases")
    sub = parser.add_subparsers(dest="command", required=True)
    
    p = sub.add_parser("add", help="Track a repo")
    p.add_argument("repo", help="owner/repo")
    p.set_defaults(func=cmd_add)
    
    p = sub.add_parser("remove", help="Stop tracking")
    p.add_argument("repo")
    p.set_defaults(func=cmd_remove)
    
    p = sub.add_parser("list", help="List tracked repos")
    p.add_argument("--format", "-f", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_list)
    
    p = sub.add_parser("check", help="Check for new releases")
    p.add_argument("repo", nargs="?")
    p.add_argument("--format", "-f", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_check)
    
    p = sub.add_parser("releases", help="Show releases for a repo")
    p.add_argument("repo")
    p.add_argument("--limit", "-n", type=int, default=5)
    p.add_argument("--format", "-f", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_releases)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
