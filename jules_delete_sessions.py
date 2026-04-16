#!/usr/bin/env python3
"""Delete Jules sessions via the Jules REST API.

Requires --source or JULES_SOURCE env var to scope deletion to a repo.
Use --all to delete sessions across all repos.

Usage:
    export JULES_API_KEY="your_api_key"
    export JULES_SOURCE="sources/github/OWNER/REPO"

    # Delete sessions for a specific repo only (safe default):
    python3 scripts/jules_delete_sessions.py --source sources/github/OWNER/REPO

    # Delete ALL sessions across all repos (destructive!):
    python3 scripts/jules_delete_sessions.py --all

    # Delete only already-archived sessions:
    python3 scripts/jules_delete_sessions.py --source sources/github/OWNER/REPO --archived

    # Archive sessions before deleting (two-step, for audit trail):
    python3 scripts/jules_delete_sessions.py --source sources/github/OWNER/REPO --archive-first

    # Dry run (list sessions without deleting):
    python3 scripts/jules_delete_sessions.py --source sources/github/OWNER/REPO --dry-run

    # Or pass the key directly:
    python3 scripts/jules_delete_sessions.py --api-key YOUR_KEY --source sources/github/OWNER/REPO

Get your API key at: https://jules.google.com/settings/api
API reference:     https://jules.google/docs/api/reference/overview/
"""

import argparse
import os
import sys
import urllib.error
import urllib.request
import json

BASE_URL = "https://jules.googleapis.com/v1alpha"


def api_request(api_key: str, method: str, path: str, params: dict = None, body: dict = None):
    url = BASE_URL + path
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("x-goog-api-key", api_key)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def fetch_all_sessions(api_key: str) -> list:
    sessions = []
    page_token = None
    while True:
        params = {"pageSize": "50"}
        if page_token:
            params["pageToken"] = page_token
        status, body = api_request(api_key, "GET", "/sessions", params)
        if status != 200:
            print(f"ERROR: Failed to list sessions (HTTP {status}): {body[:200]}", file=sys.stderr)
            sys.exit(1)
        data = json.loads(body)
        page = data.get("sessions", [])
        sessions.extend(page)
        print(f"  Fetched {len(page)} sessions (total: {len(sessions)})")
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return sessions


def archive_session(api_key: str, sid: str) -> tuple[int, bytes]:
    return api_request(api_key, "POST", f"/sessions/{sid}:archive", body={})


def main():
    parser = argparse.ArgumentParser(description="Delete Jules sessions")
    parser.add_argument("--api-key", default=os.environ.get("JULES_API_KEY"), help="Jules API key (or set JULES_API_KEY env var)")
    parser.add_argument("--source", default=os.environ.get("JULES_SOURCE"), help="Filter by source repo, e.g. sources/github/OWNER/REPO (or set JULES_SOURCE env var)")
    parser.add_argument("--all", dest="all_sources", action="store_true", help="Delete sessions from ALL repos (dangerous!)")
    parser.add_argument("--archived", action="store_true", help="Only delete sessions already in ARCHIVED state")
    parser.add_argument("--archive-first", action="store_true", help="Archive each session before deleting it")
    parser.add_argument("--dry-run", action="store_true", help="List sessions without deleting")
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: No API key provided. Set JULES_API_KEY or use --api-key.", file=sys.stderr)
        sys.exit(1)

    if not args.all_sources and not args.source:
        print("ERROR: Provide --source sources/github/OWNER/REPO, set JULES_SOURCE, or use --all.", file=sys.stderr)
        sys.exit(1)

    print("Fetching all sessions...")
    all_sessions = fetch_all_sessions(args.api_key)

    if args.all_sources:
        sessions = all_sessions
        print(f"\nScope: ALL repos ({len(sessions)} sessions)")
    else:
        sessions = [s for s in all_sessions if s.get("sourceContext", {}).get("source") == args.source]
        print(f"\nScope: {args.source}")
        print(f"Matching sessions: {len(sessions)} of {len(all_sessions)} total")

    if args.archived:
        before = len(sessions)
        sessions = [s for s in sessions if s.get("state") == "ARCHIVED"]
        print(f"Filtering to ARCHIVED state: {len(sessions)} of {before}")

    if not sessions:
        print("Nothing to delete.")
        return

    if args.dry_run:
        print("\n[DRY RUN] Sessions that would be deleted:")
        for s in sessions:
            sid = s["name"].split("/")[-1]
            source = s.get("sourceContext", {}).get("source", "unknown")
            print(f"  {sid} | {s.get('state','?')} | {source} | {s.get('title','?')[:50]}")
        return

    print("\nDeleting...")
    deleted = 0
    failed = 0
    for s in sessions:
        sid = s["name"].split("/")[-1]
        title = s.get("title", "?")[:50]

        if args.archive_first and s.get("state") != "ARCHIVED":
            status, body = archive_session(args.api_key, sid)
            if status in (200, 204):
                print(f"  ARCHIVED {sid} | {title}")
            else:
                print(f"  ARCHIVE FAILED {sid} | {title} | HTTP {status} | {body[:100]}")
                failed += 1
                continue

        status, body = api_request(args.api_key, "DELETE", f"/sessions/{sid}")
        if status in (200, 204):
            print(f"  DELETED {sid} | {title}")
            deleted += 1
        else:
            print(f"  FAILED  {sid} | {title} | HTTP {status} | {body[:100]}")
            failed += 1

    print(f"\nDone. Deleted: {deleted}  Failed: {failed}")


if __name__ == "__main__":
    main()
