# LLM registry and task map

Copy [llm-config.example.json](../../llm-config.example.json) to ignored `llm-config.json`.
Set `BRIEF_LLM_CONFIG` to choose a different file. A custom registry can also be named
by `llm_config` in the legacy ignored `.brief-config.json`.

The registry has `version: 1`, a `llms` object and a `tasks` object. Each LLM entry
has a provider and exact model ID. `openai` uses OpenAI's official Responses endpoint;
`link` uses a `base_url` ending in the compatible API prefix (typically `/v1`);
`ollama` uses its native host URL (typically `http://localhost:11434`).

## Current task defaults

| Task key | Purpose | Default |
|---|---|---|
| `extract` | Simple section figures/quotes/metadata | `nano` / GPT-5 nano |
| `extract_tables` | Numerically dense table sections | `luna` / GPT-6 Luna |
| `recover_extract` | Retry low-yield exact-source extraction | `luna` |
| `write` | Overview, highlights, risks | `luna` |
| `review` | Context/attribution review of claims and figures | `luna` |
| `answer` | Source-grounded follow-up questions | `luna` |
| `contract` | ABS payment-rule specification/repair | `luna` |
| `month_inputs` | Monthly waterfall inputs | `nano` |

The six base tasks (`extract`, `write`, `review`, `answer`, `contract`, `month_inputs`)
are required. Table/recovery routes are optional; when absent, extraction uses the
base extraction model without cross-model recovery. Additional named tasks can be
registered for extensions.

A task can simply reference a key (`"write": "local"`) or set options:

```json
"review": {"llm": "luna", "reasoning_effort": "medium", "max_output_tokens": 12000}
```

Options in the task map take precedence over caller defaults. GPT-5 nano supports
`minimal`; GPT-6 Luna supports `none`, `low`, `medium` and higher efforts, not `minimal`.
Effort does not apply to the compatible/native local backend unless that backend's
implementation supports it; temperature remains 0 there.

## Fully local example

```json
{
  "version": 1,
  "llms": {
    "local": {"provider": "link", "model": "your-model-id", "base_url": "http://127.0.0.1:8000/v1"}
  },
  "tasks": {
    "extract": "local", "extract_tables": "local", "recover_extract": "local",
    "write": "local", "review": "local", "answer": "local",
    "contract": "local", "month_inputs": "local"
  }
}
```

This does not load or require an OpenAI key. Local model IDs and endpoints must be
supplied/verified, not guessed. For Ollama, use provider `ollama` and its host URL.
For other hosted services, choose `link` only when the endpoint supports the
OpenAI-compatible streaming chat/schema interface. Keys stay server-side.

## Credentials and validation

Use `api_key_env` and/or `api_key_file`, never an embedded `api_key`. An OpenAI entry
checks its environment reference first, then its file reference. If the file field
is omitted, `OPENAI_API_KEY_FILE` or `~/.openai_key` is the fallback. An explicit file
field takes precedence over the global file environment variable. A compatible/local
entry without credential references sends no authorization header.

Provider URLs reject embedded credentials/query strings. Disabled entries cannot be
assigned to tasks. Unknown keys, unsupported providers and malformed budgets fail
validation rather than silently using another model. OpenAI keys are not sent to a
custom URL: use `link` with that endpoint's own credential reference.

```sh
.venv-brief/bin/python -m financial_brief.llm_config llm-config.json
.venv-brief/bin/python -m financial_brief.llm_config llm-config.json --test
```

The first command makes no requests. The second makes one small test per selected
LLM and can incur charges. Registry changes apply at job start; active jobs retain
their snapshot. Health/report metadata includes aliases, actual model IDs, provider
and revision, never resolved secrets or private endpoint URLs.

Legacy `.brief-config.json`, `BRIEF_MODEL*` and `BRIEF_BACKEND` settings remain
available when no registry is selected. Prefer the registry for new installations.
