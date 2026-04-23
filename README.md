# cleanup-google-jules

Utility script for cleaning up [Jules](https://jules.google.com) sessions via the
[Jules REST API](https://jules.google/docs/api/reference/overview/).

## Prerequisites

- Python 3.10+
- A Jules API key from <https://jules.google.com/settings/api>

```bash
export JULES_API_KEY="your_api_key"
export JULES_SOURCE="sources/github/OWNER/REPO"   # optional, safer default
```

## Usage

```
python3 jules_delete_sessions.py [OPTIONS]
```

| Flag | Description |
|---|---|
| `--api-key KEY` | Jules API key (or `JULES_API_KEY` env var) |
| `--source NAME` | Scope to one repo, e.g. `sources/github/OWNER/REPO` (or `JULES_SOURCE`) |
| `--all` | Operate across **all** repos (destructive!) |
| `--dry-run` | List matching sessions without making any changes |
| `--archived` | Only operate on sessions already in `ARCHIVED` state |
| `--state STATE` | Only operate on sessions in a specific state (see below) |
| `--archive-only` | **Archive** sessions without deleting them |
| `--archive-first` | Archive each session before deleting (audit trail) |
| `--purge` | Full cleanup: archive **all** sessions then delete **all** |

### Session states

`QUEUED` · `PLANNING` · `AWAITING_PLAN_APPROVAL` · `AWAITING_USER_FEEDBACK` ·
`IN_PROGRESS` · `PAUSED` · `COMPLETED` · `FAILED` · `ARCHIVED`

### Examples

```bash
# Dry-run: see what would be deleted
python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --dry-run

# Delete sessions for a specific repo
python3 jules_delete_sessions.py --source sources/github/OWNER/REPO

# Delete only already-archived sessions
python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --archived

# Archive sessions without deleting (move to archive shelf)
python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --archive-only

# Archive before deleting (keeps audit trail)
python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --archive-first

# Full purge: archive everything then delete everything
python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --purge

# Delete only COMPLETED sessions
python3 jules_delete_sessions.py --source sources/github/OWNER/REPO --state COMPLETED

# Delete ALL sessions across all repos
python3 jules_delete_sessions.py --all
```

## API coverage

The Jules v1alpha API exposes **Sessions**, **Activities**, and **Sources**.

> **Knowledge & Memory** — Jules may surface "Knowledge" and "Memory" features
> in its web UI, but as of the current API version there are no public endpoints
> for these resources.  This script will be updated once those endpoints are
> published.