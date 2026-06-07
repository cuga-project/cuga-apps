/**
 * mcpServers.ts — the shared MCP servers that power every CUGA app.
 *
 * Seven servers are deployed to IBM Cloud Code Engine (see deploy_mcp.sh).
 * Each shares one image but runs as its own CE app named `cuga-apps-mcp-<id>`,
 * reachable at the streamable-HTTP `/mcp` endpoint. The eighth server
 * (invocable_apis) is local-dev only and is intentionally not listed here.
 *
 * The CE host hash + region are the same public values the apps use, so we
 * reuse them from deployment.ts rather than duplicating the strings.
 */
import { CE_PROJECT_HASH, CE_REGION } from './deployment'

export interface McpServer {
  /** server id — matches `cuga-apps-mcp-<id>` and mcp_servers/<id>/ */
  id: string
  /** display name */
  name: string
  /** local dev port (29100–29106) */
  port: number
  /** one-line purpose */
  blurb: string
  /** upstream data sources / libraries it wraps */
  sources: string[]
  /** the MCP tools it exposes */
  tools: string[]
  /** accent color key (Tailwind palette) */
  accent: 'blue' | 'emerald' | 'amber' | 'pink' | 'cyan' | 'violet' | 'rose'
}

/** Public Code Engine `/mcp` endpoint for a deployed server. */
export function mcpServerUrl(id: string): string {
  return `https://cuga-apps-mcp-${id}.${CE_PROJECT_HASH}.${CE_REGION}.codeengine.appdomain.cloud/mcp`
}

/** The mcp-tool-explorer — browse + invoke every tool across all servers. */
export const TOOL_EXPLORER_URL =
  `https://cuga-apps-mcp-tool-explorer.${CE_PROJECT_HASH}.${CE_REGION}.codeengine.appdomain.cloud`

export const MCP_SERVERS: McpServer[] = [
  {
    id: 'web',
    name: 'Web',
    port: 29100,
    blurb: 'Search the live web, fetch pages, read feeds, pull video transcripts.',
    sources: ['Tavily', 'BeautifulSoup', 'RSS / feedparser', 'YouTube'],
    tools: ['web_search', 'fetch_webpage', 'fetch_webpage_links', 'fetch_feed', 'search_feeds', 'get_youtube_video_info', 'get_youtube_transcript'],
    accent: 'blue',
  },
  {
    id: 'knowledge',
    name: 'Knowledge',
    port: 29101,
    blurb: 'Encyclopedic + academic lookup across Wikipedia, arXiv and Semantic Scholar.',
    sources: ['Wikipedia', 'arXiv', 'Semantic Scholar'],
    tools: ['search_wikipedia', 'get_wikipedia_article', 'get_article_summary', 'get_article_sections', 'get_related_articles', 'search_arxiv', 'get_arxiv_paper', 'search_semantic_scholar', 'get_paper_references'],
    accent: 'violet',
  },
  {
    id: 'geo',
    name: 'Geo',
    port: 29102,
    blurb: 'Geocoding, points of interest, trails and weather for any location.',
    sources: ['Nominatim', 'Overpass', 'OpenTripMap', 'wttr.in'],
    tools: ['geocode', 'find_hikes', 'search_attractions', 'get_weather'],
    accent: 'emerald',
  },
  {
    id: 'finance',
    name: 'Finance',
    port: 29103,
    blurb: 'Live crypto and equity quotes.',
    sources: ['CoinGecko', 'Alpha Vantage'],
    tools: ['get_crypto_price', 'get_stock_quote'],
    accent: 'amber',
  },
  {
    id: 'code',
    name: 'Code',
    port: 29104,
    blurb: 'Static analysis of source — syntax checks, metrics, language detection.',
    sources: ['Python stdlib (ast)'],
    tools: ['check_python_syntax', 'extract_code_metrics', 'detect_language'],
    accent: 'cyan',
  },
  {
    id: 'local',
    name: 'Local',
    port: 29105,
    blurb: 'Host telemetry and on-box audio transcription.',
    sources: ['psutil', 'faster-whisper'],
    tools: ['get_system_metrics', 'get_system_metrics_with_alerts', 'list_top_processes', 'check_disk_usage', 'find_large_files', 'get_service_status', 'transcribe_audio'],
    accent: 'rose',
  },
  {
    id: 'text',
    name: 'Text',
    port: 29106,
    blurb: 'Document extraction, token counting and chunking for RAG pipelines.',
    sources: ['docling', 'tiktoken'],
    tools: ['extract_text', 'extract_text_from_bytes', 'chunk_text', 'count_tokens'],
    accent: 'pink',
  },
]
