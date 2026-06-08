/**
 * deployment.ts — single source of truth for URL rewriting in the umbrella UI.
 *
 * Two modes:
 *   local  — rewrite `localhost` → window.location.hostname (works for
 *            `docker compose up` on laptop or a remote VM).
 *   remote — rewrite to the corresponding Code Engine deployment URL.
 *            Used when the umbrella UI itself is hosted somewhere the
 *            local docker apps aren't reachable (Hugging Face Space,
 *            Code Engine, custom CDN).
 *
 * Detected in this order:
 *   1. Build-time   VITE_DEPLOYMENT_TARGET=remote (or legacy `huggingface`/
 *                   `ce`) baked in via Dockerfile build-arg. Always wins.
 *   2. Runtime      hostname ends in `.hf.space`, `.huggingface.co`, or
 *                   `.codeengine.appdomain.cloud` → remote.
 *   3. Otherwise    local.
 *
 * In remote mode, only apps in CE_APP_BY_ID get a working URL; others
 * return null so the "Launch App" button can be suppressed.
 *
 * No secrets here. CE project hash + region are public info.
 */
import type { UseCase } from './usecases'


// ── Code Engine project — hardcodes ────────────────────────────────────
// CE app URLs follow the pattern
//   https://<app-name>.<project-hash>.<region>.codeengine.appdomain.cloud
// These two strings are stable for the life of the project. Change them
// if you redeploy in a different CE project. Public information — safe
// to ship in client-side bundles.
export const CE_PROJECT_HASH = '1gxwxi8kos9y'
export const CE_REGION       = 'us-east'


// ── Apps actually deployed to CE (tier 1 + tier 2 = 26) ────────────────
// Maps the use-case `id` from usecases.ts to the CE app name. Most are
// `cuga-apps-<id>` directly; the one exception is `travel-agent` whose
// underlying directory is `travel_planner`.
const CE_APP_BY_ID: Record<string, string> = {
  // Tier 1 — stateless
  'web-researcher':     'cuga-apps-web-researcher',
  'paper-scout':        'cuga-apps-paper-scout',
  'travel-agent':       'cuga-apps-travel-planner',  // id ≠ dirname
  'code-reviewer':      'cuga-apps-code-reviewer',
  'hiking-research':    'cuga-apps-hiking-research',
  'movie-recommender':  'cuga-apps-movie-recommender',
  'webpage-summarizer': 'cuga-apps-webpage-summarizer',
  'wiki-dive':          'cuga-apps-wiki-dive',
  'youtube-research':   'cuga-apps-youtube-research',
  'arch-diagram':       'cuga-apps-arch-diagram',
  'brief-budget':       'cuga-apps-brief-budget',
  'trip-designer':      'cuga-apps-trip-designer',
  'ibm-cloud-advisor':  'cuga-apps-ibm-cloud-advisor',
  'ibm-docs-qa':        'cuga-apps-ibm-docs-qa',
  'ibm-whats-new':      'cuga-apps-ibm-whats-new',
  'api-doc-gen':        'cuga-apps-api-doc-gen',
  'stock-alert':        'cuga-apps-stock-alert',
  'recipe-composer':    'cuga-apps-recipe-composer',
  'city-beat':          'cuga-apps-city-beat',
  'github-trending':    'cuga-apps-github-trending',
  'ai-labs-news':       'cuga-apps-ai-labs-news',
  'find-a-doctor':      'cuga-apps-find-a-doctor',

  // Tier 2 — in-memory state
  'newsletter':         'cuga-apps-newsletter',
  'server-monitor':     'cuga-apps-server-monitor',
  'ouroboros':          'cuga-apps-ouroboros',
  'meetup-finder':      'cuga-apps-meetup-finder',  // browser image (Playwright)
}


// ── Deployment-target detection ────────────────────────────────────────
type DeploymentTarget = 'local' | 'remote'

const REMOTE_HOST_SUFFIXES = [
  '.hf.space',
  '.huggingface.co',
  '.codeengine.appdomain.cloud',
]

function detectTarget(): DeploymentTarget {
  // Build-time override wins. `huggingface` and `ce` accepted as legacy
  // aliases for `remote` so existing build pipelines keep working.
  // `remote-allinone` also counts as remote (it's hosted off-box, on HF).
  const buildTarget = (import.meta as any).env?.VITE_DEPLOYMENT_TARGET
  if (buildTarget === 'remote' || buildTarget === 'huggingface'
      || buildTarget === 'ce' || buildTarget === 'remote-allinone') {
    return 'remote'
  }
  if (typeof window !== 'undefined') {
    const host = window.location.hostname
    if (REMOTE_HOST_SUFFIXES.some(s => host.endsWith(s))) {
      return 'remote'
    }
  }
  return 'local'
}


// Cached so React renders don't recompute on every tile.
const TARGET = detectTarget()


// ── remote-allinone mode (lightweight HF umbrella UI → CE all-in-one) ───
// A static umbrella UI (e.g. a Hugging Face Static Space) that only LAUNCHES
// apps, linking into the single all-in-one Code Engine service's path routes
// (`<base>/a/<app>/`). The heavy backend (apps + MCP + stats) lives in that one
// CE container; this UI carries no backend of its own.
//
//   VITE_DEPLOYMENT_TARGET=remote-allinone
//   VITE_ALLINONE_BASE=https://<ce-allinone-host>   (no trailing slash needed)
const BUILD_TARGET = (import.meta as any).env?.VITE_DEPLOYMENT_TARGET as string | undefined
const ALLINONE_BASE = (((import.meta as any).env?.VITE_ALLINONE_BASE as string | undefined) || '')
  .replace(/\/+$/, '')

/** Path segment behind the all-in-one nginx for an app id — identical to the
 *  `single`-mode derivation and to generate.py's nginx routes
 *  (cuga-apps-web-researcher → web-researcher). null if the app isn't deployed. */
function allinoneSeg(id: string): string | null {
  const ce = CE_APP_BY_ID[id]
  return ce ? ce.replace(/^cuga-apps-/, '') : null
}


// ── URL transform ──────────────────────────────────────────────────────

/**
 * Resolve the right `appUrl` for the current deployment context.
 *
 *   local  → rewrite `localhost` to the page's own hostname so the UI
 *            works when accessed via remote IP, tunnel, or proxy.
 *   remote → rewrite to the CE deployment URL for this app, IF the app
 *            is in CE_APP_BY_ID. If not, return null so callers can
 *            suppress the "Launch App" button.
 *
 * Returns null when the app has no usable URL in the current context.
 */
export function resolveAppUrl(uc: Pick<UseCase, 'id' | 'appUrl'>): string | null {
  if (!uc.appUrl) return null

  // remote-allinone: link into the single CE all-in-one service's path route.
  // Same `/a/<seg>/` the nginx serves, made absolute to the CE host.
  if (BUILD_TARGET === 'remote-allinone') {
    const seg = allinoneSeg(uc.id)
    return seg && ALLINONE_BASE ? `${ALLINONE_BASE}/a/${seg}/` : null
  }

  if (TARGET === 'remote') {
    const ceName = CE_APP_BY_ID[uc.id]
    if (!ceName) {
      return null
    }
    return `https://${ceName}.${CE_PROJECT_HASH}.${CE_REGION}.codeengine.appdomain.cloud`
  }

  // Local context: rewrite localhost → page hostname so the link follows
  // the user wherever they're accessing the UI from.
  if (typeof window !== 'undefined') {
    return uc.appUrl.replace('localhost', window.location.hostname)
  }
  return uc.appUrl
}


/**
 * True when this build/runtime is hosted somewhere CE-rewriting is
 * needed (Hugging Face Space, Code Engine, etc). Useful for conditionally
 * showing CE-aware copy elsewhere in the UI.
 */
export const isRemote = (): boolean => TARGET === 'remote'


/**
 * URL of the usage / stats dashboard (the bundled usage_collector app), resolved
 * for the current deployment context:
 *
 *   single  → '/a/usage-collector/'  (path-routed behind the all-in-one nginx)
 *   remote  → the Code Engine URL for cuga-apps-usage-collector
 *   local   → http://<page-host>:28827/  (usage_collector's dev port)
 *
 * Checks VITE_DEPLOYMENT_TARGET directly so it works in the single-container
 * build without the patch-deployment.cjs injection (which only rewrites
 * resolveAppUrl). Returns null only when there is no usable URL.
 */
export function statsDashboardUrl(): string | null {
  const buildTarget = (import.meta as any).env?.VITE_DEPLOYMENT_TARGET
  if (buildTarget === 'single') {
    return '/a/usage-collector/'
  }
  if (buildTarget === 'remote-allinone') {
    return ALLINONE_BASE ? `${ALLINONE_BASE}/a/usage-collector/` : null
  }
  if (TARGET === 'remote') {
    return `https://cuga-apps-usage-collector.${CE_PROJECT_HASH}.${CE_REGION}.codeengine.appdomain.cloud`
  }
  const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
  return `http://${host}:28827/`
}
