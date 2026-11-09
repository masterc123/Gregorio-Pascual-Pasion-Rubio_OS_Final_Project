"""Module 1 / Member 4: the grep-like text search command.

    grep [-i] [-n] [-v] [-c] [-o] [-E] [--groups] PATTERN [FILE...]

* Default (basic matching): a line matches when it CONTAINS the text PATTERN.
* -E (bonus): PATTERN is a regular expression. Python's `re` module is used
  (allowed by the project rules) so  .  [a-z]  *  +  ?  \\  and ( ) groups work.
* --groups (bonus, needs -E): also print each captured group of the first match.
* Exit status: 0 = at least one line selected, 1 = none, 2 = error.
"""
import re
import sys

from util import os_error_text

USAGE = "usage: grep [-i -n -v -c -o -E --groups] PATTERN [FILE...]"


def cmd_grep(args, ctx):
    flags = set()
    show_groups = False
    operands = []
    parsing_options = True
    for a in args:
        if parsing_options and a == "--":
            parsing_options = False
        elif parsing_options and a == "--groups":
            show_groups = True
        elif parsing_options and a.startswith("-") and len(a) > 1 and not a.startswith("--"):
            for ch in a[1:]:
                if ch not in "invcoE":
                    ctx.error(f"grep: invalid option -- '{ch}'")
                    return 2
                flags.add(ch)
        elif parsing_options and a.startswith("--"):
            ctx.error(f"grep: unrecognized option '{a}'")
            return 2
        else:
            operands.append(a)

    if not operands:
        ctx.error(USAGE)
        return 2
    pattern, files = operands[0], operands[1:]
    use_regex = "E" in flags
    if show_groups and not use_regex:
        ctx.error("grep: --groups needs -E (regular expressions)")
        return 2

    # Build the regex once. For plain text we escape it so every character is literal.
    try:
        rx = re.compile(pattern if use_regex else re.escape(pattern),
                        re.IGNORECASE if "i" in flags else 0)
    except re.error as e:
        ctx.error(f"grep: invalid regular expression '{pattern}': {e}")
        return 2

    needle = pattern.lower() if "i" in flags else pattern

    def matches(line):
        if use_regex:
            return rx.search(line) is not None
        # basic matching written by hand: does the line contain the text?
        return needle in (line.lower() if "i" in flags else line)

    # ---- read inputs
    sources, failed = [], False
    if files:
        for f in files:
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    sources.append((f, fh.read()))
            except OSError as e:
                ctx.error(f"grep: {f}: {os_error_text(e)}")
                failed = True
    else:
        sources.append((None, ctx.read_stdin()))

    multiple = len(files) > 1
    found_any = False
    for name, text in sources:
        count = 0
        for number, line in enumerate(text.splitlines(), 1):
            selected = matches(line)
            if "v" in flags:
                selected = not selected
            if not selected:
                continue
            count += 1
            found_any = True
            if "c" in flags:
                continue
            prefix = (f"{name}:" if multiple else "") + (f"{number}:" if "n" in flags else "")
            if "o" in flags and "v" not in flags:
                for m in rx.finditer(line):
                    if m.group(0):
                        ctx.println(prefix + m.group(0))
            else:
                ctx.println(prefix + line)
                if show_groups:
                    m = rx.search(line)
                    if m and m.groups():
                        for g, value in enumerate(m.groups(), 1):
                            ctx.println(f"    group {g}: {value}")
        if "c" in flags:
            ctx.println((f"{name}:" if multiple else "") + str(count))

    if failed:
        return 2
    return 0 if found_any else 1


# ------------------------------------------------- standalone use (no shell needed)
class _CliCtx:
    """Minimal stand-in for the shell's context so this file also runs by itself."""

    _cache = False

    def println(self, text=""):
        print(text)

    def error(self, text):
        print(text, file=sys.stderr)

    def read_stdin(self):
        """Text piped in (cat file | python3 grep_cmd.py word). Read once, only when needed."""
        if self._cache is False:
            self._cache = "" if sys.stdin.isatty() else sys.stdin.read()
        return self._cache


if __name__ == "__main__":
    sys.exit(cmd_grep(sys.argv[1:], _CliCtx()))
