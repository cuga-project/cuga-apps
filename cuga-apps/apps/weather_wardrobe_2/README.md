# Weather Wardrobe 2

## Port

**28071**

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Set required env vars (example: Anthropic)
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=<your-key>
export AGENT_SETTING_CONFIG=/path/to/settings.toml

# Run
python main.py --port 28842

# Open in browser
open http://127.0.0.1:28842
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Always | `anthropic` \| `openai` \| `rits` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Always | Model name for the chosen provider (e.g. `claude-sonnet-4-6`, `gpt-4o`) |
| `AGENT_SETTING_CONFIG` | Always | Path to the agent settings TOML file |
| `ANTHROPIC_API_KEY` | When `LLM_PROVIDER=anthropic` | Anthropic API key |
| `OPENAI_API_KEY` | When `LLM_PROVIDER=openai` | OpenAI API key |
| `RITS_API_KEY` | When `LLM_PROVIDER=rits` | IBM RITS API key |

## Example prompts

1. `What should I wear in Paris?`
2. `Do I need an umbrella in London tomorrow?`
3. `Outfit for Toronto this weekend`
4. `Is it shorts weather in Barcelona?`
5. `What to pack for 3 days in Tokyo?`

## Tools

| Tool | Description |
|---|---|
| `geocode` | Converts a place name, city, or address into latitude, longitude, and a canonical display name using OpenStreetMap Nominatim |
| `get_sunrise_sunset`  | Retrieves sunrise, sunset, solar noon, and day length for given coordinates and a date. Returns times in UTC.                                                                                                      |
| `find_hikes`          | Finds named hiking trails near specified coordinates using OpenStreetMap. Supports search radius, difficulty, and kid-friendly filters.                                                                            |
| `search_attractions`  | Finds nearby attractions using OpenStreetMap, filtering by category such as cultural, historic, natural, architecture, or sports. Returns names, distances, coordinates, and available website or Wikipedia links. |
| `convert_timezone`    | Converts a date and time between IANA time zones, accounting for daylight saving time. Returns the converted time, UTC offset, and whether the calendar date changes.                                              |
| `get_weather`         | Fetches current weather conditions and a three-day forecast for a specified city using wttr.in.                                                                                                                    |
| `get_public_holidays` | Retrieves public holidays for a specified country and year, including dates, local names, and holiday types, using Nager.Date.                                                                                     |

