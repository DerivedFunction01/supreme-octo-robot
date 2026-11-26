#!/usr/bin/env python3
"""Living-dates component: living documents and code
comments carry no dates.

Living documents state the present truth and carry no
dates; code comments and docstrings carry no dates
either. Dates as data — string literals, fixtures,
specimens, served values — are not documents or comments
and pass. Code inside a document — fenced blocks and
inline code spans — is data in the same way: it is the
doc form of a string literal, never a finding. Comments
in config files are comments: the hash comment family
(a .gitignore file, TOML, YAML, CFG, INI) is in the
population, its values never a surface. Archives are
records: finished plans and run-log or dated-log
directories are excluded by directory convention only,
never by a register of exempt files.

Repo-scoped: the population is the whole tracked tree
from the repo root (git ls-files), which is why the leg
is declared once in the gate package's declaration and
executed over the repo root, never per package — a
per-package declaration would rescan the whole tree for
every package. Findings name rule, path, and line, never
matched content.

Usage (module form, from the pipeline root):
python3 -m gate.livingdates [--root DIR]
Exit: 0 = no findings; 1 = findings; 2 = usage error.
Standalone, the root defaults to the current directory;
under the runner, the repo root is passed in.
"""
from __future__ import annotations

import ast
import io
import os
import re
import sys
import tokenize
from pathlib import Path

from .linecap import enumerate_tracked_files, expand_equals

DOC_SUFFIXES = (".md",)
PYTHON_SUFFIXES = (".py",)
SCRIPT_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs")
SCAN_SUFFIXES = DOC_SUFFIXES + PYTHON_SUFFIXES + SCRIPT_SUFFIXES
CONFIG_SUFFIXES = (".toml", ".yaml", ".yml", ".cfg", ".ini")
CONFIG_NAMES = frozenset({".gitignore"})
ALL_SUFFIXES = SCAN_SUFFIXES + CONFIG_SUFFIXES

# Archive directory conventions: a path under a
# finished-plan directory, a run-log directory, or a
# dated-log directory is a record, not a living
# document. A directory named by a date is a dated log
# by its name alone.
ARCHIVE_DIR_NAMES = frozenset(
    {"run-log", "run-logs", "run_log", "run_logs",
     "dated-logs", "dated_logs"}
)
DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December|"
    r"Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|"
    r"Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)"
)
ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
SLASH_DATE_RE = re.compile(r"\b\d{4}/\d{2}/\d{2}\b")
MONTH_DAY_YEAR_RE = re.compile(
    r"\b" + _MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b"
)
DAY_MONTH_YEAR_RE = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r"\s+\d{4}\b")
MONTH_YEAR_RE = re.compile(r"\b" + _MONTH + r"\s+\d{4}\b")
PAREN_YEAR_RE = re.compile(r"\(\s*(?:19|20)\d{2}\s*\)")

DATE_LEGS = (
    ("living-dates/iso-date", ISO_DATE_RE),
    ("living-dates/iso-date", SLASH_DATE_RE),
    ("living-dates/month-date", MONTH_DAY_YEAR_RE),
    ("living-dates/month-date", DAY_MONTH_YEAR_RE),
    ("living-dates/month-date", MONTH_YEAR_RE),
    ("living-dates/date-parenthetical", PAREN_YEAR_RE),
)


def _is_archive(relpath: str) -> bool:
    parts = Path(relpath).parts
    dirs = parts[:-1]
    for index, part in enumerate(dirs):
        if part in ARCHIVE_DIR_NAMES or DATE_DIR_RE.match(part):
            return True
        if part == ".plans" and index + 1 < len(dirs):
            if dirs[index + 1] == "finished":
                return True
    return False


def _in_population(relpath: str) -> bool:
    path = Path(relpath)
    return path.suffix in ALL_SUFFIXES or path.name in CONFIG_NAMES


def population(root) -> list[str]:
    """Repo-relative tracked living docs and code files,
    archives excluded. The tracked enumeration is the
    line cap's (git ls-files --cached, with its walk
    fallback in a git-less tree)."""
    files: list[str] = []
    for relpath in enumerate_tracked_files(str(root)):
        if not _in_population(relpath) or _is_archive(relpath):
            continue
        if not os.path.isfile(os.path.join(str(root), relpath)):
            continue
        files.append(relpath)
    return files


def _date_findings(relpath: str, lineno: int, text: str):
    """[(rule, relpath, lineno)] — one per date leg the
    text matches; the matched content is never carried."""
    findings = []
    for rule, pattern in DATE_LEGS:
        if pattern.search(text):
            findings.append((rule, relpath, lineno))
    return findings


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _find_span_close(line: str, start: int, run: int) -> int | None:
    """End index of the backtick run of exactly ``run``
    closing a span."""
    index = start
    length = len(line)
    while index < length:
        if line[index] != "`":
            index += 1
            continue
        run_end = index
        while run_end < length and line[run_end] == "`":
            run_end += 1
        if run_end - index == run:
            return run_end
        index = run_end
    return None


def _mask_code_spans(line: str) -> str:
    """The line with inline code spans blanked to spaces.

    A span opens with a run of backticks and closes with
    a run of the same length; an unmatched run is literal
    text and stays. Length is preserved, so columns and
    line numbers hold.
    """
    chars = list(line)
    index = 0
    length = len(line)
    while index < length:
        if line[index] != "`":
            index += 1
            continue
        run_end = index
        while run_end < length and line[run_end] == "`":
            run_end += 1
        close = _find_span_close(line, run_end, run_end - index)
        if close is None:
            index = run_end
            continue
        for position in range(index, close):
            chars[position] = " "
        index = close
    return "".join(chars)


def _mask_doc_lines(text: str) -> list[str]:
    """Doc lines with fenced blocks and code spans
    blanked.

    Code inside a document is data — the doc form of a
    string literal — so fenced blocks (backtick or
    tilde) and inline code spans are blanked in place;
    prose on the same lines still scans, and line
    numbers hold.
    """
    masked: list[str] = []
    fence_char = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if fence_char:
            masked.append("")
            if stripped.startswith(fence_char * 3):
                fence_char = ""
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence_char = stripped[0]
            masked.append("")
            continue
        masked.append(_mask_code_spans(line))
    return masked


def _scan_doc(relpath: str, text: str):
    findings = []
    for lineno, line in enumerate(_mask_doc_lines(text), start=1):
        findings.extend(_date_findings(relpath, lineno, line))
    return findings


def _python_surfaces(text: str) -> list[tuple[int, str]]:
    """(line, text) pairs for comments and docstring
    lines."""
    surfaces: list[tuple[int, str]] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                surfaces.append((token.start[0], token.string))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return surfaces
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                   ast.AsyncFunctionDef)
        ):
            continue
        if not node.body or not isinstance(node.body[0], ast.Expr):
            continue
        value = node.body[0].value
        if not (isinstance(value, ast.Constant)
                and isinstance(value.value, str)):
            continue
        first = value.lineno
        last = value.end_lineno or first
        lines = text.splitlines()
        for lineno in range(first, last + 1):
            surfaces.append((lineno, lines[lineno - 1]))
    return surfaces


def _script_surfaces(text: str) -> list[tuple[int, str]]:
    """(line, text) pairs for TS/JS comments, lexed by
    hand.

    Strings and template literals are skipped so a date
    held as data never reads as a comment. Regex
    literals are not distinguished from division; a date
    inside a regex reads as comment text — the
    conservative direction.
    """
    surfaces: list[tuple[int, str]] = []
    index = 0
    lineno = 1
    length = len(text)
    while index < length:
        char = text[index]
        nxt = text[index + 1] if index + 1 < length else ""
        if char == "\n":
            lineno += 1
            index += 1
        elif char == "/" and nxt == "/":
            end = text.find("\n", index)
            if end == -1:
                end = length
            surfaces.append((lineno, text[index:end]))
            index = end
        elif char == "/" and nxt == "*":
            end = text.find("*/", index + 2)
            if end == -1:
                end = length - 2
            segment = text[index:end + 2]
            for offset, line in enumerate(segment.splitlines()):
                surfaces.append((lineno + offset, line))
            lineno += segment.count("\n")
            index = end + 2
        elif char in "'\"`":
            quote = char
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == "\n":
                    lineno += 1
                if text[index] == quote:
                    index += 1
                    break
                index += 1
        else:
            index += 1
    return surfaces


def _scan_code(relpath: str, text: str):
    if Path(relpath).suffix in PYTHON_SUFFIXES:
        surfaces = _python_surfaces(text)
    else:
        surfaces = _script_surfaces(text)
    findings = []
    for lineno, surface in surfaces:
        findings.extend(_date_findings(relpath, lineno, surface))
    return findings


def _hash_comment_surfaces(text: str) -> list[tuple[int, str]]:
    """(line, comment) pairs for hash-comment config
    files.

    A comment runs from an unquoted ``#`` to the end of
    the line. Quoted strings are data — a ``#`` inside
    one starts no comment — so the scan skips them with
    the same quote discipline as the script lexer;
    values are never a surface.
    """
    surfaces: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        quote = ""
        index = 0
        while index < len(line):
            char = line[index]
            if quote:
                if char == "\\" and quote == '"':
                    index += 2
                    continue
                if char == quote:
                    if quote == "'" and line[index + 1:index + 2] == "'":
                        index += 2
                        continue
                    quote = ""
                index += 1
                continue
            if char in "'\"":
                quote = char
                index += 1
                continue
            if char == "#":
                surfaces.append((lineno, line[index:]))
                break
            index += 1
    return surfaces


def _scan_config(relpath: str, text: str):
    if Path(relpath).name in CONFIG_NAMES:
        # Gitignore syntax: a comment is a line whose
        # first character is a hash; a hash later in a
        # line is pattern content, not a comment.
        surfaces = [
            (lineno, line)
            for lineno, line in enumerate(text.splitlines(), start=1)
            if line.startswith("#")
        ]
    else:
        surfaces = _hash_comment_surfaces(text)
    findings = []
    for lineno, surface in surfaces:
        findings.extend(_date_findings(relpath, lineno, surface))
    return findings


def scan(root):
    """(rows, failures, scanned) over the whole tracked
    tree at root (the repo root). There is no declaration
    mechanism: every finding is a failure, so rows and
    failures are the same list of (rule, relpath, lineno);
    scanned is the population's file count."""
    root = Path(root)
    files = population(root)
    findings = []
    for relpath in files:
        text = _read_text(root / relpath)
        if text is None:
            continue
        suffix = Path(relpath).suffix
        if suffix in DOC_SUFFIXES:
            findings.extend(_scan_doc(relpath, text))
        elif Path(relpath).name in CONFIG_NAMES \
                or suffix in CONFIG_SUFFIXES:
            findings.extend(_scan_config(relpath, text))
        else:
            findings.extend(_scan_code(relpath, text))
    findings.sort(key=lambda row: (row[1], row[2], row[0]))
    return findings, findings, len(files)


def render(rows, failures, scanned=None):
    """The leg's output block, the portability form:
    findings as rule, path, line with content withheld;
    the ok line names the population scanned."""
    lines = []
    for rule, relpath, lineno in rows:
        lines.append(f"{rule}: {relpath}:{lineno} (content withheld)")
    if failures:
        lines.append(f"living-dates: {len(failures)} finding(s)")
    elif scanned is not None:
        lines.append(f"living-dates: ok ({scanned} files scanned)")
    else:
        lines.append("living-dates: ok")
    return lines


def main(argv):
    root = os.getcwd()
    args = expand_equals(argv)
    while args:
        arg = args.pop(0)
        if arg == "--root" and args:
            root = os.path.abspath(args.pop(0))
        else:
            print("usage: livingdates.py [--root DIR]",
                  file=sys.stderr)
            return 2
    rows, failures, scanned = scan(root)
    for line in render(rows, failures, scanned):
        print(line)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
