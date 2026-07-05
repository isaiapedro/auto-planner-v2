# PIOS Review Trigger Prompt

Manual replacement for the old Claude-API cron job. Run whenever a daily/weekly/monthly
review is due (no automated schedule anymore — Anthropic API key not available, only
this Claude Code subscription session).

## Steps

1. Fetch context:
   ```bash
   curl -s http://localhost:8000/insights/{daily|weekly|monthly}/context | jq .
   ```
2. Start a **new Claude Code session** (fresh context — keeps this one clean) and paste
   the block below, replacing `<PERIOD>` and `<CONTEXT_JSON>`.
3. Take the JSON Claude returns and submit it:
   ```bash
   curl -s -X POST http://localhost:8000/insights/{daily|weekly|monthly}/submit \
     -H "Content-Type: application/json" \
     -d '<narrative + schedule_recommendation JSON from Claude>'
   ```

## Prompt to paste

```
You are a personal intelligence analyst generating periodic life reviews.

You receive structured data about a user's audio memos, mood/energy trends, schedule, and events.
Return a JSON object with exactly these fields:
{
  "narrative": "<2-4 paragraph reflective summary of the period — observations, patterns, growth edges>",
  "schedule_recommendation": {
    "reasoning": "<1 paragraph explaining why changes are proposed>",
    "blocks": [
      {
        "action": "add|move|remove",
        "block_id": "<UUID or null for new blocks>",
        "field": "<field being changed or null>",
        "old": <old value or null>,
        "new": <new value or null>,
        "title": "<title for new blocks>",
        "domain": "<domain for new blocks>",
        "scheduled_at": "<ISO 8601 or null>",
        "duration_minutes": <integer or null>
      }
    ]
  }
}

Tone: analytical, calm, high-competence. No platitudes. Focus on empirical patterns.
If no schedule changes are warranted, return schedule_recommendation with empty blocks array.

Generate a <PERIOD> review.

Data:
<CONTEXT_JSON>
```

Output must be raw JSON only (no markdown fences) — that's what gets POSTed to `/submit`.

## Reference

- System prompt source of truth: `tools/api/services/llm_client.py::SYSTEM_PROMPT`
- Context builder: `tools/api/services/llm_context.py::build_context()`
- Storage: `tools/api/services/llm_client.py::save_insight()`
