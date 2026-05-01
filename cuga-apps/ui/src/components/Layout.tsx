import { useTheme } from '../hooks/useTheme'

export default function Layout({ children }: { children: React.ReactNode }) {
  const { theme, toggle } = useTheme()

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-tbg">
      {/* Top bar */}
      <header className="h-16 flex-shrink-0 bg-tsurf border-b-2 border-tborder flex items-center px-8 shadow-sm gap-4">
        <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center text-base font-bold text-white shadow-sm">
          C
        </div>
        <span className="text-t1 font-bold text-lg tracking-tight">CUGA Apps</span>
        <div className="flex-1" />
        <button
          onClick={toggle}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-tsurf2 border border-tborder text-sm font-medium text-t2 hover:text-t1 hover:border-t3 transition-colors"
        >
          <span>{theme === 'warm' ? '☀️ Warm' : '🌙 Dark'}</span>
        </button>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}
