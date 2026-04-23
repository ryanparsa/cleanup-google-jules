#!/usr/bin/env python3
"""Clean up Jules sessions via the Jules REST API.

Supports archiving, deleting, and purging (archive-then-delete) sessions,
scoped to a specific repo or across all repos.

NOTE: The Jules v1alpha API exposes Sessions, Activities, and Sources only.
      There are currently no public API endpoints for "Knowledge" or "Memory"
      features visible in the Jules web UI.  When those endpoints are
      published, this script will be updated to support them.

Usage:
    export JULES_API_KEY="your_api_key"
    export JULES_SOURCE="sources/github/OWNER/REPO"

    # Delete sessions for a specific repo (safe default):
    python3 jules_delete_sessions.py --source sources/github/OWNER/REPO

    # Delete ALL sessions across all repos (destructive!):
    python3 jules_delete_sessions.py --all

    # Delete only already-archived sessions:
    python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --archived

    # Archive sessions before deleting (two-step, for audit trail):
    python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --archive-first

    # Archive sessions WITHOUT deleting them:
    python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --archive-only

    # Filter to a specific session state, e.g. only COMPLETED sessions:
    python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --state COMPLETED

    # Purge: archive every session then delete all (full cleanup, one command):
    python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --purge

    # Dry run (list sessions without changing anything):
    python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --dry-run

    # Or pass the key directly:
    python3 jules_delete_sessions.py --api-key YOUR_KEY --source sources/github/OWNER/REPO

Get your API key at: https://jules.google.com/settings/api
API reference:      https://jules.google/docs/api/reference/overview/

Session states: QUEUED, PLANNING, AWAITING_PLAN_APPROVAL, AWAITING_USER_FEEDBACK,
                IN_PROGRESS, PAUSED, COMPLETED, FAILED, ARCHIVED
"""

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import json

BASE_URL = "https://jules.googleapis.com/v1alpha"

ALL_STATES = {
    "QUEUED",
    "PLANNING",
    "AWAITING_PLAN_APPROVAL",
    "AWAITING_USER_FEEDBACK",
    "IN_PROGRESS",
    "PAUSED",
    "COMPLETED",
    "FAILED",
    "ARCHIVED",
}


def api_request(api_key: str, method: str, path: str, params: dict = None, body: dict = None):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
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
        params = {"pageSize": "100"}
        if page_token:
            params["pageToken"] = page_token
        status, body = api_request(api_key, "GET", "/sessions", params)
        if status != 200:
            print(f"ERROR: Failed to list sessions (HTTP {status}): {body[:200]}", file=sys.stderr)
            sys.exit(1)
        data = json.loads(body)
        page = data.get("sessions", [])
        sessions.extend(page)
        print(f"  Fetched {len(page)} sessions (total so far: {len(sessions)})")
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return sessions


def archive_session(api_key: str, sid: str) -> tuple[int, bytes]:
    return api_request(api_key, "POST", f"/sessions/{sid}:archive", body={})


def delete_session(api_key: str, sid: str) -> tuple[int, bytes]:
    return api_request(api_key, "DELETE", f"/sessions/{sid}")


def print_session(s: dict, prefix: str = "  ") -> None:
    sid = s["name"].split("/")[-1]
    source = s.get("sourceContext", {}).get("source", "unknown")
    state = s.get("state", "?")
    title = s.get("title", "?")[:60]
    created = s.get("createTime", "?")[:19].replace("T", " ")
    print(f"{prefix}{sid} | {state:<28} | {created} | {source} | {title}")


def do_archive(api_key: str, sessions: list, dry_run: bool) -> tuple[int, int]:
    archived = skipped = failed = 0
    for s in sessions:
        sid = s["name"].split("/")[-1]
        title = s.get("title", "?")[:60]
        state = s.get("state", "?")
        if state == "ARCHIVED":
            print(f"  SKIP     {sid} | already ARCHIVED | {title}")
            skipped += 1
            continue
        if dry_run:
            print(f"  [DRY] ARCHIVE {sid} | {state} | {title}")
            archived += 1
            continue
        status, body = archive_session(api_key, sid)
        if status in (200, 204):
            print(f"  ARCHIVED {sid} | {title}")
            archived += 1
        else:
            print(f"  FAILED   {sid} | archive HTTP {status} | {body[:120]}")
            failed += 1
    return archived, failed


def do_delete(api_key: str, sessions: list, archive_first: bool, dry_run: bool) -> tuple[int, int]:
    deleted = failed = 0
    for s in sessions:
        sid = s["name"].split("/")[-1]
        title = s.get("title", "?")[:60]
        state = s.get("state", "?")

        if archive_first and state != "ARCHIVED":
            if dry_run:
                print(f"  [DRY] ARCHIVE {sid} | {state} | {title}")
            else:
                status, body = archive_session(api_key, sid)
                if status in (200, 204):
                    print(f"  ARCHIVED {sid} | {title}")
                else:
                    print(f"  ARCHIVE FAILED {sid} | {title} | HTTP {status} | {body[:120]}")
                    failed += 1
                    continue

        if dry_run:
            print(f"  [DRY] DELETE {sid} | {state} | {title}")
            deleted += 1
            continue

        status, body = delete_session(api_key, sid)
        if status in (200, 204):
            print(f"  DELETED  {sid} | {title}")
            deleted += 1
        else:
            print(f"  FAILED   {sid} | delete HTTP {status} | {body[:120]}")
            failed += 1

    return deleted, failed


def main():
    parser = argparse.ArgumentParser(
        description="Clean up Jules sessions: archive, delete, or purge.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--api-key", default=os.environ.get("JULES_API_KEY"),
                        help="Jules API key (or set JULES_API_KEY env var)")
    parser.add_argument("--source", default=os.environ.get("JULES_SOURCE"),
                        help="Filter by source repo, e.g. sources/github/OWNER/REPO "
                             "(or set JULES_SOURCE env var)")
    parser.add_argument("--all", dest="all_sources", action="store_true",
                        help="Operate on sessions from ALL repos (dangerous!)")
    parser.add_argument("--archived", action="store_true",
                        help="Only operate on sessions already in ARCHIVED state")
    parser.add_argument("--state", metavar="STATE",
                        help="Only operate on sessions in this state "
                             "(e.g. COMPLETED, FAILED, QUEUED).  "
                             f"Valid values: {', '.join(sorted(ALL_STATES))}")
    parser.add_argument("--archive-first", action="store_true",
                        help="Archive each session before deleting it (audit trail)")
    parser.add_argument("--archive-only", action="store_true",
                        help="Archive sessions WITHOUT deleting them")
    parser.add_argument("--purge", action="store_true",
                        help="Full cleanup: archive ALL sessions then delete ALL "
                             "(equivalent to --archive-first with no state filter)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List sessions without making any changes")
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: No API key provided. Set JULES_API_KEY or use --api-key.", file=sys.stderr)
        sys.exit(1)

    if not args.all_sources and not args.source:
        print("ERROR: Provide --source sources/github/OWNER/REPO, "
              "set JULES_SOURCE, or use --all.", file=sys.stderr)
        sys.exit(1)

    if args.state and args.state.upper() not in ALL_STATES:
        print(f"ERROR: Unknown state '{args.state}'. "
              f"Valid values: {', '.join(sorted(ALL_STATES))}", file=sys.stderr)
        sys.exit(1)

    # Mutually exclusive mode checks
    mode_flags = {"--archived": args.archived,
                  "--archive-only": args.archive_only,
                  "--purge": args.purge}
    active_modes = [name for name, val in mode_flags.items() if val]
    if len(active_modes) > 1:
        print(f"ERROR: {', '.join(active_modes)} are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    if args.purge and args.state:
        print("ERROR: --purge operates on all sessions; --state cannot be combined with it.",
              file=sys.stderr)
        sys.exit(1)

    if args.archive_only and args.archive_first:
        print("ERROR: --archive-only and --archive-first are mutually exclusive.",
              file=sys.stderr)
        sys.exit(1)

    print("Fetching all sessions...")
    all_sessions = fetch_all_sessions(args.api_key)
    print(f"Total sessions fetched: {len(all_sessions)}")

    # --- scope by source ---
    if args.all_sources:
        sessions = all_sessions
        print(f"\nScope: ALL repos ({len(sessions)} sessions)")
    else:
        sessions = [s for s in all_sessions
                    if s.get("sourceContext", {}).get("source") == args.source]
        print(f"\nScope: {args.source}")
        print(f"Matching sessions: {len(sessions)} of {len(all_sessions)} total")

    # --- state filters ---
    if args.purge:
        # purge = archive every session then delete everything
        pass
    elif args.archived:
        before = len(sessions)
        sessions = [s for s in sessions if s.get("state") == "ARCHIVED"]
        print(f"Filtering to ARCHIVED state: {len(sessions)} of {before}")
    elif args.state:
        state_filter = args.state.upper()
        before = len(sessions)
        sessions = [s for s in sessions if s.get("state") == state_filter]
        print(f"Filtering to {state_filter} state: {len(sessions)} of {before}")

    if not sessions:
        print("Nothing to process.")
        return

    # --- dry-run listing ---
    if args.dry_run:
        action = "archived" if args.archive_only else ("purged" if args.purge else "deleted")
        print(f"\n[DRY RUN] Sessions that would be {action}:")
        for s in sessions:
            print_session(s)
        print(f"\nTotal: {len(sessions)}")
        return

    # --- execute ---
    if args.archive_only:
        print(f"\nArchiving {len(sessions)} session(s)...")
        archived, failed = do_archive(args.api_key, sessions, dry_run=False)
        print(f"\nDone. Archived: {archived}  Failed: {failed}")

    elif args.purge:
        print(f"\nPurging {len(sessions)} session(s) "
              "(archive all first, then delete all)...")
        print("\n-- Phase 1: Archive --")
        archived, arch_failed = do_archive(args.api_key, sessions, dry_run=False)
        print(f"   Archived: {archived}  Failed: {arch_failed}")

        print("\n-- Phase 2: Delete --")
        deleted, del_failed = do_delete(
            args.api_key, sessions, archive_first=False, dry_run=False
        )
        print(f"\nDone. Archived: {archived}  Deleted: {deleted}  "
              f"Failed: {arch_failed + del_failed}")

    else:
        print(f"\nDeleting {len(sessions)} session(s)...")
        deleted, failed = do_delete(
            args.api_key, sessions,
            archive_first=args.archive_first,
            dry_run=False,
        )
        print(f"\nDone. Deleted: {deleted}  Failed: {failed}")


if __name__ == "__main__":
    main()
