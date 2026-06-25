import { NavLink } from 'react-router-dom'
import { useTheme } from '../hooks/useTheme'

const NAV = [
  { to: '/', label: 'Apps', end: true },
  { to: '/mcp-servers', label: 'MCP Servers', end: false },
]

// Where to send feedback / bug reports — the cuga-apps GitHub issue tracker.
const FEEDBACK_URL = 'https://github.com/cuga-project/cuga-apps/issues/new'

// The source for this whole collection — surfaced at the very top so visitors
// can jump straight to the code behind every app on the page.
const REPO_URL = 'https://github.com/cuga-project/cuga-apps'

// The CUGA agent harness itself — the "give us a star" CTA points here, not at
// the apps repo above.
const STAR_URL = 'https://github.com/cuga-project/cuga-agent'

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
        <a
          href={STAR_URL}
          target="_blank"
          rel="noopener noreferrer"
          title="Star CUGA on GitHub"
          className="flex items-center gap-2 px-4 h-9 rounded-full text-sm font-semibold text-[#3a2c08] bg-[linear-gradient(135deg,#f5dca0_0%,#e6c074_50%,#d4a857_100%)] border border-[#d8b970] shadow-[0_2px_8px_rgba(180,130,40,0.22)] hover:brightness-105 transition"
        >
          <span aria-hidden="true" className="text-base leading-none">⭐</span>
          <span>Star CUGA on GitHub</span>
        </a>
        <a
          href={REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
          title="cuga-apps source on GitHub"
          className="flex items-center gap-2 px-3 h-9 bg-tsurf border border-tborder text-sm font-medium text-t2 hover:bg-tsurf2 hover:text-t1 transition-colors"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true" className="w-4 h-4 fill-current">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/>
          </svg>
          <span>GitHub</span>
        </a>
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
