# ADR 003: Adopt Regex for Query Validation

**Date**: 2026-05-05
**Status**: Accepted

## Context

We use regex for query validation.

## Decision
We will use regex for query validation.

We rejected the alternatives for the following reasons:
* `AST + White List`: More stable but a little more difficult than regex. And we have readonly transaction to refuse all the DML/DDL, so, we choose the easiest way regex.

## Consequences

**Positive:**
* **Concurrency:** Easy. 
