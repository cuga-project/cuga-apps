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


// ── Apps actually deployed to CE (tier 1 + tier 2 = 21) ────────────────
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

  // Tier 2 — in-memory state
  'newsletter':         'cuga-apps-newsletter',
  'server-monitor':     'cuga-apps-server-monitor',
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
  const buildTarget = (import.meta as any).env?.VITE_DEPLOYMENT_TARGET
  if (buildTarget === 'remote' || buildTarget === 'huggingface' || buildTarget === 'ce') {
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
