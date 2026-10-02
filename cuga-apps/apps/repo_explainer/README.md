# Repo Explainer

Repo Explainer turns a GitHub repository page into a newcomer-friendly briefing.
It explains what the project does, who it is for, how to run it, and where a
first-time contributor can start, using only information fetched from the page.

## Quick start

```bash
pip install -r requirements.txt
python main.py --port 28837
```

Open <http://127.0.0.1:28837> in your browser.

## Example prompts

- `Explain https://github.com/cuga-project/cuga-agent`
- `What does https://github.com/psf/requests do?`
- `How do I get started with https://github.com/fastapi/fastapi?`
- `Is https://github.com/pallets/flask beginner-friendly?`
- `Summarize https://github.com/cuga-project/cuga-apps for a new contributor`

## Tools

The app uses the web MCP server's `fetch_webpage` tool to read the repository
page and its README. The agent requires the standard CUGA LLM environment
variables; see the repository README for provider configuration.
