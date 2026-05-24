# ADR 001: Adopt `uv` for Project Scaffolding and Dependency Management

**Date**: 2026-05-01
**Status**: Accepted

## Context

We are bootstrapping a new multi-agent DBA tunning system targeting PostgreSQL. The architeture is composed of Model Context Protocol(MCP), LangGraph, and various LangChain core libraries.


The Python ecosystem offers multiple tools for dependency and environment management, including `pip` (+ `venv`), `conda`, `poetry`, and `uv`. Because the project will involve rapid iteration and frequent updates to highly volatile AI and agentic frameworks, we require a project manager that provides:
* Strict dependency locking for production stability.
* Adherence to modern Python packaging standards (`pyproject.toml`).
* Rapid dependency resolution to minimize friction during development and testing on macOS.

## Decision
We will use **`uv`** as the exclusive tool for project scaffolding, virtual environment management, and dependency resolution.

We rejected the alternatives for the following reasons:
* `pip`: Lacks native lockfile support and automated environment management.
* `conda`: Overly heavy and optimized for complex data science/C-level dependencies rather than backend API/orchestration work.
* `poetry`: While mature and fully featured, its dependency resolution engine is significantly slower, which introduces unnecessary waiting time during the frequent package updates expected in this project.

## Consequences

**Positive:**
* **Speed:** Dependency installation and lockfile generation occur in milliseconds, drastically improving developer experience.
* **Standardization:** The project adheres to PEP 621 (`pyproject.toml`), ensuring compatibility with modern Python tooling.
* **Simplicity:** `uv` handles both the virtual environment (`.venv`) and package management under a single CLI, reducing setup steps for new environments or CI/CD pipelines.

**Negative:**
* **Ecosystem Maturity:** As a newer tool compared to `poetry`, we may occasionally encounter edge cases with highly obscure legacy packages, though this risk is minimal for modern AI libraries.
