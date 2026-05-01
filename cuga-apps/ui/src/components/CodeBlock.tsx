import { useState } from 'react'

interface Props {
  code: string
  language?: string
}

export default function CodeBlock({ code, language = 'bash' }: Props) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="relative group rounded-lg bg-gray-950 border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800 bg-gray-900/50">
        <span className="text-xs text-gray-500 font-mono">{language}</span>
        <button
          onClick={handleCopy}
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-0.5 rounded hover:bg-gray-800"
        >
          {copied ? '✓ copied' : 'copy'}
        </button>
      </div>
      {/* Code */}
      <pre className="p-4 overflow-x-auto text-gray-300 text-xs leading-relaxed whitespace-pre">
        {code}
      </pre>
    </div>
  )
}
