# Wikipedia Fact Checker

A CUGA demo app that checks a claim against Wikipedia and returns one of three
verdicts: **Supported**, **Contradicted**, or **Not enough information**. Each
answer includes the deciding passage, a short explanation, and the source.

## Run

```bash
pip install -r requirements.txt
python main.py --port 28832
```

Open <http://127.0.0.1:28832>. An LLM provider is required for real answers;
see the repository README for supported provider settings.

## Example prompts

- The Great Wall of China is visible from space
- Einstein failed math at school
- Goldfish have a 3-second memory
- Mount Everest is the tallest mountain on Earth
- Bats are blind

## Tools

The app loads these tools from the shared `knowledge` MCP server:

- `search_wikipedia`
- `get_article_summary`
- `get_article_sections`
