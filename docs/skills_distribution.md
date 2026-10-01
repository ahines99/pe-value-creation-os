# Distributing the Agent Skills (PVC-076)

Current installation evidence: Claude Code 2.1.280 installed the six-skill plugin
locally from a detached `31ebfe9` checkout and connected to its stdio server.
A separate local `pvc-showcase` HTTP entry connected to the persisted Docker
workspace. These are agent-performed checks, not a human skill conversation.
See [showcase closeout](portfolio/showcase-closeout.md). Instructions and behavior
were checked against the installed CLI and
[Anthropic's marketplace documentation](https://code.claude.com/docs/en/plugin-marketplaces).

The six skills live in `skills/` and are versioned with the package (`pe_value_os.__version__`, mirrored in
`.claude-plugin/plugin.json`; a test keeps them equal). CI runs `python -m pe_value_os.skills_lint`, which fails if
a skill references a tool, metric or reference file that does not exist.

## Option 1: Claude Code plugin (recommended for analysts)

The repository is a Claude Code plugin: `.claude-plugin/plugin.json` (manifest), `skills/` (skills) and `.mcp.json`
(registers the MCP server over stdio via `uv run pvc mcp-stdio`, dev scope). A marketplace file is included.

The included marketplace source is `./`; it resolves the local checkout and does **not** select a release tag. For a reproducible installation, resolve an approved published tag (when available) or full reviewed commit SHA, create a detached checkout, and record the resolved SHA:

```bash
git clone <repository-url> pe-value-creation-os-<release>
cd pe-value-creation-os-<release>
git fetch --tags
git checkout --detach <approved-tag-or-full-commit-sha>
git rev-parse HEAD
uv sync --frozen --extra dev
```

Add that absolute checkout path to the client, rather than an unpinned default branch:

```text
/plugin marketplace add <absolute-path-to-detached-checkout>
/plugin install pe-value-creation-os@pvc-internal
```

Opening the checkout itself as a Claude Code project also registers the server from `.mcp.json`; the path defaults to the project directory when no plugin root is set.

If the client reports the server as failed to connect, check that `uv` is on the `PATH` the client inherits (`uv --version` in a fresh terminal). On Windows the uv installer places it in `%USERPROFILE%\.local\bin`; add that folder to the user `PATH` and restart the client. Running `uv run --extra server pvc mcp-stdio` from the checkout should start the server and wait for input.

For the deployed server, replace `.mcp.json` in your fork with an HTTP entry pointing at the Streamable HTTP
endpoint; Claude Code performs the OAuth flow against the fund identity provider (PVC-091).

## Option 2: project skills directory

Copy (or git-submodule) `skills/*` into a project's `.claude/skills/`. Update by pulling a tagged release.

## Option 3: Claude API / claude.ai

Zip each skill directory (`SKILL.md` plus `references/`) and upload it as a custom skill in your organisation's
settings or through the Skills API. Upload the version matching the deployed server.

## Release process

1. Change skills and tools together; run `PVC_ENV=dev python scripts/generate_skill_examples.py`. The current generator uses server-issued quantity references and writes its replay date. All six examples were replayed on September 27; this is scripted MCP evidence, not a human acceptance session.
2. CI: skills lint, tool schema snapshot, skills tests.
3. Bump `__version__` and `plugin.json` together, publish an approved release tag, and record its full commit SHA. Do not claim that the relative marketplace entry automatically follows it.
4. Install from the detached checkout above and record a human client smoke session (client version, tag, SHA, tools list, diagnostic output). Publication and a human installation have not yet been verified.
5. Updating requires a newly reviewed checkout/version and another recorded installation check. The manifest version alone is not an immutable source pin.
