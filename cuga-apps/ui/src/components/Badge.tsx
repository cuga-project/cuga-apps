type Color = 'green' | 'yellow' | 'red' | 'blue' | 'purple' | 'orange' | 'pink' | 'cyan' | 'indigo' | 'gray'

interface Props {
  label: string
  color?: Color
  small?: boolean
}

// Carbon-style tags: a translucent accent fill that reads on both the White
// and Gray 100 themes, with a 600-weight label and a faint accent border.
const COLOR_MAP: Record<Color, string> = {
  green:  'bg-green-500/10 text-green-600 border border-green-500/30',
  yellow: 'bg-yellow-500/10 text-yellow-600 border border-yellow-500/30',
  red:    'bg-red-500/10 text-red-600 border border-red-500/30',
  blue:   'bg-blue-500/10 text-blue-600 border border-blue-500/30',
  purple: 'bg-purple-500/10 text-purple-600 border border-purple-500/30',
  orange: 'bg-orange-500/10 text-orange-600 border border-orange-500/30',
  pink:   'bg-pink-500/10 text-pink-600 border border-pink-500/30',
  cyan:   'bg-sky-500/10 text-sky-700 border border-sky-500/30',
  indigo: 'bg-indigo-500/10 text-indigo-600 border border-indigo-500/30',
  gray:   'bg-tsurf2 text-t3 border border-tborder',
}

export default function Badge({ label, color = 'gray', small = false }: Props) {
  return (
    <span className={`inline-flex items-center rounded font-mono ${small ? 'text-xs px-1.5 py-0.5' : 'text-xs px-2 py-0.5'} ${COLOR_MAP[color]}`}>
      {label}
    </span>
  )
}
