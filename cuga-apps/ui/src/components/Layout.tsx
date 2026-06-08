import { NavLink } from 'react-router-dom'
import { useTheme } from '../hooks/useTheme'
import { statsDashboardUrl } from '../data/deployment'

const NAV = [
  { to: '/', label: 'Apps', end: true },
  { to: '/mcp-servers', label: 'MCP Servers', end: false },
]

// External link to the bundled usage/stats dashboard (resolved per deployment
// mode). Opens in a new tab since it's a separate app, not a UI route.
const STATS_URL = statsDashboardUrl()

// Where to send feedback / bug reports — the cuga-apps GitHub issue tracker.
const FEEDBACK_URL = 'https://github.com/cuga-project/cuga-apps/issues/new'

export default function Layout({ children }: { children: React.ReactNode }) {
  const { theme, toggle } = useTheme()

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-tbg">
      {/* Top bar */}
      <header className="h-16 flex-shrink-0 bg-tsurf border-b border-tborder flex items-center px-6 gap-5">
        <NavLink to="/" className="flex items-center gap-3 shrink-0">
          <div className="w-8 h-8 bg-indigo-600 flex items-center justify-center text-base font-semibold text-white">
            C
          </div>
          <span className="text-t1 font-semibold text-lg tracking-tight">
            CUGA <span className="text-t3 font-normal">Apps</span>
          </span>
        </NavLink>

        {/* Tabs */}
        <nav className="flex items-center gap-1 h-full">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `relative h-full flex items-center px-4 text-sm font-medium transition-colors ${
                  isActive
                    ? 'text-t1 after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-indigo-600'
                    : 'text-t3 hover:text-t1'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
          {STATS_URL && (
            <a
              href={STATS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="relative h-full flex items-center px-4 text-sm font-medium text-t3 hover:text-t1 transition-colors"
            >
              Stats ↗
            </a>
          )}
          <a
            href={FEEDBACK_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="relative h-full flex items-center px-4 text-sm font-medium text-t3 hover:text-t1 transition-colors"
          >
            Feedback ↗
          </a>
        </nav>

        <div className="flex-1" />
        <button
          onClick={toggle}
          className="flex items-center gap-2 px-4 h-9 bg-tsurf border border-tborder text-sm font-medium text-t2 hover:bg-tsurf2 hover:text-t1 transition-colors"
        >
          <span>{theme === 'warm' ? '☀ Light' : '🌙 Gray 100'}</span>
        </button>
      </header>

      {/* Privacy notice — these are public demo apps; usage (including the
          text you type) is logged for analytics. Tell users not to paste
          secrets/PII. */}
      <div className="flex-shrink-0 bg-amber-100 border-b border-amber-300 px-6 py-2 text-xs text-amber-900">
        Heads up: these are public demo apps. Your requests are logged for usage
        analytics — please don't enter confidential information, credentials, or
        personal data.
      </div>

      {/* Content */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}
