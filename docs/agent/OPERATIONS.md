# Operations and troubleshooting

Follow [SETUP.md](../../SETUP.md) for installation/provider questions and production
commands. Primary app: port 8422. Original ABS page: 8420; HTTP MCP: 8421 by default.
Do not assume all are running or start duplicate processes.

## Limits

- Financial brief: five documents / 16 MB after ZIP expansion; 600,000 extracted
  characters, 64 overlapping sections and 250 PDF pages.
- ABS deal: 100 uploaded/expanded documents / 300 MB, including nested folders,
  HTML/TXT/PDF contracts/reports and CSV/XML ABS-EE tapes.
- No nested ZIPs or archive traversal/symlinks. Duplicate document paths fail.
- Two concurrent reports by default (`BRIEF_CONCURRENCY=1..4`), six admitted total,
  then a queue-full response. Default retained snapshot cap 40 (`BRIEF_MAX_JOBS`).
- Reports expire after one hour. Uploaded originals are deleted on completion/error.
- Document decoding runs separately with a timeout and Linux resource bounds.

The library is local/allowlisted: displaying six examples does not call an LLM or
fetch every document from SEC. Do not auto-generate all 50 examples during setup.

## Runtime verification

`GET /healthz` shows active task mappings/revision and concurrency, not connectivity.
Validate models with the registry CLI's optional `--test`. Check the actual web host's
network route for private models. A Mac-local tunnel is not reachable from another host.

Python's macOS certificate/proxy discovery after a Gunicorn fork can abort a worker.
OpenAI requests use certifi and explicit environment-proxy handling to avoid that path.
Do not disable TLS verification to work around a missing certificate bundle.

## Symptoms

- **Cannot reach OpenAI/local model:** inspect credential/endpoint configuration and
  the host's DNS/network route. Never print a key or replace a working server blindly.
- **Queued:** the job starts when a processing slot becomes available. Use another
  browser tab to submit another report; the admission bound still applies.
- **Encrypted PDF:** empty-password reading is attempted. A genuine user password
  is not guessed; request an unlocked copy. Sparse image-only pages produce warnings.
- **No cards/charts:** inspect exact-source and context verdicts. Matching a number
  is not enough to establish its period, scale or issuer. Do not force a visual.
- **Waterfall flagged:** preserve unknown inputs/missing clauses. Never silently hoist
  model fields or weaken rules to claim successful payments.
- **Report not found:** check browser/hostname/session, expiry, persisted signing key
  and data directory. Exports shown in an old tab may still be saved.

## Restarts and secrets

Use one process per data directory. On startup the app marks interrupted running/
queued work as errors and removes upload folders. Wait for active/queued jobs before
reloading Python. Frontend changes need refresh only; model-map changes need no restart.

Keep `BRIEF_DATA`, `.session-secret`, browser state, credentials and live registries out
of Git and the static directory. Use server-side environment variables or private key
files. Configuration and exports are never authorization to contact a new provider.
