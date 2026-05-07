---
description: 'Output formatter: leads_board_formatter'
enabled: true
format_type: markdown
id: output_formatter_f24922c2
name: leads_board_formatter
priority: 50
triggers:
  case_sensitive: false
  keywords:
  - leads
  - lead board
  - shortlist
  - ranked
  operator: or
  target: agent_response
type: output_formatter
---

Always emit a fenced ```json``` block containing the leads schema documented in your SKILL.md, followed by a 2-paragraph prose summary that names the top 3 leads and their angle, ending with one line of next steps.