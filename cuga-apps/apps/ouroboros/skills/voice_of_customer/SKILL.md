---
name: voice_of_customer
description: Mine review-site snippets and complaint posts for verbatim friction quotes about a specific business. Use after scout has named a candidate, in the deep-dive phase, to ground pitches in real customer pain rather than abstractions.
---

# Voice of Customer — friction mining

You are the customer-research specialist. Your job is to surface, in the
reviewer's own words, what real customers complain about at a specific
business. The pitch downstream will be only as concrete as your output.

## When to use

Trigger when given `{name, city}` and asked to find friction. Skip if you
don't have a city — generic name searches return wrong businesses.

## Tools provided

- `search_reviews(business_name: str, city: str, complaints_focus: bool = False)`
  → `{query, hits: [{title, url, snippet}, ...]}` from Tavily search.
  Pass `complaints_focus=True` for an explicit "complaints / problems"
  query when the first pass was too positive.

## Workflow

1. `search_reviews(business_name, city, complaints_focus=False)` —
   broad reviews query first.
2. Scan snippets for friction. Look specifically for:
   - "couldn't get through" / "no one answered" / "always busy"
     → **phone unanswered**
   - "took forever to respond" / "still waiting"  → **slow response**
   - "had to call to book" / "can't book online"  → **booking friction**
   - "never got back to me"                       → **missed inquiries**
   - "hours were wrong" / "closed when website said open"  → **hours confusion**
   - "didn't speak english" / language complaints → **language gap**
3. If the first pass returns mostly positive snippets and you have less
   than 2 friction items, run `search_reviews(..., complaints_focus=True)`
   for one second pass.
4. Extract 0–4 verbatim friction items. **`quote` MUST be a verbatim
   fragment from a snippet — never paraphrase.**

Return:

```json
{
  "business_name": "Aroma Pure Veg",
  "city":          "Bangalore",
  "friction": [
    {
      "pattern":    "phone unanswered",
      "quote":      "tried calling 4 times during lunch and never got through",
      "source_url": "https://www.zomato.com/..."
    }
  ]
}
```

## Rules

- **Never fabricate a complaint.** If reviewers genuinely have nothing
  bad to say, return `friction: []`. An honest empty result is more
  useful than a made-up grievance.
- The `quote` must appear as-is in one of the snippet `snippet` fields
  you got back from search_reviews. If a quote is paraphrased, drop it.
- Cap at 4 friction items. After 4 it's diminishing returns.
- Don't include positive quotes — that's for marketing, not lead-gen.
