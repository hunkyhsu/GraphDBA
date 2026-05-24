Root cause: single_external_call only catches Python exceptions. MCP's isError=True on CallToolResult is an
  application-level error that never raises, so it always came back as (result, None).
  - validation.py: Added elif result.isError check so tool errors are recorded in aggregate_output (which the LLM sees
  and will classify as inconclusive), and fixed the success branch to extract result.content[0].text instead of
  appending the raw object.
  - proposing.py: Added if result.isError check that returns FAILED with the error text before attempting to read
  ticket_id.
