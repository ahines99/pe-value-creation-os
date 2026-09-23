"""Skill lint (PVC-075). Run: python -m pe_value_os.skills_lint [skills_dir]

Checks every skills/<name>/SKILL.md:
- frontmatter has `name` (matches the directory, lowercase letters/digits/hyphens, <= 64 chars) and a
  `description` (<= 1024 chars);
- every tool the skill calls (`tool_name(`) exists on the MCP server, unless listed in PLANNED with a ticket;
- every baseline metric named in backticks (`*_arr`, `*_cost`, `*_expense`, `*_cogs`) exists in the registry;
- every file under `references/` that the skill mentions exists.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import anyio

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "skills"
PLANNED: dict[str, str] = {}  # tool name -> ticket id, for tools a skill may reference before they ship
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TOOL_RE = re.compile(r"`([a-z][a-z0-9_]+)\(")
METRIC_RE = re.compile(r"`([a-z][a-z0-9_]*_(?:arr|cost|expense|cogs))`")
REF_RE = re.compile(r"`(references/[^`]+)`")
NOT_METRICS = {"annual_run_cost", "one_time_cost"}  # proposal cost fields, not baseline metrics


def _server_tools() -> set[str]:
    from mcp import Client

    from .mcp_server import build_server

    async def go() -> set[str]:
        async with Client(build_server()) as c:
            return {t.name for t in (await c.list_tools()).tools}

    return anyio.run(go)


def lint(skills_dir: Path = DEFAULT_DIR, tools: set[str] | None = None) -> list[str]:
    from .domain.baselines import REGISTRY

    tools = tools if tools is not None else _server_tools()
    problems: list[str] = []
    dirs = sorted(d for d in skills_dir.iterdir() if d.is_dir())
    if not dirs:
        return [f"No skills found in {skills_dir}"]
    for d in dirs:
        f = d / "SKILL.md"
        if not f.exists():
            problems.append(f"{d.name}: missing SKILL.md")
            continue
        text = f.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            problems.append(f"{d.name}: missing YAML frontmatter")
            continue
        meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
        name = meta.get("name", "").strip()
        desc = meta.get("description", "").strip()
        if name != d.name:
            problems.append(f"{d.name}: frontmatter name {name!r} does not match directory")
        if not NAME_RE.match(name):
            problems.append(f"{d.name}: invalid name {name!r}")
        if not desc:
            problems.append(f"{d.name}: missing description")
        elif len(desc) > 1024:
            problems.append(f"{d.name}: description longer than 1024 characters")
        body = text[m.end():]
        for tool in sorted(set(TOOL_RE.findall(body))):
            if tool not in tools and tool not in PLANNED:
                problems.append(f"{d.name}: references unknown tool {tool!r}")
        for metric in sorted(set(METRIC_RE.findall(body)) - NOT_METRICS):
            if metric not in REGISTRY:
                problems.append(f"{d.name}: references unknown baseline metric {metric!r}")
        for ref in sorted(set(REF_RE.findall(body))):
            if not (d / ref).exists():
                problems.append(f"{d.name}: referenced file {ref} does not exist")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    problems = lint(Path(args[0]) if args else DEFAULT_DIR)
    for p in problems:
        print(f"ERROR {p}")
    print(f"skills lint: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
