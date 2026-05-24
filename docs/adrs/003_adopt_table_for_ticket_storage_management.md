# ADR 003: Adopt Table for Ticket Storage Management

**Date**: 2026-05-05
**Status**: Accepted

## Context

We use database tables to storage the tickets for managment.

## Decision
We will use table for tickets storage management.

We rejected the alternatives for the following reasons:
* `redis`: Need a extra component redis and the query is more flexible than SQL.
* `file system`: Unsuitable at concurrency and server problems.
* `in-memory`: No persistency.

## Consequences

**Positive:**
* **Concurrency:** The transactions and locks in database, which are fixed, could protest the safety of tickets when multipe write MCP servers try to create/modify tickets. 
* **Persistency:** Tickets must persist until approved or executed by a DBA. Database tables is the most reliable solution. 
* **Observation:** Database tables make it easy to query the historial tickets' statements using SQL.