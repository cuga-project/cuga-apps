import { useState, useEffect } from 'react'

export type Theme = 'warm' | 'dark'

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => {
    return (localStorage.getItem('theme') as Theme) || 'warm'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggle = () => setThemeState(t => t === 'warm' ? 'dark' : 'warm')

  return { theme, toggle }
}
