# climbing-watch

Watches the CTU (ČVUT) climbing PE class listing for newly opened free spots
and sends a push notification via [ntfy.sh](https://ntfy.sh) when one appears.

Source page: https://www.utvs.cvut.cz/vyuka/povinna-volitelna?s%5B%5D=17&d=0&t=420%3B1380

## How it runs

The check (`climbing_watch.py`) runs as a GitHub Actions workflow:
[`.github/workflows/check.yml`](.github/workflows/check.yml).

**Scheduling is external, not GitHub's own `schedule:` trigger.** GitHub
throttles frequent cron schedules heavily (a `*/5 * * * *` schedule was
observed firing only every 2-4 hours in practice, sometimes not at all for
hours), so the workflow only listens for `workflow_dispatch` and is triggered
every 5 minutes by an outside cron service:

- **[cron-job.org](https://cron-job.org)** — free account, calls the GitHub
  API every 5 minutes:
  - `POST https://api.github.com/repos/ProkopU/climbing-watch-cvut/actions/workflows/check.yml/dispatches`
  - Body: `{"ref":"main"}`
  - Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
    `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`
  - Auth uses a fine-grained GitHub personal access token scoped only to this
    repo with **Actions: Read and write** permission.
  - The token lives locally in `token_cron.txt` (gitignored, never committed)
    and in the cron-job.org job config — it is not stored anywhere in this repo.

If cron-job.org is ever paused/deleted and nothing else calls
`workflow_dispatch`, checks stop happening — there is no automatic fallback
schedule.

## What the workflow does each run

1. Checks out the repo, sets up Python 3.12.
2. Runs `climbing_watch.py`, which:
   - Fetches and parses the class listing page.
   - Compares each class's free-spot count against `climbing_watch_state.json`
     (last known count per class).
   - If a class's free count increased from 0 (or increased at all), sends an
     `ntfy.sh` push notification (topic from the `NTFY_TOPIC` repo secret).
   - Appends a summary line to `climbing_watch.log` (newest entries at the
     top; capped at the last 2000 lines).
   - Overwrites `climbing_watch_state.json` with the latest counts.
3. Commits `climbing_watch_state.json` and `climbing_watch.log` back to `main`
   if they changed. The push step retries with `fetch` + `rebase` a few times
   if it races another run (e.g. a manual trigger landing close to a
   cron-job.org trigger).

## Manual run / debugging

```bash
gh workflow run check.yml          # trigger a run manually
gh run list --workflow=check.yml   # see recent runs
gh run view <run-id> --log-failed  # inspect a failed run
```

To test the script locally: `NTFY_TOPIC=<topic> python3 climbing_watch.py`.

## Files

| File | Purpose |
|---|---|
| `climbing_watch.py` | The checker script |
| `climbing_watch_state.json` | Last known free-spot count per class |
| `climbing_watch.log` | Run history, newest first, capped at 2000 lines |
| `.github/workflows/check.yml` | The GitHub Actions job (manual-dispatch only) |
| `token_cron.txt` | Local-only PAT for the cron-job.org trigger (gitignored) |
