# Set up Ledger

See [AGENTS.md](AGENTS.md) for agent-assisted setup. Always reuse model choices already
provided in the conversation; ask only for missing information.

## 1. Install and check the project

Use Python 3.10 or newer. From the repository root:

```sh
python3 -m venv .venv-brief
.venv-brief/bin/pip install -r requirements-brief.txt
git lfs install
git lfs pull
python3 -m reader.selftest
.venv-brief/bin/python -m unittest discover -s tests -v
```

Install Git LFS first if `git lfs` is unavailable. Original ABS fixtures use LFS and
must contain documents rather than pointer files. The no-model self-test must pass
before trying inference. `pypdf`, `fonttools` and `certifi` are included: older PDF
fonts, permission-restricted documents and HTTPS trust all need reliable handling.

## 2. Establish provider and model choices

An assisting agent must ask, unless the answer is already supplied:

> Where should inference run: your local machine, your own remote LLM server,
> OpenAI's API, another OpenAI-compatible hosted provider, or a mixture?
> Would you like one model for every task or different models for simple and heavy work?

Hosted providers receive extracted document text and may charge for requests. Explain
this before sending documents. Do not make model requests before the provider/model
choice is established. Local or private endpoints are appropriate when document
confidentiality requires them.

For a private/hosted compatible server, establish its exact API base URL and served
model ID. Verify an available `/v1/models` response rather than inventing an ID.
For Ollama, establish its URL and installed model tag. Reuse working tunnels and
servers; do not restart a model server or create a new tunnel without a need.

For credentials, ask the person to set an environment variable or private key file.
Never ask them to paste a key into chat. Never print a key or write it into the registry.
Do not infer that an existing credential file authorizes a provider the user did not select.

## 3. Write the registry and task map

```sh
cp llm-config.example.json llm-config.json
```

Edit `llms` to register providers/models, and `tasks` to select their keys. The full
schema and local-only recipe are in [LLM_ROUTING.md](docs/agent/LLM_ROUTING.md).
The checked-in template is an example, not a decision on behalf of the person setting up.

The current template routes:

| Task | Default key |
|---|---|
| Simple section extraction and monthly inputs | `nano` — GPT-5 nano |
| Dense tables and recovery after poor extraction | `luna` — GPT-6 Luna |
| Brief writing, context review and follow-ups | `luna` |
| Contract payment rules | `luna` |

For a fully local setup, enable a `link`/`ollama` entry and assign all tasks to it.
Unused OpenAI entries do not require an OpenAI key and are not contacted.

For OpenAI, an entry's `api_key_env` is checked first, then its `api_key_file`.
If the file reference is omitted, `OPENAI_API_KEY_FILE` or `~/.openai_key` is used.
Set restrictive permissions on a key file, for example `chmod 600 /path/to/key`.
A `link`/`ollama` entry can omit credentials for an unauthenticated private endpoint.

```sh
# Validates syntax, task references and safe model metadata; no model requests.
.venv-brief/bin/python -m financial_brief.llm_config llm-config.json
# Optional: one small request for each selected LLM, using provider billing if applicable.
.venv-brief/bin/python -m financial_brief.llm_config llm-config.json --test
```

Select a different registry with `BRIEF_LLM_CONFIG=/absolute/path/models.json`.
Settings are snapshotted per job. New jobs see registry changes automatically;
changing providers during an active report does not split it across configurations.

## 4. Start the app

Check for an existing instance before starting another:

```sh
curl --fail http://localhost:8422/healthz
```

The response reports active routing and concurrency. It checks configuration and the
web process, not model reachability. If not running:

```sh
.venv-brief/bin/python -m financial_brief.server
```

Open http://localhost:8422. Choose a displayed example or upload your own files.
Use Financial brief for ordinary reports/proxy filings; use ABS deal report for a
folder/ZIP containing contracts, monthly reports and tapes. Large reports take time;
queued uploads start automatically. More than one browser tab can submit work.

No model request occurs when an example is merely loaded. Start with the smoke test
and one deliberately selected document; do not automatically run all 50 examples.

## 5. Deploy on a web host

Use **one process/instance per data directory**. The default is two active reports,
up to six admitted reports including queued jobs, one-hour retention and 40 retained
snapshots. Override concurrency with `BRIEF_CONCURRENCY` (1–4) and the snapshot cap
with `BRIEF_MAX_JOBS`. Each job's sections are read in order.

Provision a registry and credentials on the host. For a private model server, the
web host must have its own route: a tunnel on a laptop does not make the laptop's
localhost available to a remote host. For a secret file, set the entry's `api_key_file`
to its actual deployed path; do not leave a laptop-specific path in a production registry.

```sh
export BRIEF_LLM_CONFIG=/etc/ledger/llm-config.json
export BRIEF_DATA=/var/lib/ledger
export BRIEF_SECRET='<persisted randomly generated signing secret>'
export BRIEF_HTTPS=1
export BRIEF_PROXY=1
.venv-brief/bin/gunicorn --workers 1 --threads 8 --timeout 180 \
  --bind 127.0.0.1:8422 'financial_brief.server:create_app()'
```

Generate a signing secret with `python3 -c 'import secrets; print(secrets.token_hex(32))'`
and provision it through host secrets, not Git. Without `BRIEF_SECRET`, the app persists
an owner-only signing key in `BRIEF_DATA/.session-secret`. Preserve the signing secret
and data directory across deployments to preserve sessions.

Place an HTTPS reverse proxy in front, overwriting scheme headers:

```nginx
client_max_body_size 300m;
location / {
    proxy_pass http://127.0.0.1:8422;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 180s;
}
```

Use `BRIEF_HTTPS=1` only behind HTTPS. `BRIEF_PROXY=1` trusts one proxy's scheme
header. Do not expose Gunicorn directly. Keep report data outside the public/static
folders. See [operations](docs/agent/OPERATIONS.md) for limits and restart behavior.

## 6. Apply updates safely

Static HTML/CSS/JS changes require a browser refresh. Registry changes apply to new
jobs without restarting. Python changes require a restart/reload, after active and
queued work has finished. Startup recovery marks interrupted jobs as errors and
removes their uploads; do not reload a busy instance to apply a cosmetic change.

If a report is no longer accessible, use the same browser, hostname and session that
created it. Reports expire after an hour. Preserve visible exports before changing
sessions; refreshing cannot recreate deleted server data.

For original CLI/MCP setup, follow [STARTUP.md](STARTUP.md). SEC network downloads
require the user's supplied name/email in `SEC_USER_AGENT`; bundled SEC examples
are already local and need no SEC download or contact configuration.
