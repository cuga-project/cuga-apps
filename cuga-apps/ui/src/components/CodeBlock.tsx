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
    <div className="relative group bg-[#161616] border border-[#393939] overflow-hidden">
      {/* Header — Carbon Gray 90 bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#393939] bg-[#262626]">
        <span className="text-xs text-[#8d8d8d] font-mono">{language}</span>
        <button
          onClick={handleCopy}
          className="text-xs text-[#8d8d8d] hover:text-[#f4f4f4] transition-colors px-2 py-0.5 hover:bg-[#393939]"
        >
          {copied ? '✓ copied' : 'copy'}
        </button>
      </div>
      {/* Code */}
      <pre className="p-4 overflow-x-auto text-[#f4f4f4] text-xs leading-relaxed whitespace-pre">
        {code}
      </pre>
    </div>
  )
}
