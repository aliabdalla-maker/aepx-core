"""ADLC 'Validate' stage: static checks on what an agent produced, before a person approves it.

Each fenced code block in the answer is checked with the parser for its language. Nothing is
executed. The report is appended to the run result so the reviewer sees it next to the code.
"""
import ast
import json
import re

FENCE = re.compile(r"```([^\n`]*)\n(.*?)```", re.S)
LANGS = {"python": "python", "py": "python", "json": "json"}


def _check(lang: str, code: str) -> str | None:
    if lang == "python":
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return f"Python syntax error on line {exc.lineno}: {exc.msg}"
    elif lang == "json":
        try:
            json.loads(code)
        except ValueError as exc:
            return f"Invalid JSON: {exc}"
    return None


def validate_answer(text: str) -> dict:
    """Returns {"checked": n, "passed": n, "problems": [..], "skipped": n} for the fenced blocks."""
    checked = passed = skipped = 0
    problems: list[str] = []
    for i, m in enumerate(FENCE.finditer(text or ""), start=1):
        info = m.group(1).strip().split()
        lang = LANGS.get(info[0].lower()) if info else None
        if lang is None:
            skipped += 1
            continue
        checked += 1
        error = _check(lang, m.group(2))
        if error:
            label = next((w for w in info[1:] if "." in w), f"block {i}")
            problems.append(f"{label}: {error}")
        else:
            passed += 1
    return {"checked": checked, "passed": passed, "problems": problems[:20], "skipped": skipped}


def report(text: str) -> str:
    r = validate_answer(text)
    if not r["checked"]:
        return ""
    lines = [f"\n\n---\nAutomated validation: {r['passed']}/{r['checked']} code blocks passed static checks"
             + (f" ({r['skipped']} not checked)" if r["skipped"] else "") + "."]
    lines += [f"- {p}" for p in r["problems"]]
    return "\n".join(lines)
