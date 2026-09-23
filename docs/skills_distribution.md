# Distributing the Agent Skills (PVC-076)

The six skills live in `skills/` and are versioned with the package (`pe_value_os.__version__`, mirrored in
`.claude-plugin/plugin.json`; a test keeps them equal). CI runs `python -m pe_value_os.skills_lint`, which fails if
a skill references a tool, metric or reference file that does not exist.

## Option 1: Claude Code plugin (recommended for analysts)

The repository is a Claude Code plugin: `.claude-plugin/plugin.json` (manifest), `skills/` (skills) and `.mcp.json`
(registers the MCP server over stdio via `uv run pvc mcp-stdio`, dev scope). A marketplace file is included.

```text
/plugin marketplace add <git URL or local path of this repository>
/plugin install pe-value-creation-os@pvc-internal
```

For the deployed server, replace `.mcp.json` in your fork with an HTTP entry pointing at the Streamable HTTP
endpoint; Claude Code performs the OAuth flow against the fund identity provider (PVC-091).

## Option 2: project skills directory

Copy (or git-submodule) `skills/*` into a project's `.claude/skills/`. Update by pulling a tagged release.

## Option 3: Claude API / claude.ai

Zip each skill directory (`SKILL.md` plus `references/`) and upload it as a custom skill in your organisation's
settings or through the Skills API. Upload the version matching the deployed server.

## Release process

1. Change skills and tools together; run `python scripts/generate_skill_examples.py` to refresh worked examples.
2. CI: skills lint, tool schema snapshot, skills tests.
3. Bump `__version__` and `plugin.json` version; tag the release; the marketplace entry resolves to the tag.
