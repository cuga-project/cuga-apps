# build/hf/ — lightweight umbrella UI for a Hugging Face Static Space

This packages the umbrella UI as a **dumb, static launcher** for a Hugging Face
Space. It pairs with the all-in-one image deployed to Code Engine ([build/ce/](../ce)):

```
   HF Static Space (this)              Code Engine: ONE all-in-one service
   ┌────────────────────┐   click    ┌──────────────────────────────────────┐
   │ umbrella UI (SPA)  │ ─────────▶ │ nginx :8080                           │
   │ links →            │  travel    │  /a/travel-planner/ → travel_planner   │
   │  <ce>/a/<app>/      │  planner   │  /a/city-beat/      → city_beat        │
   │  <ce>/a/usage-..    │            │  /a/usage-collector/→ stats dashboard  │
   └────────────────────┘            │  21 apps + 5 MCP (loopback) + stats   │
     no backend                      └──────────────────────────────────────┘
```

The Space carries **no backend** — no apps, no MCP, no Python. It only
*navigates* to the CE service's `/a/<app>/` routes (full-page, so there's no
CORS). The heavy, stateful backend is the single CE container.

## How it works

The umbrella UI ([cuga-apps/ui](../../cuga-apps/ui)) has a build mode
`remote-allinone` (in [deployment.ts](../../cuga-apps/ui/src/data/deployment.ts)).
With it, every app link resolves to `${VITE_ALLINONE_BASE}/a/<seg>/` — the same
path the all-in-one nginx serves, made absolute to the CE host. `<seg>` is the
hyphenated app name (matching `build/generate.py`'s routes).

This is purely additive: the existing `local`, `remote`, and `single` (in-image)
modes are untouched, so the all-in-one image still serves its own UI at `/`.

## Build

```bash
cd build/hf
ALLINONE_BASE=https://<your-ce-allinone-host> ./build.sh
# → build/hf/dist/  (a complete HF Static Space: index.html + assets + README)
```

`ALLINONE_BASE` is **baked into the bundle**. If you redeploy the all-in-one to a
different CE URL, rebuild and re-push. (Default is the repo's CE project; pass
your own.)

## Publish to a Hugging Face Static Space

1. Create a Space: huggingface.co → New Space → **SDK: Static**.
2. Push the **contents** of `build/hf/dist/` to the Space's git repo:

   ```bash
   git clone https://huggingface.co/spaces/<user>/<space> /tmp/space
   cp -r build/hf/dist/. /tmp/space/
   cd /tmp/space && git add -A && git commit -m "umbrella UI" && git push
   ```

The Space serves at `https://<user>-<space>.hf.space/`. Clicking any app opens
the corresponding `<ce-host>/a/<app>/`; **Stats ↗** opens
`<ce-host>/a/usage-collector/`.

## Deploy order

1. Deploy the all-in-one to Code Engine first (`build/ce/`), note its URL.
2. `ALLINONE_BASE=<that-url> ./build.sh`, then publish `dist/` to HF.

## Notes

- `dist/` is build output — git-ignored here; it lives in the HF Space repo.
- A `404.html` (copy of `index.html`) is included so client-side routes survive
  a hard refresh on the static host.
- CORS isn't needed for launching apps (full-page navigation). It would only
  matter if the UI started *fetching* app data cross-origin — it doesn't.
