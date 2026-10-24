# Agent instructions — Ledger / Deal Report Reader

Read this file first. Existing user instructions and choices take precedence; do not
ask for model selection or permission again when the conversation already provides it.

## Context map

- [Architecture](docs/agent/ARCHITECTURE.md): app modes, files and data flow.
- [LLM routing](docs/agent/LLM_ROUTING.md): registry, task keys, providers and credentials.
- [Operations](docs/agent/OPERATIONS.md): startup, hosting, limits and troubleshooting.
- [Evaluation](docs/agent/EVALUATION.md): source checks, independent review and known limits.
- [Handoff](docs/agent/HANDOFF.md): current implementation and continuation notes.
- [Setup](SETUP.md), [README](README.md), [original CLI/MCP](STARTUP.md).

## When setting up for someone

1. Check Python >=3.10, create `.venv-brief`, install `requirements-brief.txt`, install/
   pull Git LFS if needed, and run `python3 -m reader.selftest` plus unit tests.
   Stop and fix failed checks before calling a model.
2. **Ask which LLM provider(s)/models they want**, unless already established. Offer
   local machine/Ollama, their remote private OpenAI-compatible server, OpenAI API,
   another compatible hosted provider, or a mix. Ask whether one model should handle
   all tasks or whether they want separate simple/heavy models.
3. For a server, establish its exact API URL, model ID, authentication and network
   access. Never guess them. Reuse a working endpoint/tunnel; do not replace it.
4. Hosted providers receive document text and can incur charges: explain before
   using them. Ask the person to set credential environment variables or private key
   files themselves. Never request keys in chat, print them, or embed them in JSON.
5. Create ignored `llm-config.json` from the example and tailor registry/task mappings
   to the answers. Fully local routing must work without an OpenAI key. Validate the
   file; a connection test makes one small request per selected LLM.
6. Check `/healthz` for an existing web instance; start `.venv-brief/bin/python -m
   financial_brief.server` if absent. Tell them to open http://localhost:8422.
   Try a chosen document, not every library example automatically.
7. Use SETUP.md for hosting, stable session secrets and reverse proxy configuration.

## When changing code

- Preserve arithmetic/source checks. Never edit `reader/checks.py` merely to make a
  report pass. The no-model self-test must continue to pass.
- Keep arithmetic, pooling, precision and loan-tape aggregation in code, not the LLM.
- Keep schemas on every backend. Use temperature 0 where supported; GPT-5 nano/mini
  and Luna reasoning models use supported effort settings and omit temperature.
- Do not repair PDF numbers by guessing or silently transcribe unreadable images.
  Preserve quarter/annual, group/segment, reported/adjusted, units, signs and speakers.
- Fail closed on missing/unsupported review verdicts. Missing review is not proof of
  a wrong figure. Never depict a failed waterfall as verified.
- Tests use fake calls unless explicitly doing live evaluation. Do not add network
  calls or API keys to ordinary CI. Record which model/config generated live artifacts.
- Registry edits are read per job; changing Python needs a safe restart. Never reload
  active/queued work just to apply frontend or registry changes.
- Never commit `.brief-data`, local model registries, API keys, browser-session state,
  private user uploads or private generated reports. Public example assets are allowlisted.

## Independent review workflow

The current user requested **agy models**, with **Gemini Flash as coordinator**,
for independent report review. Do not replace this with session subagents. Run the
review CLI described in the evaluation guide; preserve actual reviewer IDs and any
quota/format fallbacks. Treat reviewer claims and scores critically against sources.

## Original CLI/MCP

The original workflow remains available. For local stdio MCP or HTTP, follow
STARTUP.md and the user's chosen backend. SEC downloads need a supplied name/email
in `SEC_USER_AGENT`; never invent that identity. Local bundled examples do not need it.
Do not send email/Slack messages or publish content as part of setup unless authorized.
