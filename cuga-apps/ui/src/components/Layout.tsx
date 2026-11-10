import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useTheme } from '../hooks/useTheme'

const NAV = [
  { to: '/', label: 'Apps', end: true },
  { to: '/mcp-servers', label: 'MCP Servers', end: false },
]

// Where to send feedback / bug reports — the cuga-apps GitHub issue tracker.
const FEEDBACK_URL = 'https://github.com/cuga-project/cuga-apps/issues/new'
// The source for this whole collection.
const REPO_URL = 'https://github.com/cuga-project/cuga-apps'
// The CUGA agent harness itself — the "Star us" CTA points here.
const STAR_REPO = 'cuga-project/cuga-agent'
const STAR_URL = `https://github.com/${STAR_REPO}`
const LOGO = `${((import.meta as any).env?.BASE_URL as string | undefined) ?? "/"}cuga-logo.png`

// Live star count, like cuga.dev's header. Public GitHub API, cached for the
// session; the button just shows "Star us" if the call fails or is rate-limited.
function useStarCount(): number | null {
  const [stars, setStars] = useState<number | null>(() => {
    try { const v = sessionStorage.getItem('cuga-stars'); return v ? Number(v) : null } catch { return null }
  })
  useEffect(() => {
    if (stars !== null) return
    fetch(`https://api.github.com/repos/${STAR_REPO}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d && typeof d.stargazers_count === 'number') {
          setStars(d.stargazers_count)
          try { sessionStorage.setItem('cuga-stars', String(d.stargazers_count)) } catch { /* ignore */ }
        }
      })
      .catch(() => {})
  }, [stars])
  return stars
}

function GitHubIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className={`${className} fill-current`}>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/>
    </svg>
  )
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { theme, toggle } = useTheme()
  const stars = useStarCount()

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-tbg">
      <header className="h-[72px] flex-shrink-0 bg-tsurf/95 backdrop-blur border-b border-tborder flex items-center px-4 md:px-14 gap-6 md:gap-10">
        <NavLink to="/" className="flex items-center gap-2.5 shrink-0" title="CUGA Apps">
          <img src={LOGO} alt="" className="w-8 h-8 object-contain rounded" />
          <span className="font-display text-[26px] font-medium tracking-tight text-t1 leading-none">
            CUGA<span className="text-indigo-600">.</span>
          </span>
          <span className="eyebrow text-t3 mt-1 hidden sm:inline">Apps</span>
        </NavLink>

        <nav className="flex items-center gap-5 md:gap-8">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}
              className={({ isActive }) =>
                `relative py-1 text-[13px] whitespace-nowrap transition-colors ${
                  isActive
                    ? 'text-t1 font-medium after:absolute after:left-0 after:right-0 after:-bottom-[25px] after:h-0.5 after:bg-indigo-600'
                    : 'text-t2 hover:text-indigo-600'}`}>
              {item.label}
            </NavLink>
          ))}
          <a href={FEEDBACK_URL} target="_blank" rel="noopener noreferrer"
             className="hidden md:block text-[13px] text-t2 hover:text-indigo-600 transition-colors">
            Feedback
          </a>
        </nav>

        <div className="flex-1" />

        <a href={STAR_URL} target="_blank" rel="noopener noreferrer" title="Star CUGA on GitHub"
           className="hidden md:flex items-center h-10 rounded border border-tborder hover:border-indigo-600 text-[13px] font-medium text-indigo-600 transition-colors">
          <span className="flex items-center gap-2 px-3.5"><GitHubIcon /> Star us</span>
          {stars !== null && (
            <span className="flex items-center gap-1.5 px-3.5 border-l border-tborder">
              <span className="text-amber-600" aria-hidden="true">★</span>
              {stars.toLocaleString()}
            </span>
          )}
        </a>
        <a href={REPO_URL} target="_blank" rel="noopener noreferrer" title="cuga-apps source on GitHub"
           className="hidden sm:flex w-10 h-10 rounded items-center justify-center border border-tborder text-t2 hover:text-indigo-600 hover:border-indigo-600 transition-colors">
          <GitHubIcon />
        </a>
        <button onClick={toggle} title={theme === 'warm' ? 'Switch to dark' : 'Switch to light'}
                className="w-10 h-10 rounded flex items-center justify-center border border-tborder text-t2 hover:text-indigo-600 hover:border-indigo-600 transition-colors">
          <span aria-hidden="true">{theme === 'warm' ? '☾' : '☀'}</span>
        </button>
        <a href="https://cuga.dev" target="_blank" rel="noopener noreferrer"
           className="hidden lg:flex items-center gap-6 h-10 px-4 rounded bg-indigo-600 hover:bg-indigo-700 text-white text-[13px] font-medium transition-colors">
          cuga.dev <span aria-hidden="true">↗</span>
        </a>
      </header>

      {/* Privacy notice — public demo apps; requests are logged for analytics. */}
      <div className="flex-shrink-0 bg-tsurf2 border-b border-tborder px-4 md:px-14 py-2 text-xs text-t3">
        <span className="font-medium text-t2">Public demo.</span> Requests are logged for usage analytics —
        please don't enter confidential information, credentials or personal data.
      </div>

      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  )
}
