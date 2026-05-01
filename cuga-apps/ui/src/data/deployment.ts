/**
 * deployment.ts — single source of truth for URL rewriting in the umbrella UI.
 *
 * The umbrella UI is a static SPA. The app URLs in usecases.ts are written
 * for local docker-compose (`http://localhost:28xxx`). When the UI runs in
 * a different deployment context (Hugging Face Space, served from a remote
 * machine), those localhost URLs need to be rewritten so a visitor's browser
 * actually reaches the running app.
 *
 * We support three contexts, detected in this order:
 *
 *   1. Build-time:   VITE_DEPLOYMENT_TARGET=huggingface  (baked in via the
 *                    Dockerfile build-arg). Always wins when set.
 *   2. Runtime:      hostname ends in `.hf.space` — Hugging Face Spaces
 *                    auto-detected without rebuild.
 *   3. Otherwise:    rewrite `localhost` → window.location.hostname so the
 *                    UI works when accessed via remote IP / proxy.
 *
 * On HF, `appUrl` localhost links get rewritten to the corresponding Code
 * Engine deployment URL (https://cuga-apps-<name>.<hash>.<region>.code
 * engine.appdomain.cloud). Only apps actually deployed to CE (the 19 in
 * tier 1 + tier 2) are rewritten — others have their links suppressed
 * because they have no public CE URL.
 *
 * No secrets here. The CE project hash + region are public info.
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
type DeploymentTarget = 'local' | 'huggingface'

function detectTarget(): DeploymentTarget {
  // Build-time override wins.
  // (Vite replaces import.meta.env.VITE_* at build time.)
  const buildTarget = (import.meta as any).env?.VITE_DEPLOYMENT_TARGET
  if (buildTarget === 'huggingface' || buildTarget === 'ce') {
    return 'huggingface'
  }
  // Runtime hostname check — works for HF without any rebuild.
  if (typeof window !== 'undefined') {
    const host = window.location.hostname
    if (host.endsWith('.hf.space') || host.endsWith('.huggingface.co')) {
      return 'huggingface'
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
 *   local       → rewrite `localhost` to the page's own hostname so the UI
 *                 works when accessed via remote IP, tunnel, or proxy.
 *   huggingface → rewrite to the CE deployment URL for this app, IF the
 *                 app is in the deployed set. If not (tier 3 apps without
 *                 a CE deployment), return null so callers can suppress
 *                 the "Launch App" button.
 *
 * Returns null when the app has no usable URL in the current context.
 */
export function resolveAppUrl(uc: Pick<UseCase, 'id' | 'appUrl'>): string | null {
  if (!uc.appUrl) return null

  if (TARGET === 'huggingface') {
    const ceName = CE_APP_BY_ID[uc.id]
    if (!ceName) {
      // App not deployed to CE — no working URL on Hugging Face.
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
 * True when this build/runtime is targeting Hugging Face. Useful for
 * conditionally showing CE-aware copy elsewhere in the UI.
 */
export const isHuggingFace = (): boolean => TARGET === 'huggingface'
