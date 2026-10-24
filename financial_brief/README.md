# Ledger

The current product guide is [the repository README](../README.md).

- [Setup and deployment](../SETUP.md)
- [Agent setup/handoff](../AGENTS.md)
- [LLM registry and task routing](../docs/agent/LLM_ROUTING.md)
- [Architecture](../docs/agent/ARCHITECTURE.md)
- [Operations](../docs/agent/OPERATIONS.md)
- [Evaluation and limitations](../docs/agent/EVALUATION.md)

Run `.venv-brief/bin/python -m financial_brief.server` from the repository root after
choosing/configuring providers. Open http://localhost:8422. There is no frontend build
or mandatory local GPU. Hosted providers receive extracted text and can charge for it;
fully local task routing requires only the selected endpoints.
