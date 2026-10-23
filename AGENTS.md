# Setting up servicer-report-reader (instructions for coding agents)

You are helping someone run this project. It takes an auto-loan ABS deal's documents (monthly servicer reports,
the deal contracts, loan tapes, a .zip of them, or an EDGAR link) and builds one report: each servicer report's
figures with arithmetic checks, the contract's payment waterfall run and compared line by line with what the servicer
paid, and loan-tape statistics reconciled to the pool balance. Every figure or line either passes or is flagged with
the reason. Follow these steps in order and ask the user only where a step says so.

## 1. Check the basics
- `python3 --version` must be 3.10 or newer. The core needs no packages; `pip install pypdf` only for PDF reports,
  `pip install anthropic` only for the Anthropic API backend.
- Example reports are stored with Git LFS. If `examples/*.htm` are tiny pointer files, run `git lfs install && git lfs pull`.
- Run `python3 -m reader.selftest`. It needs no model and must print `ok: ...`. If it fails, stop and report it.

## 2. Ask the user where the model should run
Ask once, offering the four ways in [STARTUP.md](STARTUP.md) (recommend the first two: documents stay on their own
hardware). Follow that file for the chosen way. For a link, ask for the URL, the model name and, if a tunnel is
needed, the SSH login; never guess them. For an API key, ask the user to set the variable themselves; never ask them to
paste a key into the chat. Ways 3 and 4 send documents to an outside service: say so before using them.
"<backend flags>" below means the flags of the chosen way, e.g. `--backend link --url ... --model ...`.

## 3. Try one example
```
python3 -m reader.extract examples/carmax-2024-1__2026-07-31.htm examples/carmax-2024-1__2026-08-31.htm <backend flags> --out out/
```
Compare `out/*.json` with `examples/*.expected.json` (rule-checked answers). Report how many figures match and how
many were flagged. A flagged figure is the system working, not a failure: it was not trusted.

To try a whole deal (contracts + reports + loan tape, checked against each other), use the bundled example:
```
python3 -m reader.deal examples/santander-drive-2024-1-deal/* <backend flags> --out deal.json
```
or an EDGAR trust. Links to sec.gov need a contact in the User-Agent: ask the user for a name and email and
`export SEC_USER_AGENT="Name email"`. Then:
```
python3 -m reader.deal --link "CIK 2003263" <backend flags> --out deal.json
```
This downloads the deal's contracts, its latest two servicer reports and its loan tape. Reading the contract into a
waterfall takes a few minutes per deal on a local 27B model.

## 4. Start the page
```
python3 app.py <backend flags>
```
Then tell the user to open http://localhost:8420 and drop files, a .zip, or paste an EDGAR link. The model is fixed
by the start flags; to change it, restart the server. For access from other devices, see STARTUP.md.

## If the user asks to use this as an MCP server
When the user says something like "set this up as an MCP server" (in Claude Code, Codex or Claude Desktop):
1. Clone the repo if it isn't local yet (`git clone https://github.com/aka-vm/servicer-report-reader`), and use the
   absolute path of `mcp_server.py` below.
2. `python3 -m pip install mcp`, then check `python3 -c "import mcp"` works with the same `python3` you will register.
3. Ask where the model runs (step 2 above, STARTUP.md section 1) and turn the answer into backend flags.
4. Ask for a name and email for SEC downloads (EDGAR links), unless the user says they will only use local files.
5. Register it for the assistant you are running in:
   - Claude Code: `claude mcp add deal-report -e SEC_USER_AGENT="<name email>" -- python3 <abs path>/mcp_server.py <backend flags>`
   - Codex: `codex mcp add deal-report --env SEC_USER_AGENT="<name email>" -- python3 <abs path>/mcp_server.py <backend flags>`
   - Claude Desktop: add the same command under `mcpServers` in
     `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) and tell the user to restart the app.
6. Tell the user the tools appear in a new session, and to ask e.g. "Build a deal report for CIK 2003263" or
   "Make a deal report from the files in <folder>".
The Claude web and mobile apps cannot run local servers: for them, follow STARTUP.md section 3 (HTTP mode behind an
HTTPS tunnel, added as a custom connector).

## Rules when changing code
- Never edit `reader/checks.py` to make a flag go away on one report. A check must hold for every issuer;
  after any change, `python3 -m reader.selftest` must still pass (it fails if a check fires on a correct answer).
- Keep the model's job to reading, not arithmetic: totals and precision are fixed in code (`checks.finalize`, `checks.exact`).
- Keep temperature 0 and the JSON schema on every backend.
