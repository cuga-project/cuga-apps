# Usage Collector — cross-app usage dashboard

A single, always-on dashboard that answers "**are people actually using these
apps?**" across the whole cuga-apps fleet — requests, unique visitors per day,
and last-seen, per app.

Every app installs [`apps/_usage.py`](../_usage.py), which fire-and-forgets a
tiny ping per request to this collector's `POST /track`. The collector
aggregates them into per-app, per-day counters and serves the dashboard at `/`.

## Why a separate app

The other apps **scale to zero**, so any counters kept in their memory are lost
on cold start. This collector runs at **min-scale 1** and **persists a
snapshot**, so the history survives restarts.

## Privacy

It only ever receives `visitor` = a **daily-salted hash of the client IP**
(computed in `_usage.py`). No IPs, no PII, and a visitor can't be linked across
days. "Unique visitors" is therefore a per-day count.

## Persistence

| Mode | How | Durability |
| ---- | --- | ---------- |
| **File** (default) | JSON at `USAGE_DB_PATH` (default `/tmp/usage_db.json`) | survives while the instance lives; ephemeral across CE redeploys |
| **S3 / IBM COS** | set `USAGE_S3_BUCKET` (+ `USAGE_S3_ENDPOINT` for COS) and `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` | durable across redeploys — **recommended for production** |

Snapshots are written every `USAGE_SAVE_INTERVAL` seconds (when dirty) and on
shutdown, and loaded on startup.

## Security

- `POST /track` requires header `X-Usage-Token == USAGE_TOKEN` (if set). **Set
  it in production** so the public endpoint can't be flooded with fake data.
- The dashboard (`/`, `/api/stats`) requires `?token=<USAGE_DASHBOARD_TOKEN>`
  (if set) so usage stats aren't public.

## Run

```bash
cd apps/usage_collector
pip install -r requirements.txt
python main.py --port 28827
```

Open <http://127.0.0.1:28827> (append `?token=…` if `USAGE_DASHBOARD_TOKEN` is set).

For apps to report to it, set in their environment:

```bash
export USAGE_COLLECTOR_URL=http://127.0.0.1:28827/track
export USAGE_TOKEN=<same secret as the collector>     # if you set one
```

`start.sh` exports `USAGE_COLLECTOR_URL` automatically for the in-container run.

## Endpoints

| Method | Path          | Purpose                                             |
| ------ | ------------- | --------------------------------------------------- |
| POST   | `/track`      | Receive a usage ping (token-guarded)                |
| GET    | `/`           | Dashboard                                           |
| GET    | `/api/stats`  | Rollup JSON the dashboard polls                     |
| GET    | `/health`     | `{"ok": true}`                                      |

## Code Engine

1. Deploy it (it's Tier 2 / min-scale 1 in `deploy_apps.sh`):
   `./deploy_apps.sh usage_collector`
2. Grab its public URL: `ibmcloud ce app get --name cuga-apps-usage-collector --output url`
3. Put these in the shared `app-env` secret (so every app reports in):
   - `USAGE_COLLECTOR_URL=https://<that-url>/track`
   - `USAGE_TOKEN=<a secret>` (and the same on the collector)
   - optionally `USAGE_DASHBOARD_TOKEN=<another secret>`
   - for durable history: `USAGE_S3_BUCKET`, `USAGE_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
4. Redeploy the apps so they pick up the env: `./deploy_apps.sh`

This app is an **ops dashboard**, not a demo — it is intentionally not listed in
the public umbrella UI (`usecases.ts`).
