type Color = 'green' | 'yellow' | 'red' | 'blue' | 'purple' | 'orange' | 'pink' | 'cyan' | 'indigo' | 'gray'

interface Props {
  label: string
  color?: Color
  small?: boolean
}

const COLOR_MAP: Record<Color, string> = {
  green:  'bg-green-900/40 text-green-300 border border-green-800/50',
  yellow: 'bg-yellow-900/40 text-yellow-300 border border-yellow-800/50',
  red:    'bg-red-900/40 text-red-300 border border-red-800/50',
  blue:   'bg-blue-900/40 text-blue-300 border border-blue-800/50',
  purple: 'bg-purple-900/40 text-purple-300 border border-purple-800/50',
  orange: 'bg-orange-900/40 text-orange-300 border border-orange-800/50',
  pink:   'bg-pink-900/40 text-pink-300 border border-pink-800/50',
  cyan:   'bg-cyan-900/40 text-cyan-300 border border-cyan-800/50',
  indigo: 'bg-indigo-900/40 text-indigo-300 border border-indigo-800/50',
  gray:   'bg-gray-800 text-gray-400 border border-gray-700',
}

export default function Badge({ label, color = 'gray', small = false }: Props) {
  return (
    <span className={`inline-flex items-center rounded font-mono ${small ? 'text-xs px-1.5 py-0.5' : 'text-xs px-2 py-0.5'} ${COLOR_MAP[color]}`}>
      {label}
    </span>
  )
}
