# Weather Wardrobe

A CUGA demo app that turns a live weather forecast into a practical, day-by-day outfit plan. Type any city — or a fuzzy query like "Toronto this weekend" — and the agent fetches the next 3 days of weather data and tells you exactly what to wear: layers, rain gear, and shoes.

## What it does

1. Calls the `get_weather` tool (from the shared `geo` MCP server — no API key required) for the city you name.
2. For each of the 3 forecast days it produces a one-line outfit: base layer / warm layer / outer shell, rain gear if precipitation is likely, and appropriate footwear.
3. Adds a **Heads-up** line highlighting the day that needs the most planning (e.g. a big temperature swing or afternoon rain).
4. Shows temperatures in °C, plus °F when the user appears to be in the US.

## How to run

```bash
# From the repo root
pip install -r apps/weather_wardrobe/requirements.txt

cd apps/weather_wardrobe
python main.py --port 28835
```

Then open <http://localhost:28835> in your browser.

## Example prompts

- What should I wear in Paris?
- Do I need an umbrella in London tomorrow?
- Outfit for Toronto this weekend
- Is it shorts weather in Barcelona?
- What to pack for 3 days in Tokyo?

## Tools used

| Tool | MCP server | Key needed? |
|------|-----------|-------------|
| `get_weather` | `geo` | No |

## Provider setup (optional — needed to get real answers)

Set these environment variables before starting the app:

```bash
# OpenAI
export LLM_PROVIDER=openai LLM_MODEL=gpt-4o OPENAI_API_KEY=sk-...
export AGENT_SETTING_CONFIG=../settings.openai.toml MODEL_NAME=gpt-4o

# Local Ollama (free)
export LLM_PROVIDER=ollama LLM_MODEL=gpt-oss:20b
export AGENT_SETTING_CONFIG=../settings.openai.toml
export OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama MODEL_NAME=gpt-oss:20b
```

Without a provider key the server still starts and the health check passes; clicking a button returns a "Missing credentials" message, which confirms the plumbing works.

## Health check

```bash
curl -s localhost:28835/health
# → {"ok":true}
```
