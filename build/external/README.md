# build/external/ — apps that live in their own repo, deployed next to the all-in-one

Most cuga-apps ship **inside** the all-in-one `cuga-agent-apps` image ([../ce/](../ce/)).
An *external* app is different: its source and Dockerfile live in **its own repo**, and it
runs as **its own Code Engine app** in the same project. The umbrella UI (Hugging Face
Space + the all-in-one's own UI) links to it like any other tile.

Use this when an app needs one of:

- **Its own origin**: e.g. users paste their own API keys into the page. Inside the all-in-one,
  every app shares one origin, so any app's code could reach another app's page.
- **Its own secret**: credentials that the other 21 apps shouldn't see.
- **Its own lifecycle**: heavy images, its own restarts, without redeploying every other app.

| App | Repo | CE app | Why external |
|---|---|---|---|
| `bharat-core-cuga-agent-app` | [CUGA-Voice-RAG-Agent](https://github.ibm.com/Anupama-Murthi/CUGA-Voice-RAG-Agent) | `bharat-core-cuga-agent-app` | Users enter their own Sarvam key; 2.2 GB embedding model + baked index |

## Files

| File | What |
|---|---|
| `apps/<app>.conf` | Everything about one app: CE name, image, port, sizing, probes, source repo. Sourced by both scripts |
| `apps/<app>.env.example` | What goes in the app's CE secret. Copy to `apps/<app>.env` (gitignored by the repo's `*.env` rule) |
| `build_external.sh <app> <checkout>` | Build the image from the app's checkout and push to ICR, tagged with its git SHA |
| `deploy_external.sh <app> <tag>` | Sync `apps/<app>.env` → secret `<CE_APP>-env`, then create/update the CE app |

## Deploy

One-time setup is the same as the all-in-one's ([../ce/README.md](../ce/README.md#one-time-prerequisites)):
`ibmcloud login --sso`, `ibmcloud target -r us-east -g routing`,
`ibmcloud ce project select --name ce-project-routing`, registry secret `icr-secret-1`.

```bash
cd build/external
cp apps/bharat-core-cuga-agent-app.env.example apps/bharat-core-cuga-agent-app.env      # fill in

./build_external.sh bharat-core-cuga-agent-app ~/src/CUGA-Voice-RAG-Agent    # prints the tag
./deploy_external.sh bharat-core-cuga-agent-app <tag>                         # prints the URL
```

**Build modes.** By default (`MODE=ce`), Code Engine builds the image from your local checkout on
linux/amd64 in IBM Cloud and pushes it to ICR. This is the fast path on Apple Silicon, where an
emulated amd64 build is very slow. Only what the checkout's `.dockerignore` allows is uploaded,
and the script refuses to run unless that file excludes `.env` and `.git`. `MODE=local` builds
with docker/podman on this machine instead.

**Rollback.** Images are tagged by git SHA, so `./deploy_external.sh bharat-core-cuga-agent-app <previous-tag>`.

**Verify.**
```bash
curl https://bharat-core-cuga-agent-app.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/ready
python <app-checkout>/e2e_test.py https://bharat-core-cuga-agent-app.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud
ibmcloud ce app logs --name bharat-core-cuga-agent-app --follow
```

## Linking it from the umbrella UI

Add the app's tile to `cuga-apps/ui/src/data/usecases.ts` (as for any app) and its URL to
`EXTERNAL_APP_BY_ID` in `cuga-apps/ui/src/data/deployment.ts`. `resolveAppUrl()` returns that URL
in every hosted mode (Hugging Face `remote-allinone`, the all-in-one's own `single` UI, and
per-app `remote`), and the tile's `appUrl` (`http://localhost:<port>`) when running locally. Then
republish the two UIs as usual: `build/hf/build.sh` for the Space, and `build/ce/` for the
all-in-one's UI.

Do **not** add an external app to `CE_APP_BY_ID`, `build/generate.py`'s `SHIP_READY`, or
`apps/_ports.py`. Those make the all-in-one route `/a/<app>/` to a process that isn't there, and
make the smoke tests expect it locally.

## Conventions an external app must follow

These match the in-tree apps, so the umbrella UI, the stats dashboard and Code Engine treat it the same:

- **Rate limiting:** vendor `cuga-apps/apps/_ratelimit.py` unchanged; `install_rate_limit(app)`.
  Keep `MAX_SCALE=1`, since the counters are in memory.
- **Usage:** vendor `cuga-apps/apps/_usage.py` unchanged; `install_usage(app, app_name=...)`. Set
  `USAGE_COLLECTOR_URL` + `USAGE_TOKEN` in the env file to report to the all-in-one's dashboard.
- **Health:** a fast liveness path and a readiness path that returns 200 only when the app can
  actually answer (point `PROBE_READY_PATH` at it).
- **Secrets:** env file → CE secret only. No secrets in the image; `.dockerignore` excludes `.env`.
- **No CORS** unless the app genuinely needs cross-origin callers. The umbrella UI only links to apps, opening them in a new tab.
