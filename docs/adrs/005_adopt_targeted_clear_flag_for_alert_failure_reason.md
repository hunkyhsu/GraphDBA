# ADR 005: Adopt Targeted Clear Flag for Alert Failure Reason

**Date**: 2026-05-25
**Status**: Accepted

## Context

The write MCP server updates rows in the `alerts` table as the agent graph moves through the workflow. Some alert fields are lifecycle markers:

* `escalation_reason` is set when the graph decides the alert is too complex or unsafe to continue automatically.
* `solved_at` is set when the alert is solved.
* `resolved_at` is set when the alert is externally resolved.
* `failure_reason` can be set during a failed attempt, but the graph may retry and later succeed.

This creates a partial update problem. A caller needs to express three different intents for nullable fields:

* Do not change the existing database value.
* Set a new non-null value.
* Clear the existing value back to `NULL`.

## Considered Options

### Static Update Fields

Static updates assign every nullable field directly from the input model.

```sql
failure_reason = $4
```

This is simple and explicit, but it is unsafe for partial updates. If a caller omits a field or passes `None`, the existing database value is overwritten with `NULL` even when the caller intended to leave it unchanged.

### `COALESCE` Partial Updates

`COALESCE` makes `NULL` mean "leave the existing value unchanged".

```sql
failure_reason = COALESCE($4, failure_reason)
```

This is a good default for most optional update fields because omitted values do not erase existing data. The trade-off is that callers can no longer intentionally clear a field to `NULL`, because `NULL` has already been assigned the meaning "do not update".

### `CASE` with Clear Flags

A clear flag separates "omitted" from "clear this field".

```sql
failure_reason = CASE
    WHEN $4 THEN NULL
    WHEN $5::text IS NOT NULL THEN $5
    ELSE failure_reason
END
```

This supports all three update intents. The trade-off is API complexity: every clearable field needs an additional boolean flag, and too many flags make the MCP tool schema noisier for agents and callers.

## Decision

We will use `COALESCE` for normal optional alert fields, and add a clear flag only for `failure_reason`.

`failure_reason` is the only alert field in the current workflow that needs to be cleared after it is set. A retry path can set `failure_reason` during a failed validation or diagnostic attempt, then later succeed. In that case, the stale failure reason must be removed.

Other nullable fields do not need clear flags:

* `escalation_reason` is terminal for the graph path that sets it.
* `solved_at` is a write-once completion timestamp.
* `resolved_at` is a lifecycle timestamp and should not be cleared by normal retry logic.

The update model should therefore include:

```python
failure_reason: str | None = None
clear_failure_reason: bool = False
```

And the SQL should handle only `failure_reason` with `CASE`:

```sql
failure_reason = CASE
    WHEN $clear_failure_reason THEN NULL
    WHEN $failure_reason::text IS NOT NULL THEN $failure_reason
    ELSE failure_reason
END
```

Fields such as `escalation_reason`, `solved_at`, and `resolved_at` can continue to use `COALESCE`.

## Consequences

**Positive:**
* Keeps partial updates safe by default.
* Allows retry-success paths to clear stale `failure_reason`.
* Avoids adding unnecessary clear flags to fields that are effectively terminal or write-once.
* Keeps the MCP tool schema easier for agents to use.

**Negative:**
* `failure_reason` has special update semantics that must be documented and tested.
* If future workflow paths require clearing other nullable fields, new clear flags may need to be added intentionally.
