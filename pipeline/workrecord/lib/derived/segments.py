"""Document segments: the served form of an entry's text
document (the segment feed, math adoption round).

The backend serves a markdown document as structured
segments — blocks of text runs plus math nodes — so the
frontend renders display-ready content and never parses
(document segments contract: the math-component study,
approved 2026-11-13, form (b)). A math node carries
{source, display, valid}: the TeX source as written, the
display flag, and the served validity state. Validity is
decided HERE, at serve time, by tex_valid below — the
renderer's fallback is driven by this flag, never by a
render outcome.

Math syntax is the plan syntax standard, ported from the
original viewer's extraction scanner (viewer client
sections/plans/math.ts): `$...$` inline, `$$...$$`
display, no other delimiter forms. Inline code spans and
`\$` are never math, and the inline heuristic (no
surrounding spaces inside the span, no digit right after
the closing `$`) keeps prices like "$5 and $10" literal.

Block grammar is deliberately small — ATX headings,
paragraphs, fenced code, lists, and a standalone display
equation (with its document-served equation number, a
trailing `(n)`, riding the math block). Anything else
folds into paragraph text; no source text is dropped.
"""

import re

# ----------------------------------------------------------------
# TeX validity (the served state)
# ----------------------------------------------------------------

_TWO_GROUP = {"frac", "dfrac", "tfrac", "binom", "dbinom",
              "tbinom", "overset", "underset"}
_COMMAND_RE = re.compile(r"\\([a-zA-Z]+)")


def _skip_ws(text, i):
    while i < len(text) and text[i] in " \t\n":
        i += 1
    return i


def _consume_group(text, i):
    """Consume one TeX argument at i: a balanced {...}
    group, a [...] group (for \\sqrt's optional argument
    the caller handles brackets itself), a \\command, or a
    single character. Returns the index past it, or None
    when no argument is present."""
    i = _skip_ws(text, i)
    if i >= len(text):
        return None
    ch = text[i]
    if ch == "{":
        depth = 0
        j = i
        while j < len(text):
            c = text[j]
            if c == "\\":
                j += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return None
    if ch == "\\":
        m = _COMMAND_RE.match(text, i)
        return m.end() if m else i + 2
    return i + 1


def tex_valid(source) -> bool:
    """The served validity rule: structural soundness of
    the TeX source. Invalid when the source is empty,
    braces are unbalanced, a \\begin/\\end environment is
    unclosed or mismatched, or a command that requires
    brace-group arguments (the \\frac family, \\sqrt) is
    missing one. Anything else is served valid; the
    renderer's own no-throw guard covers the residue."""
    text = source.strip()
    if not text:
        return False
    depth = 0
    envs = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            m = _COMMAND_RE.match(text, i)
            if not m:
                i += 2
                continue
            name = m.group(1)
            i = m.end()
            if name in ("begin", "end"):
                j = _skip_ws(text, i)
                if j >= len(text) or text[j] != "{":
                    return False
                end = _consume_group(text, j)
                if end is None:
                    return False
                env = text[j + 1:end - 1]
                if name == "begin":
                    envs.append(env)
                elif not envs or envs.pop() != env:
                    return False
                i = end
                continue
            if name in _TWO_GROUP:
                for _ in range(2):
                    nxt = _consume_group(text, i)
                    if nxt is None:
                        return False
                    i = nxt
                continue
            if name == "sqrt":
                j = _skip_ws(text, i)
                if j < len(text) and text[j] == "[":
                    close = text.find("]", j)
                    if close == -1:
                        return False
                    i = close + 1
                nxt = _consume_group(text, i)
                if nxt is None:
                    return False
                i = nxt
                continue
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0 and not envs


# ----------------------------------------------------------------
# Inline runs (the extraction scanner, ported)
# ----------------------------------------------------------------

def segment_runs(text) -> list:
    """Split one block's text into runs: text runs, code
    runs (backtick spans), and math nodes. Mirrors the
    original scanner's rules exactly, including the
    inline-price heuristic."""
    runs = []
    buf = []

    def flush():
        if buf:
            runs.append({"type": "text",
                         "text": "".join(buf)})
            buf.clear()

    def math(source, display):
        flush()
        runs.append({"type": "math", "source": source,
                     "display": display,
                     "valid": tex_valid(source)})

    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and text[i + 1:i + 2] == "$":
            buf.append("$")
            i += 2
            continue
        if ch == "`":
            n = 1
            while text[i + n:i + n + 1] == "`":
                n += 1
            ticks = "`" * n
            close = text.find(ticks, i + n)
            if close == -1:
                buf.append(ticks)
                i += n
            else:
                flush()
                runs.append({"type": "code",
                             "text": text[i + n:close]})
                i = close + n
            continue
        if ch == "$" and text[i + 1:i + 2] == "$":
            close = text.find("$$", i + 2)
            tex = "" if close == -1 else text[i + 2:close]
            if close != -1 and tex.strip():
                math(tex, True)
                i = close + 2
            else:
                buf.append("$$")
                i += 2
            continue
        if ch == "$":
            line_end = text.find("\n", i)
            bound = len(text) if line_end == -1 else line_end
            close = text.find("$", i + 1)
            tex = "" if close == -1 else text[i + 1:close]
            after = "" if close == -1 else text[close + 1:close + 2]
            if (close != -1 and close < bound and tex != ""
                    and not tex[0].isspace()
                    and not tex[-1].isspace()
                    and not after.isdigit()):
                math(tex, False)
                i = close + 1
            else:
                buf.append("$")
                i += 1
            continue
        buf.append(ch)
        i += 1
    flush()
    return runs


# ----------------------------------------------------------------
# Blocks
# ----------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_NUMBER_RE = re.compile(r"^\(\d+\)$")


def _math_block(runs):
    """A paragraph whose runs are a single display math
    node (plus at most its `(n)` equation number as a
    text run) is a math block: the number is document
    content and rides the block, where the renderer
    draws it in the display well's number slot."""
    nodes = [r for r in runs if r["type"] == "math"]
    texts = [r for r in runs if r["type"] == "text"]
    if len(nodes) != 1 or not nodes[0]["display"]:
        return None
    if len(runs) - len(nodes) - len(texts) != 0:
        return None
    number = None
    for t in texts:
        stripped = t["text"].strip()
        if not stripped:
            continue
        if number is None and _NUMBER_RE.match(stripped):
            number = stripped
        else:
            return None
    node = nodes[0]
    block = {"kind": "math", "source": node["source"],
             "display": True, "valid": node["valid"]}
    if number is not None:
        block["number"] = number
    return block


def segment_document(text) -> list:
    """Segment a markdown document into blocks (see the
    module docstring for the grammar)."""
    blocks = []
    lines = text.split("\n")
    para = []

    def flush_para():
        if not para:
            return
        body = "\n".join(para).strip()
        para.clear()
        if not body:
            return
        runs = segment_runs(body)
        block = _math_block(runs)
        if block is not None:
            blocks.append(block)
        else:
            blocks.append({"kind": "paragraph",
                           "runs": runs})

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_para()
            language = stripped[3:].strip() or None
            code = []
            i += 1
            while i < len(lines) \
                    and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # the closing fence (or EOF)
            blocks.append({"kind": "code",
                           "text": "\n".join(code),
                           "language": language})
            continue
        if not stripped:
            flush_para()
            i += 1
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush_para()
            blocks.append({
                "kind": "heading",
                "level": len(heading.group(1)),
                "runs": segment_runs(heading.group(2).strip()),
            })
            i += 1
            continue
        item = _LIST_RE.match(line)
        if item:
            flush_para()
            ordered = item.group(2)[0].isdigit()
            items = []
            while i < len(lines):
                m = _LIST_RE.match(lines[i])
                if not m:
                    break
                items.append(segment_runs(m.group(3).strip()))
                i += 1
            blocks.append({"kind": "list",
                           "ordered": ordered,
                           "items": items})
            continue
        para.append(line)
        i += 1
    flush_para()
    return blocks
