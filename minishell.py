#!/usr/bin/env python3
"""
CmpSc 123 Project: MiniShell
Role: Member 1 — Shell Lead (Module 1: Shell Core & Final Command Integration)

Implements:
1. File and directory built-ins: pwd, cd, ls (with -l and -a), mkdir, rmdir,
   touch, cp, mv, rm, cat, echo, clear, history, help, exit, true, false.
2. Permissions: chmod (numeric octal modes like 755, 644) and ls -l permission view.
3. Redirection: >, >>, <, 2>, 2>>, and 2>&1 (plus 1>&2).
4. Pipes: Arbitrary multi-stage pipelines joined by | (e.g., ls | grep txt | cat).
5. Variables: Assignment (NAME=value), expansion ($NAME, ${NAME}, $?), and env.
6. Conditional execution: &&, ||, and ; (plus Bonus: if / then / elif / else / fi).
7. Error handling: Clear, non-crashing error messages for unknown commands,
   missing files, permission errors, and invalid arguments.
8. Text search (grep): Substring and Bonus regex matching (., [a-z], *, +, ?,
   backslash escaping, and capturing groups) on files or piped stdin.
9. Final Integration Dispatcher: Clean plug-in hooks for Module 2 (`sched`) and
   Module 3 (`deadlock`) so teammate modules integrate seamlessly.
"""

from __future__ import annotations

import datetime
import glob
import io
import os
try:
    import grp
except ImportError:
    grp = None  # type: ignore
try:
    import pwd as pwd_module
except ImportError:
    pwd_module = None  # type: ignore
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, TextIO, Tuple


# ============================================================================
# Data Structures for Parsing, Redirection, and Execution
# ============================================================================

@dataclass
class Redirection:
    """Represents a single I/O stream redirection operator and its target."""
    op: str          # '>', '>>', '<', '2>', '2>>', '2>&1', '1>&2'
    target: Optional[str] = None  # Filename for file redirects; None for 2>&1 / 1>&2


@dataclass
class SimpleCommand:
    """Represents a single command with arguments, variable assignments, and redirections."""
    args: List[str] = field(default_factory=list)
    assignments: List[Tuple[str, str]] = field(default_factory=list)
    redirections: List[Redirection] = field(default_factory=list)


@dataclass
class Token:
    """Lexer token preserving quote context so variable expansion and operators behave like Bash."""
    value: str
    is_operator: bool = False
    single_quoted: bool = False
    quoted: bool = False


# ============================================================================
# Teammate Integration Registry (Modules 2, 3, and 4)
# ============================================================================

class IntegrationRegistry:
    """
    Holds plug-in handlers for teammate modules:
      - Member 2 (Scheduler Lead): `sched` command
      - Member 3 (Resources Lead): `deadlock` command
      - Member 4 (Docs & Testing Lead): optional external `grep` override

    Teammates can either:
      1. Place `scheduler.py` (with `run_sched(args, stdin, stdout, stderr)`)
         and `deadlock.py` (with `run_deadlock(args, stdin, stdout, stderr)`)
         in the same directory, which MiniShell auto-discovers at startup; OR
      2. Register their function directly via `shell.registry.register("sched", fn)`.
    """

    def __init__(self) -> None:
        self.handlers: Dict[str, Callable[[List[str], TextIO, TextIO, TextIO], int]] = {}
        self._auto_discover_teammate_modules()

    def register(
        self,
        command_name: str,
        handler: Callable[[List[str], TextIO, TextIO, TextIO], int],
    ) -> None:
        """Register a teammate module handler for a top-level shell command."""
        self.handlers[command_name] = handler

    def _auto_discover_teammate_modules(self) -> None:
        """Attempt to import teammate modules (`scheduler.py`, `deadlock.py`) if present."""
        try:
            import scheduler  # type: ignore
            if hasattr(scheduler, "run_sched"):
                self.register("sched", scheduler.run_sched)
        except Exception:
            pass

        try:
            import deadlock  # type: ignore
            if hasattr(deadlock, "run_deadlock"):
                self.register("deadlock", deadlock.run_deadlock)
        except Exception:
            pass

        try:
            import report  # type: ignore
            if hasattr(report, "run_compare"):
                self.register("compare", report.run_compare)
        except Exception:
            pass


# ============================================================================
# Core MiniShell Implementation
# ============================================================================

class MiniShell:
    """
    Main MiniShell interpreter implementing Module 1 (Shell Core) and the
    integration layer for Modules 2 (`sched`), 3 (`deadlock`), and `grep`.
    """

    PROMPT = "minishell> "
    VALID_ALGOS = {"fcfs", "sjn", "sjf", "priority", "prio", "rr", "roundrobin", "round-robin", "mlq", "mlfq", "compare", "all", "show"}
    VALID_DEADLOCK_MODES = {"detect", "banker", "recover"}

    def __init__(self, interactive: bool = True) -> None:
        self.interactive = interactive
        self.running = True
        self.last_exit_code = 0
        self.variables: Dict[str, str] = dict(os.environ)
        self.history: List[str] = []
        self.prev_dir: Optional[str] = None
        # Simulated permission map so `chmod` + `ls -l` always reflect exact octal
        # modes even on filesystems that ignore POSIX chmod bits (e.g., FAT/NTFS/containers).
        self.permission_overrides: Dict[str, int] = {}
        self.registry = IntegrationRegistry()

        self.builtins: Dict[str, Callable[[List[str], TextIO, TextIO, TextIO], int]] = {
            "pwd": self.builtin_pwd,
            "cd": self.builtin_cd,
            "ls": self.builtin_ls,
            "mkdir": self.builtin_mkdir,
            "rmdir": self.builtin_rmdir,
            "touch": self.builtin_touch,
            "cp": self.builtin_cp,
            "mv": self.builtin_mv,
            "rm": self.builtin_rm,
            "cat": self.builtin_cat,
            "chmod": self.builtin_chmod,
            "echo": self.builtin_echo,
            "env": self.builtin_env,
            "export": self.builtin_export,
            "unset": self.builtin_unset,
            "grep": self.builtin_grep,
            "wc": self.builtin_wc,
            "sort": self.builtin_sort,
            "head": self.builtin_head,
            "tail": self.builtin_tail,
            "sched": self.builtin_sched_adapter,
            "deadlock": self.builtin_deadlock_adapter,
            "help": self.builtin_help,
            "history": self.builtin_history,
            "clear": self.builtin_clear,
            "true": self.builtin_true,
            "false": self.builtin_false,
            "exit": self.builtin_exit,
        }

    # ========================================================================
    # 1. Interactive Loop (REPL)
    # ========================================================================

    def run_repl(self) -> int:
        """Run the interactive shell prompt loop until `exit` or EOF."""
        try:
            import readline  # noqa: F401
        except ImportError:
            pass
        buffer: List[str] = []
        in_if_block = 0

        while self.running:
            try:
                prompt = self.PROMPT if in_if_block == 0 else "if...> "
                if self.interactive:
                    sys.stdout.write(prompt)
                    sys.stdout.flush()
                line = sys.stdin.readline()
                if not line:  # EOF (Ctrl+D)
                    if self.interactive:
                        sys.stdout.write("\n")
                    break

                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue

                # Track multi-line `if ... then ... else ... fi` blocks
                first_word = stripped.split()[0] if stripped.split() else ""
                if first_word == "if" and not self._has_closing_fi(stripped):
                    in_if_block += 1
                    buffer.append(stripped)
                    continue
                elif in_if_block > 0:
                    buffer.append(stripped)
                    if first_word == "if" and not self._has_closing_fi(stripped):
                        in_if_block += 1
                    if first_word == "fi" or stripped.endswith("; fi") or stripped.endswith(" fi"):
                        in_if_block -= 1
                    if in_if_block == 0:
                        full_cmd = "; ".join(buffer)
                        buffer.clear()
                        self.history.append(full_cmd)
                        self.last_exit_code = self.execute_line(full_cmd)
                    continue

                self.history.append(stripped)
                self.last_exit_code = self.execute_line(stripped)

            except KeyboardInterrupt:
                # Never crash on Ctrl+C; reset buffer and show fresh prompt
                sys.stdout.write("\n")
                buffer.clear()
                in_if_block = 0
                self.last_exit_code = 130
            except Exception as exc:
                # Defensive catch-all so the shell never crashes
                sys.stderr.write(f"minishell: unexpected error: {exc}\n")
                self.last_exit_code = 1

        return self.last_exit_code

    @staticmethod
    def _has_closing_fi(line: str) -> bool:
        """Check whether a single-line `if` statement already ends with `fi`."""
        tokens = re.split(r"[;\s]+", line.strip())
        return "fi" in tokens

    # ========================================================================
    # 2. Lexer, Variable Expansion, and Conditional / Control-Flow Parser
    # ========================================================================

    def expand_variables(self, text: str) -> str:
        """
        Expand `$VAR`, `${VAR}`, and `$?` using the shell's variable table.
        Unknown variables expand to an empty string (standard POSIX shell behavior).
        """
        def replace_braced(match: re.Match) -> str:
            name = match.group(1)
            if name == "?":
                return str(self.last_exit_code)
            return self.variables.get(name, "")

        def replace_simple(match: re.Match) -> str:
            name = match.group(1)
            if name == "?":
                return str(self.last_exit_code)
            return self.variables.get(name, "")

        # Handle escaped \$ by temporarily masking it
        masked = text.replace(r"\$", "\x00ESCAPED_DOLLAR\x00")
        expanded = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*|\?)\}", replace_braced, masked)
        expanded = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*|\?)", replace_simple, expanded)
        return expanded.replace("\x00ESCAPED_DOLLAR\x00", "$")

    def tokenize(self, line: str) -> List[Token]:
        """
        Tokenize a command line into words and operators:
          Operators: `&&`, `||`, `;`, `|`, `2>&1`, `1>&2`, `2>>`, `2>`, `>>`, `>`, `<`
        Preserves quote state so single-quoted strings do not undergo `$VAR` expansion
        while double-quoted and unquoted strings expand `$VAR`.
        """
        tokens: List[Token] = []
        i = 0
        n = len(line)
        current: List[str] = []
        in_single = False
        in_double = False
        token_was_quoted = False
        token_pure_single = True

        def flush_word() -> None:
            nonlocal current, token_was_quoted, token_pure_single
            if current or token_was_quoted:
                raw_val = "".join(current)
                tokens.append(
                    Token(
                        value=raw_val,
                        is_operator=False,
                        single_quoted=(token_was_quoted and token_pure_single),
                        quoted=token_was_quoted,
                    )
                )
                current = []
                token_was_quoted = False
                token_pure_single = True

        multi_ops = ["2>&1", "1>&2", "2>>", "&&", "||", ">>", "2>"]
        single_ops = {";", "|", ">", "<"}

        while i < n:
            ch = line[i]

            if in_single:
                if ch == "'":
                    in_single = False
                else:
                    current.append(ch)
                i += 1
                continue

            if in_double:
                if ch == '"':
                    in_double = False
                    i += 1
                elif ch == "\\" and i + 1 < n and line[i + 1] in {'"', "\\", "$"}:
                    if line[i + 1] == "$":
                        current.append(r"\$")
                    else:
                        current.append(line[i + 1])
                    i += 2
                else:
                    # Expand variables immediately inside double-quoted segments
                    if ch == "$":
                        m = re.match(r"^\$\{([A-Za-z_][A-Za-z0-9_]*|\?)\}", line[i:])
                        if not m:
                            m = re.match(r"^\$([A-Za-z_][A-Za-z0-9_]*|\?)", line[i:])
                        if m:
                            current.append(self.expand_variables(m.group(0)))
                            i += len(m.group(0))
                            continue
                    current.append(ch)
                    i += 1
                continue

            # Outside quotes: ignore comments starting with unquoted #
            if ch == "#" and not current and not token_was_quoted:
                break

            if ch.isspace():
                flush_word()
                i += 1
                continue

            if ch == "'":
                in_single = True
                token_was_quoted = True
                i += 1
                continue

            if ch == '"':
                in_double = True
                token_was_quoted = True
                token_pure_single = False
                i += 1
                continue

            if ch == "\\":
                token_pure_single = False
                token_was_quoted = True
                if i + 1 < n:
                    if line[i + 1] == "$":
                        current.append(r"\$")
                    else:
                        current.append(line[i + 1])
                    i += 2
                else:
                    current.append("\\")
                    i += 1
                continue

            # Check multi-character operators
            matched_op: Optional[str] = None
            for op in multi_ops:
                if line.startswith(op, i):
                    # Ensure `2>` / `1>&2` is only treated as redirection if at start of token
                    if op[0].isdigit() and (current or token_was_quoted):
                        continue
                    matched_op = op
                    break

            if matched_op:
                flush_word()
                tokens.append(Token(value=matched_op, is_operator=True))
                i += len(matched_op)
                continue

            if ch in single_ops:
                flush_word()
                tokens.append(Token(value=ch, is_operator=True))
                i += 1
                continue

            # Unquoted variable expansion
            token_pure_single = False
            if ch == "$":
                m = re.match(r"^\$\{([A-Za-z_][A-Za-z0-9_]*|\?)\}", line[i:])
                if not m:
                    m = re.match(r"^\$([A-Za-z_][A-Za-z0-9_]*|\?)", line[i:])
                if m:
                    current.append(self.expand_variables(m.group(0)))
                    i += len(m.group(0))
                    continue

            current.append(ch)
            i += 1

        if in_single or in_double:
            raise ValueError("syntax error: unmatched quote")

        flush_word()
        return tokens

    # ========================================================================
    # 3. High-Level Execution: Bonus `if/then/else` & Conditional Chains
    # ========================================================================

    def execute_line(
        self,
        line: str,
        stdin: Optional[TextIO] = None,
        stdout: Optional[TextIO] = None,
        stderr: Optional[TextIO] = None,
    ) -> int:
        """
        Execute a full command line supporting:
          - Bonus `if <cond>; then <cmd>; [elif <cond>; then <cmd>;] [else <cmd>;] fi`
          - Sequential & conditional operators (`;`, `&&`, `||`)
          - Pipelines (`|`)
          - Redirections (`>`, `>>`, `<`, `2>`, `2>&1`)
        """
        in_stream = stdin if stdin is not None else sys.stdin
        out_stream = stdout if stdout is not None else sys.stdout
        err_stream = stderr if stderr is not None else sys.stderr

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return 0

        # Check for Bonus `if / then / else / fi` construct
        if re.match(r"^if\b", stripped):
            return self._execute_if_statement(stripped, in_stream, out_stream, err_stream)

        try:
            tokens = self.tokenize(stripped)
        except ValueError as exc:
            err_stream.write(f"minishell: {exc}\n")
            self.last_exit_code = 2
            return 2

        if not tokens:
            return 0

        return self._execute_conditional_tokens(tokens, in_stream, out_stream, err_stream)

    def _execute_if_statement(
        self,
        line: str,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ) -> int:
        """
        Bonus feature: Parse and execute `if ...; then ...; [elif ...; then ...;] [else ...;] fi`.
        Supports commands separated by semicolons or newlines.
        """
        try:
            tokens = self.tokenize(line)
        except ValueError as exc:
            stderr.write(f"minishell: {exc}\n")
            return 2

        # Split tokens into clauses by top-level keywords: if, then, elif, else, fi
        clauses: List[Tuple[str, List[Token]]] = []
        current_kw: Optional[str] = None
        current_tokens: List[Token] = []
        expect_kw = True

        for tok in tokens:
            if tok.is_operator and tok.value == ";":
                if current_tokens and current_tokens[-1].is_operator and current_tokens[-1].value == ";":
                    continue
                current_tokens.append(tok)
                expect_kw = True
                continue

            if expect_kw and not tok.is_operator and tok.value in {"if", "then", "elif", "else", "fi"}:
                kw = tok.value
                # Trim trailing semicolon from previous clause
                while current_tokens and current_tokens[-1].is_operator and current_tokens[-1].value == ";":
                    current_tokens.pop()
                if current_kw is not None:
                    clauses.append((current_kw, current_tokens))
                current_kw = kw
                current_tokens = []
                expect_kw = True
                continue

            current_tokens.append(tok)
            expect_kw = False

        if current_kw != "fi":
            stderr.write("minishell: syntax error: expected 'fi' to close 'if' statement\n")
            self.last_exit_code = 2
            return 2

        # Validate structure and evaluate branches
        idx = 0
        n = len(clauses)
        while idx < n:
            kw, cond_tokens = clauses[idx]
            if kw in {"if", "elif"}:
                if not cond_tokens:
                    stderr.write(f"minishell: syntax error: empty condition after '{kw}'\n")
                    return 2
                if idx + 1 >= n or clauses[idx + 1][0] != "then":
                    stderr.write(f"minishell: syntax error: expected 'then' after '{kw}'\n")
                    return 2
                then_tokens = clauses[idx + 1][1]
                if not then_tokens:
                    stderr.write("minishell: syntax error: empty body after 'then'\n")
                    return 2

                cond_status = self._execute_conditional_tokens(cond_tokens, stdin, stdout, stderr)
                if cond_status == 0:
                    res = self._execute_conditional_tokens(then_tokens, stdin, stdout, stderr)
                    self.last_exit_code = res
                    return res
                idx += 2
            elif kw == "else":
                if not cond_tokens:
                    stderr.write("minishell: syntax error: empty body after 'else'\n")
                    return 2
                res = self._execute_conditional_tokens(cond_tokens, stdin, stdout, stderr)
                self.last_exit_code = res
                return res
            else:
                stderr.write(f"minishell: syntax error: unexpected '{kw}'\n")
                return 2

        self.last_exit_code = 0
        return 0

    def _execute_conditional_tokens(
        self,
        tokens: List[Token],
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ) -> int:
        """
        Split a token list by conditional/sequential operators (`;`, `&&`, `||`)
        and execute each pipeline according to short-circuit semantics:
          - `cmd1 ; cmd2`  -> always run `cmd2`
          - `cmd1 && cmd2` -> run `cmd2` only if `cmd1` returned 0
          - `cmd1 || cmd2` -> run `cmd2` only if `cmd1` returned non-zero
        """
        segments: List[Tuple[Optional[str], List[Token]]] = []
        current: List[Token] = []
        prev_op: Optional[str] = None

        for tok in tokens:
            if tok.is_operator and tok.value in {";", "&&", "||"}:
                if not current:
                    if tok.value == ";":
                        continue
                    stderr.write(f"minishell: syntax error near unexpected token '{tok.value}'\n")
                    self.last_exit_code = 2
                    return 2
                segments.append((prev_op, current))
                current = []
                prev_op = tok.value
            else:
                current.append(tok)

        if current:
            segments.append((prev_op, current))
        elif prev_op in {"&&", "||"}:
            stderr.write(f"minishell: syntax error: expected command after '{prev_op}'\n")
            self.last_exit_code = 2
            return 2

        status = 0
        for op, seg_tokens in segments:
            if not self.running:
                break
            if op == "&&" and status != 0:
                continue
            if op == "||" and status == 0:
                continue
            status = self._execute_pipeline_tokens(seg_tokens, stdin, stdout, stderr)
            self.last_exit_code = status

        return status

    # ========================================================================
    # 4. Pipeline & Redirection Execution
    # ========================================================================

    def _execute_pipeline_tokens(
        self,
        tokens: List[Token],
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ) -> int:
        """
        Split tokens by `|` into one or more pipeline stages, parse each stage
        into a `SimpleCommand`, and connect `stdout` of stage i to `stdin` of stage i+1.
        """
        stages: List[List[Token]] = []
        current: List[Token] = []

        for tok in tokens:
            if tok.is_operator and tok.value == "|":
                if not current:
                    stderr.write("minishell: syntax error near unexpected token '|'\n")
                    return 2
                stages.append(current)
                current = []
            else:
                current.append(tok)

        if not current:
            stderr.write("minishell: syntax error: missing command after '|'\n")
            return 2
        stages.append(current)

        commands: List[SimpleCommand] = []
        for stage_tokens in stages:
            try:
                cmd = self._parse_simple_command(stage_tokens)
            except ValueError as exc:
                stderr.write(f"minishell: {exc}\n")
                return 2
            commands.append(cmd)

        # Single command (not a pipe)
        if len(commands) == 1:
            return self._execute_simple_command(commands[0], stdin, stdout, stderr, in_pipeline=False)

        # Multi-stage pipeline: pass buffered stdout of stage i as stdin of stage i+1
        current_input: TextIO = stdin
        last_status = 0
        for idx, cmd in enumerate(commands):
            is_last = idx == len(commands) - 1
            if is_last:
                stage_out = stdout
                last_status = self._execute_simple_command(
                    cmd, current_input, stage_out, stderr, in_pipeline=True
                )
            else:
                buffer = io.StringIO()
                last_status = self._execute_simple_command(
                    cmd, current_input, buffer, stderr, in_pipeline=True
                )
                buffer.seek(0)
                current_input = buffer

        return last_status

    def _parse_simple_command(self, tokens: List[Token]) -> SimpleCommand:
        """
        Parse a single command's tokens into:
          - leading variable assignments (`NAME=value`)
          - command arguments
          - stream redirections (`>`, `>>`, `<`, `2>`, `2>>`, `2>&1`, `1>&2`)
        """
        cmd = SimpleCommand()
        i = 0
        n = len(tokens)
        seen_command_word = False

        while i < n:
            tok = tokens[i]
            if tok.is_operator:
                if tok.value in {"2>&1", "1>&2"}:
                    cmd.redirections.append(Redirection(op=tok.value, target=None))
                    i += 1
                    continue
                if tok.value in {">", ">>", "<", "2>", "2>>"}:
                    if i + 1 >= n or tokens[i + 1].is_operator:
                        raise ValueError(f"syntax error: missing filename after '{tok.value}'")
                    target_path = tokens[i + 1].value
                    cmd.redirections.append(Redirection(op=tok.value, target=target_path))
                    i += 2
                    continue
                raise ValueError(f"syntax error near unexpected token '{tok.value}'")

            # Check for leading `NAME=value` variable assignment
            if not seen_command_word and not tok.single_quoted:
                m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", tok.value, re.DOTALL)
                if m:
                    cmd.assignments.append((m.group(1), m.group(2)))
                    i += 1
                    continue

            seen_command_word = True
            val = tok.value
            if not tok.quoted:
                if val == "~" or val.startswith("~/"):
                    val = self.variables.get("HOME", os.path.expanduser("~")) + val[1:]
                if any(c in val for c in "*?["):
                    matches = sorted(glob.glob(val))
                    if matches:
                        cmd.args.extend(matches)
                        i += 1
                        continue
            cmd.args.append(val)
            i += 1

        return cmd

    def _execute_simple_command(
        self,
        cmd: SimpleCommand,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
        in_pipeline: bool = False,
    ) -> int:
        """
        Apply redirections, handle variable assignments, and dispatch to either
        a built-in command, a registered teammate module (`sched`, `deadlock`),
        or an external OS binary.
        """
        # Pure variable assignment with no command (e.g., `NAME=Ana`)
        if not cmd.args and cmd.assignments and not cmd.redirections:
            if not in_pipeline:
                for name, val in cmd.assignments:
                    self.variables[name] = val
                    os.environ[name] = val
            return 0

        opened_files: List[TextIO] = []
        active_in: TextIO = stdin
        active_out: TextIO = stdout
        active_err: TextIO = stderr

        try:
            # Process redirections in left-to-right order (just like Bash)
            for redir in cmd.redirections:
                target_path = (
                    os.devnull
                    if redir.target in {"/dev/null", "NUL", "nul"}
                    else redir.target
                )
                if redir.op == "<":
                    assert target_path is not None
                    if target_path != os.devnull and not os.path.exists(target_path):
                        stderr.write(f"minishell: {redir.target}: No such file or directory\n")
                        return 1
                    if target_path != os.devnull and os.path.isdir(target_path):
                        stderr.write(f"minishell: {redir.target}: Is a directory\n")
                        return 1
                    f_in = open(target_path, "r", encoding="utf-8", errors="replace")
                    opened_files.append(f_in)
                    active_in = f_in

                elif redir.op in {">", ">>"}:
                    assert target_path is not None
                    mode = "w" if redir.op == ">" else "a"
                    f_out = open(target_path, mode, encoding="utf-8")
                    opened_files.append(f_out)
                    active_out = f_out

                elif redir.op in {"2>", "2>>"}:
                    assert target_path is not None
                    mode = "w" if redir.op == "2>" else "a"
                    f_err = open(target_path, mode, encoding="utf-8")
                    opened_files.append(f_err)
                    active_err = f_err

                elif redir.op == "2>&1":
                    active_err = active_out

                elif redir.op == "1>&2":
                    active_out = active_err

            if not cmd.args:
                for name, val in cmd.assignments:
                    self.variables[name] = val
                    os.environ[name] = val
                return 0

            # Temporary per-command variable assignments (e.g. `FOO=bar env`)
            saved_vars: Dict[str, Optional[str]] = {}
            for name, val in cmd.assignments:
                saved_vars[name] = self.variables.get(name)
                self.variables[name] = val
                os.environ[name] = val

            try:
                prog = cmd.args[0]
                args = cmd.args[1:]

                # 1. Check teammate integration registry first (`sched`, `deadlock`, etc.)
                if prog in self.registry.handlers:
                    status = self.registry.handlers[prog](args, active_in, active_out, active_err)
                # 2. Check built-in shell commands
                elif prog in self.builtins:
                    status = self.builtins[prog](args, active_in, active_out, active_err)
                # 3. Fallback to external OS program execution
                else:
                    status = self._run_external_program(cmd.args, active_in, active_out, active_err)
            finally:
                # Restore temporary command-scoped variables
                for name, old_val in saved_vars.items():
                    if old_val is None:
                        self.variables.pop(name, None)
                        os.environ.pop(name, None)
                    else:
                        self.variables[name] = old_val
                        os.environ[name] = old_val

            active_out.flush()
            active_err.flush()
            return status

        except BrokenPipeError:
            self.running = False
            return 141
        except PermissionError as exc:
            stderr.write(f"minishell: {exc.filename or 'redirect'}: Permission denied\n")
            return 1
        except OSError as exc:
            stderr.write(f"minishell: redirection error: {exc}\n")
            return 1
        finally:
            for f in opened_files:
                try:
                    f.flush()
                    f.close()
                except Exception:
                    pass

    def _run_external_program(
        self,
        argv: List[str],
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ) -> int:
        """Execute an external OS binary when a command is not a shell built-in."""
        prog = argv[0]
        resolved = shutil.which(prog)
        if resolved is None and not (os.path.sep in prog and os.path.exists(prog)):
            stderr.write(f"minishell: {prog}: command not found\n")
            return 127

        input_data: Optional[str] = None
        if stdin is not sys.stdin:
            try:
                input_data = stdin.read()
            except Exception:
                input_data = None

        try:
            proc = subprocess.run(
                argv,
                input=input_data,
                capture_output=True,
                text=True,
                env=self.variables,
                cwd=os.getcwd(),
            )
            if proc.stdout:
                stdout.write(proc.stdout)
            if proc.stderr:
                stderr.write(proc.stderr)
            return proc.returncode
        except PermissionError:
            stderr.write(f"minishell: {prog}: Permission denied\n")
            return 126
        except FileNotFoundError:
            stderr.write(f"minishell: {prog}: command not found\n")
            return 127
        except Exception as exc:
            stderr.write(f"minishell: {prog}: {exc}\n")
            return 1

    # ========================================================================
    # 5. Module 1 Built-in Commands (File, Directory, Permissions, Variables)
    # ========================================================================

    def builtin_pwd(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`pwd`: Print current working directory."""
        if args:
            stderr.write("pwd: too many arguments\n")
            return 1
        stdout.write(f"{os.getcwd()}\n")
        return 0

    def builtin_cd(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`cd [dir]`: Change working directory (supports `cd`, `cd -`, `cd ~`, `cd <path>`)."""
        if len(args) > 1:
            stderr.write("cd: too many arguments\n")
            return 1

        if not args or args[0] == "~":
            target = self.variables.get("HOME", os.path.expanduser("~"))
        elif args[0] == "-":
            if not self.prev_dir:
                stderr.write("cd: OLDPWD not set\n")
                return 1
            target = self.prev_dir
            stdout.write(f"{target}\n")
        else:
            target = os.path.expanduser(args[0])

        if not os.path.exists(target):
            stderr.write(f"cd: {args[0] if args else target}: No such file or directory\n")
            return 1
        if not os.path.isdir(target):
            stderr.write(f"cd: {args[0] if args else target}: Not a directory\n")
            return 1

        try:
            current = os.getcwd()
            os.chdir(target)
            self.prev_dir = current
            self.variables["OLDPWD"] = current
            self.variables["PWD"] = os.getcwd()
            return 0
        except PermissionError:
            stderr.write(f"cd: {target}: Permission denied\n")
            return 1
        except OSError as exc:
            stderr.write(f"cd: {target}: {exc.strerror}\n")
            return 1

    def builtin_ls(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """
        `ls [-l] [-a] [paths...]`: List directory contents or file details.
        Supports `-l` (long format showing permissions, octal mode, owner, size, date)
        and `-a` (include hidden dotfiles). Outputs one entry per line so pipelines
        like `ls | grep txt` filter individual filenames cleanly.
        """
        long_format = False
        show_all = False
        targets: List[str] = []

        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                for flag in arg[1:]:
                    if flag == "l":
                        long_format = True
                    elif flag == "a":
                        show_all = True
                    else:
                        stderr.write(f"ls: invalid option -- '{flag}'\n")
                        return 1
            else:
                targets.append(arg)

        if not targets:
            targets = ["."]

        exit_code = 0
        multiple = len(targets) > 1

        for idx, target in enumerate(targets):
            if not os.path.exists(target) and not os.path.islink(target):
                stderr.write(f"ls: cannot access '{target}': No such file or directory\n")
                exit_code = 1
                continue

            if os.path.isfile(target) or os.path.islink(target):
                if long_format:
                    stdout.write(f"{self._format_ls_long_entry(target, os.path.basename(target) or target)}\n")
                else:
                    stdout.write(f"{target}\n")
                continue

            if multiple:
                if idx > 0:
                    stdout.write("\n")
                stdout.write(f"{target}:\n")

            try:
                entries = sorted(os.listdir(target))
                if show_all:
                    entries = [".", ".."] + entries
                else:
                    entries = [e for e in entries if not e.startswith(".")]

                if long_format:
                    stdout.write(f"total {len(entries)}\n")
                    for entry in entries:
                        full_path = os.path.join(target, entry)
                        stdout.write(f"{self._format_ls_long_entry(full_path, entry)}\n")
                else:
                    for entry in entries:
                        stdout.write(f"{entry}\n")
            except PermissionError:
                stderr.write(f"ls: cannot open directory '{target}': Permission denied\n")
                exit_code = 1

        return exit_code

    def _format_ls_long_entry(self, full_path: str, display_name: str) -> str:
        """Format a single `ls -l` line with symbolic (`-rwxr-xr-x`) and octal (`0755`) permissions."""
        st = os.lstat(full_path)
        abs_path = os.path.abspath(full_path)

        # Use override permission bits if set via `chmod`, otherwise OS stat mode
        if abs_path in self.permission_overrides:
            perm_bits = self.permission_overrides[abs_path]
            file_type_bits = stat.S_IFMT(st.st_mode)
            effective_mode = file_type_bits | perm_bits
        else:
            effective_mode = st.st_mode
            perm_bits = stat.S_IMODE(st.st_mode)

        mode_str = stat.filemode(effective_mode)
        octal_str = f"{perm_bits:04o}"
        nlink = st.st_nlink

        try:
            owner = (
                pwd_module.getpwuid(st.st_uid).pw_name
                if pwd_module is not None
                else (os.environ.get("USERNAME") or os.environ.get("USER") or str(st.st_uid))
            )
        except Exception:
            owner = os.environ.get("USERNAME") or os.environ.get("USER") or str(st.st_uid)

        try:
            group = (
                grp.getgrgid(st.st_gid).gr_name
                if grp is not None
                else ("staff" if os.name == "nt" else str(st.st_gid))
            )
        except Exception:
            group = "staff" if os.name == "nt" else str(st.st_gid)

        size = st.st_size
        mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%b %d %H:%M")
        return f"{mode_str} ({octal_str}) {nlink:2d} {owner:<8} {group:<8} {size:8d} {mtime} {display_name}"

    def builtin_chmod(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """
        `chmod <mode> <file...>`: Change file permissions using numeric octal modes
        (e.g., `chmod 755 script.sh`, `chmod 644 notes.txt`).
        """
        if len(args) < 2:
            stderr.write("chmod: missing operand (usage: chmod <octal_mode> <file...>)\n")
            return 1

        mode_arg = args[0]
        targets = args[1:]

        is_octal = bool(re.match(r"^[0-7]{3,4}$", mode_arg))
        sym_match = re.match(r"^([ugoa]*)([-+=])([rwx]+)$", mode_arg)
        if not is_octal and not sym_match:
            stderr.write(f"chmod: invalid mode: '{mode_arg}' (expected numeric octal mode like 755 or symbolic like u+x)\n")
            return 1

        exit_code = 0

        for target in targets:
            if not os.path.exists(target):
                stderr.write(f"chmod: cannot access '{target}': No such file or directory\n")
                exit_code = 1
                continue
            try:
                abs_target = os.path.abspath(target)
                if is_octal:
                    mode_val = int(mode_arg, 8)
                else:
                    assert sym_match is not None
                    cur_mode = self.permission_overrides.get(
                        abs_target, stat.S_IMODE(os.lstat(target).st_mode)
                    )
                    who, op, perms = sym_match.groups()
                    who = who or "a"
                    if "a" in who:
                        who = "ugo"
                    bits_val = sum({"r": 4, "w": 2, "x": 1}[p] for p in set(perms))
                    shifts = {"u": 6, "g": 3, "o": 0}
                    mode_val = cur_mode
                    for w in who:
                        b = bits_val << shifts[w]
                        if op == "+":
                            mode_val |= b
                        elif op == "-":
                            mode_val &= ~b
                        else:
                            mode_val = (mode_val & ~(7 << shifts[w])) | b
                os.chmod(target, mode_val)
                self.permission_overrides[abs_target] = mode_val
            except PermissionError:
                stderr.write(f"chmod: changing permissions of '{target}': Operation not permitted\n")
                exit_code = 1
            except OSError as exc:
                stderr.write(f"chmod: '{target}': {exc.strerror}\n")
                exit_code = 1

        return exit_code

    def builtin_mkdir(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`mkdir [-p] <dir...>`: Create directories."""
        parents = False
        targets: List[str] = []
        for arg in args:
            if arg == "-p":
                parents = True
            elif arg.startswith("-"):
                stderr.write(f"mkdir: invalid option -- '{arg}'\n")
                return 1
            else:
                targets.append(arg)

        if not targets:
            stderr.write("mkdir: missing operand\n")
            return 1

        exit_code = 0
        for target in targets:
            try:
                if parents:
                    os.makedirs(target, exist_ok=True)
                else:
                    os.mkdir(target)
            except FileExistsError:
                stderr.write(f"mkdir: cannot create directory '{target}': File exists\n")
                exit_code = 1
            except FileNotFoundError:
                stderr.write(f"mkdir: cannot create directory '{target}': No such file or directory\n")
                exit_code = 1
            except OSError as exc:
                stderr.write(f"mkdir: cannot create directory '{target}': {exc.strerror}\n")
                exit_code = 1

        return exit_code

    def builtin_rmdir(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`rmdir <dir...>`: Remove empty directories."""
        if not args:
            stderr.write("rmdir: missing operand\n")
            return 1

        exit_code = 0
        for target in args:
            try:
                os.rmdir(target)
                self.permission_overrides.pop(os.path.abspath(target), None)
            except FileNotFoundError:
                stderr.write(f"rmdir: failed to remove '{target}': No such file or directory\n")
                exit_code = 1
            except NotADirectoryError:
                stderr.write(f"rmdir: failed to remove '{target}': Not a directory\n")
                exit_code = 1
            except OSError as exc:
                stderr.write(f"rmdir: failed to remove '{target}': Directory not empty or {exc.strerror}\n")
                exit_code = 1

        return exit_code

    def builtin_touch(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`touch <file...>`: Create empty file(s) or update modification timestamps."""
        if not args:
            stderr.write("touch: missing file operand\n")
            return 1

        exit_code = 0
        for target in args:
            try:
                with open(target, "a", encoding="utf-8"):
                    os.utime(target, None)
            except OSError as exc:
                stderr.write(f"touch: cannot touch '{target}': {exc.strerror}\n")
                exit_code = 1

        return exit_code

    def builtin_cp(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`cp [-r] <src...> <dst>`: Copy files or directories."""
        recursive = False
        operands: List[str] = []
        for arg in args:
            if arg in {"-r", "-R"}:
                recursive = True
            elif arg.startswith("-"):
                stderr.write(f"cp: invalid option -- '{arg}'\n")
                return 1
            else:
                operands.append(arg)

        if len(operands) < 2:
            stderr.write("cp: missing file operand (usage: cp [-r] <src...> <dst>)\n")
            return 1

        sources = operands[:-1]
        dst = operands[-1]

        if len(sources) > 1 and not os.path.isdir(dst):
            stderr.write(f"cp: target '{dst}' is not a directory\n")
            return 1

        exit_code = 0
        for src in sources:
            if not os.path.exists(src):
                stderr.write(f"cp: cannot stat '{src}': No such file or directory\n")
                exit_code = 1
                continue
            try:
                if os.path.isdir(src):
                    if not recursive:
                        stderr.write(f"cp: -r not specified; omitting directory '{src}'\n")
                        exit_code = 1
                        continue
                    target_dir = os.path.join(dst, os.path.basename(src.rstrip("/"))) if os.path.isdir(dst) else dst
                    shutil.copytree(src, target_dir, dirs_exist_ok=True)
                else:
                    target_path = os.path.join(dst, os.path.basename(src)) if os.path.isdir(dst) else dst
                    shutil.copy2(src, target_path)
                    abs_src = os.path.abspath(src)
                    if abs_src in self.permission_overrides:
                        self.permission_overrides[os.path.abspath(target_path)] = self.permission_overrides[abs_src]
            except OSError as exc:
                stderr.write(f"cp: cannot copy '{src}' to '{dst}': {exc.strerror}\n")
                exit_code = 1

        return exit_code

    def builtin_mv(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`mv <src...> <dst>`: Move or rename files and directories."""
        if len(args) < 2:
            stderr.write("mv: missing file operand (usage: mv <src...> <dst>)\n")
            return 1

        sources = args[:-1]
        dst = args[-1]

        if len(sources) > 1 and not os.path.isdir(dst):
            stderr.write(f"mv: target '{dst}' is not a directory\n")
            return 1

        exit_code = 0
        for src in sources:
            if not os.path.exists(src):
                stderr.write(f"mv: cannot stat '{src}': No such file or directory\n")
                exit_code = 1
                continue
            try:
                abs_src = os.path.abspath(src)
                target_path = os.path.join(dst, os.path.basename(src.rstrip("/"))) if os.path.isdir(dst) else dst
                shutil.move(src, target_path)
                if abs_src in self.permission_overrides:
                    self.permission_overrides[os.path.abspath(target_path)] = self.permission_overrides.pop(abs_src)
            except OSError as exc:
                stderr.write(f"mv: cannot move '{src}' to '{dst}': {exc.strerror}\n")
                exit_code = 1

        return exit_code

    def builtin_rm(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`rm [-r] [-f] <target...>`: Remove files or directories."""
        recursive = False
        force = False
        targets: List[str] = []

        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                for flag in arg[1:]:
                    if flag in {"r", "R"}:
                        recursive = True
                    elif flag == "f":
                        force = True
                    else:
                        stderr.write(f"rm: invalid option -- '{flag}'\n")
                        return 1
            else:
                targets.append(arg)

        if not targets:
            if force:
                return 0
            stderr.write("rm: missing operand\n")
            return 1

        exit_code = 0
        for target in targets:
            if not os.path.exists(target) and not os.path.islink(target):
                if not force:
                    stderr.write(f"rm: cannot remove '{target}': No such file or directory\n")
                    exit_code = 1
                continue
            try:
                if os.path.isdir(target) and not os.path.islink(target):
                    if not recursive:
                        stderr.write(f"rm: cannot remove '{target}': Is a directory (use -r)\n")
                        exit_code = 1
                        continue
                    shutil.rmtree(target)
                else:
                    os.remove(target)
                self.permission_overrides.pop(os.path.abspath(target), None)
            except OSError as exc:
                if not force:
                    stderr.write(f"rm: cannot remove '{target}': {exc.strerror}\n")
                    exit_code = 1

        return exit_code

    def builtin_cat(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """
        `cat [-n] [file...]`: Concatenate and print files to stdout.
        If no files are given (or `-` is passed), reads from `stdin` (supporting pipes and `<`).
        """
        number_lines = False
        files: List[str] = []
        for arg in args:
            if arg == "-n":
                number_lines = True
            elif arg.startswith("-") and arg != "-":
                stderr.write(f"cat: invalid option -- '{arg}'\n")
                return 1
            else:
                files.append(arg)

        if not files:
            files = ["-"]

        exit_code = 0
        line_num = 1

        for path in files:
            if path == "-":
                for line in stdin:
                    if number_lines:
                        stdout.write(f"{line_num:6d}\t{line}")
                        line_num += 1
                    else:
                        stdout.write(line)
                continue

            if not os.path.exists(path):
                stderr.write(f"cat: {path}: No such file or directory\n")
                exit_code = 1
                continue
            if os.path.isdir(path):
                stderr.write(f"cat: {path}: Is a directory\n")
                exit_code = 1
                continue

            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if number_lines:
                            stdout.write(f"{line_num:6d}\t{line}")
                            line_num += 1
                        else:
                            stdout.write(line)
            except PermissionError:
                stderr.write(f"cat: {path}: Permission denied\n")
                exit_code = 1
            except OSError as exc:
                stderr.write(f"cat: {path}: {exc.strerror}\n")
                exit_code = 1

        return exit_code

    def builtin_echo(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`echo [-n] [args...]`: Print arguments separated by spaces."""
        no_newline = False
        idx = 0
        if args and args[0] == "-n":
            no_newline = True
            idx = 1
        out = " ".join(args[idx:])
        if no_newline:
            stdout.write(out)
        else:
            stdout.write(out + "\n")
        return 0

    def builtin_env(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`env`: List all current shell and environment variables."""
        if args:
            stderr.write("env: too many arguments\n")
            return 1
        for key in sorted(self.variables.keys()):
            stdout.write(f"{key}={self.variables[key]}\n")
        return 0

    def builtin_export(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`export NAME=value ...`: Set or export variables."""
        if not args:
            return self.builtin_env([], stdin, stdout, stderr)
        for arg in args:
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", arg, re.DOTALL)
            if m:
                self.variables[m.group(1)] = m.group(2)
                os.environ[m.group(1)] = m.group(2)
            elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", arg):
                val = self.variables.get(arg, "")
                self.variables[arg] = val
                os.environ[arg] = val
            else:
                stderr.write(f"export: '{arg}': not a valid identifier\n")
                return 1
        return 0

    def builtin_unset(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`unset NAME ...`: Remove shell variables."""
        for name in args:
            self.variables.pop(name, None)
            os.environ.pop(name, None)
        return 0

    # ========================================================================
    # 6. Module 1 Item 8: `grep`-like Text Search (Basic + Bonus Regex)
    # ========================================================================

    def builtin_grep(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        r"""
        `grep [-i] [-n] [-v] [-c] [-F] <pattern> [file...]`
        Prints lines that match `<pattern>` from one or more files or piped `stdin`.
        Supports:
          - Basic substring matching
          - Bonus regular expressions: `.`, `[a-z]`, `*`, `+`, `?`, backslash
            escaping (`\.`, `\*`), and capturing groups `(...)`.
        Returns 0 if at least one line matched, 1 if no lines matched, 2 on error.
        """
        ignore_case = False
        line_numbers = False
        invert_match = False
        count_only = False
        fixed_strings = False
        only_matching = False
        show_groups = False
        positional: List[str] = []
        parsing_opts = True

        for arg in args:
            if parsing_opts and arg == "--":
                parsing_opts = False
            elif parsing_opts and arg == "--groups":
                show_groups = True
            elif parsing_opts and arg.startswith("-") and len(arg) > 1 and not arg.startswith("--"):
                for flag in arg[1:]:
                    if flag == "i":
                        ignore_case = True
                    elif flag == "n":
                        line_numbers = True
                    elif flag == "v":
                        invert_match = True
                    elif flag == "c":
                        count_only = True
                    elif flag == "F":
                        fixed_strings = True
                    elif flag == "o":
                        only_matching = True
                    elif flag == "E":
                        pass  # Regex is enabled by default in MiniShell
                    else:
                        stderr.write(f"grep: invalid option -- '{flag}'\n")
                        return 2
            elif parsing_opts and arg.startswith("--"):
                stderr.write(f"grep: unrecognized option '{arg}'\n")
                return 2
            else:
                positional.append(arg)

        if not positional:
            stderr.write("grep: missing search pattern (usage: grep [options] <pattern> [file...])\n")
            return 2

        pattern_str = positional[0]
        files = positional[1:]

        flags = re.IGNORECASE if ignore_case else 0
        try:
            if fixed_strings:
                regex = re.compile(re.escape(pattern_str), flags)
            else:
                regex = re.compile(pattern_str, flags)
        except re.error as exc:
            stderr.write(f"grep: invalid regular expression '{pattern_str}': {exc}\n")
            return 2

        multiple_files = len(files) > 1
        any_matched = False
        had_error = False

        def process_stream(stream: TextIO, label: Optional[str]) -> None:
            nonlocal any_matched
            match_count = 0
            for idx, raw_line in enumerate(stream, start=1):
                line_text = raw_line.rstrip("\r\n")
                m = regex.search(line_text)
                matched = (m is not None) ^ invert_match
                if matched:
                    any_matched = True
                    match_count += 1
                    if not count_only:
                        prefix = ""
                        if multiple_files and label:
                            prefix += f"{label}:"
                        if line_numbers:
                            prefix += f"{idx}:"
                        if only_matching and not invert_match:
                            for m_obj in regex.finditer(line_text):
                                if m_obj.group(0):
                                    stdout.write(f"{prefix}{m_obj.group(0)}\n")
                        else:
                            stdout.write(f"{prefix}{line_text}\n")
                            if show_groups and m is not None and m.groups():
                                for g_idx, g_val in enumerate(m.groups(), 1):
                                    stdout.write(f"    group {g_idx}: {g_val}\n")
            if count_only:
                prefix = f"{label}:" if (multiple_files and label) else ""
                stdout.write(f"{prefix}{match_count}\n")

        if not files:
            process_stream(stdin, None)
        else:
            for path in files:
                if not os.path.exists(path):
                    stderr.write(f"grep: {path}: No such file or directory\n")
                    had_error = True
                    continue
                if os.path.isdir(path):
                    stderr.write(f"grep: {path}: Is a directory\n")
                    had_error = True
                    continue
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        process_stream(f, path)
                except OSError as exc:
                    stderr.write(f"grep: {path}: {exc.strerror}\n")
                    had_error = True

        if had_error:
            return 2
        return 0 if any_matched else 1

    def builtin_wc(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`wc [-l] [-w] [-c] [file...]`: Count lines, words, and bytes."""
        flags = set()
        files: List[str] = []
        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                for ch in arg[1:]:
                    if ch not in "lwc":
                        stderr.write(f"wc: invalid option -- '{ch}'\n")
                        return 2
                    flags.add(ch)
            else:
                files.append(arg)
        if not flags:
            flags = {"l", "w", "c"}

        inputs: List[Tuple[Optional[str], str]] = []
        exit_code = 0
        if not files:
            inputs.append((None, stdin.read()))
        else:
            for path in files:
                if not os.path.exists(path):
                    stderr.write(f"wc: {path}: No such file or directory\n")
                    exit_code = 1
                    continue
                if os.path.isdir(path):
                    stderr.write(f"wc: {path}: Is a directory\n")
                    exit_code = 1
                    continue
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        inputs.append((path, f.read()))
                except OSError as exc:
                    stderr.write(f"wc: {path}: {exc.strerror}\n")
                    exit_code = 1

        totals = [0, 0, 0]
        rows: List[Tuple[List[int], Optional[str]]] = []
        for label, text in inputs:
            nums = [text.count("\n"), len(text.split()), len(text.encode("utf-8"))]
            totals = [a + b for a, b in zip(totals, nums)]
            rows.append((nums, label))
        if len(inputs) > 1:
            rows.append((totals, "total"))

        for nums, label in rows:
            cols = [f"{val:>7}" for val, key in zip(nums, "lwc") if key in flags]
            stdout.write("".join(cols) + (f" {label}\n" if label else "\n"))
        return exit_code

    def builtin_sort(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`sort [-r] [-n] [file...]`: Sort lines of text files or stdin."""
        reverse = False
        numeric = False
        files: List[str] = []
        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                for ch in arg[1:]:
                    if ch == "r":
                        reverse = True
                    elif ch == "n":
                        numeric = True
                    else:
                        stderr.write(f"sort: invalid option -- '{ch}'\n")
                        return 2
            else:
                files.append(arg)

        all_lines: List[str] = []
        exit_code = 0
        if not files:
            all_lines.extend(stdin.read().splitlines())
        else:
            for path in files:
                if not os.path.exists(path):
                    stderr.write(f"sort: {path}: No such file or directory\n")
                    exit_code = 1
                    continue
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        all_lines.extend(f.read().splitlines())
                except OSError as exc:
                    stderr.write(f"sort: {path}: {exc.strerror}\n")
                    exit_code = 1

        if numeric:
            def num_key(s: str) -> Tuple[float, str]:
                m = re.match(r"\s*(-?\d+(?:\.\d+)?)", s)
                return (float(m.group(1)) if m else 0.0, s)
            all_lines.sort(key=num_key, reverse=reverse)
        else:
            all_lines.sort(reverse=reverse)

        if all_lines:
            stdout.write("\n".join(all_lines) + "\n")
        return exit_code

    def _head_or_tail(
        self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO, mode: str
    ) -> int:
        count = 10
        files: List[str] = []
        i = 0
        while i < len(args):
            if args[i] == "-n":
                if i + 1 >= len(args):
                    stderr.write(f"{mode}: option '-n' requires an argument\n")
                    return 2
                try:
                    count = int(args[i + 1])
                except ValueError:
                    stderr.write(f"{mode}: invalid number of lines: '{args[i + 1]}'\n")
                    return 2
                i += 2
            elif args[i].startswith("-") and len(args[i]) > 1:
                stderr.write(f"{mode}: invalid option -- '{args[i]}'\n")
                return 2
            else:
                files.append(args[i])
                i += 1

        inputs: List[Tuple[Optional[str], str]] = []
        exit_code = 0
        if not files:
            inputs.append((None, stdin.read()))
        else:
            for path in files:
                if not os.path.exists(path):
                    stderr.write(f"{mode}: {path}: No such file or directory\n")
                    exit_code = 1
                    continue
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        inputs.append((path, f.read()))
                except OSError as exc:
                    stderr.write(f"{mode}: {path}: {exc.strerror}\n")
                    exit_code = 1

        for idx, (label, text) in enumerate(inputs):
            if len(inputs) > 1 and label:
                if idx > 0:
                    stdout.write("\n")
                stdout.write(f"==> {label} <==\n")
            lines_list = text.splitlines()
            selected = lines_list[:count] if mode == "head" else (lines_list[-count:] if count > 0 else [])
            if selected:
                stdout.write("\n".join(selected) + "\n")
        return exit_code

    def builtin_head(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`head [-n N] [file...]`: Output the first N lines."""
        return self._head_or_tail(args, stdin, stdout, stderr, "head")

    def builtin_tail(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`tail [-n N] [file...]`: Output the last N lines."""
        return self._head_or_tail(args, stdin, stdout, stderr, "tail")

    # ========================================================================
    # 7. Final Integration Adapters (`sched` & `deadlock`)
    # ========================================================================

    def builtin_sched_adapter(
        self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO
    ) -> int:
        """
        Integration dispatcher for Module 2 (`sched` command — Member 2: Scheduler Lead).
        Example syntax from specification:
          `sched rr --quantum 4 processes.txt`
          `sched fcfs processes.txt`
        Validates CLI arguments and delegates to `scheduler.run_sched` when present,
        or runs the built-in integration adapter so the shell works standalone.
        """
        if not args:
            stderr.write(
                "sched: missing arguments (usage: sched <fcfs|sjn|priority|rr|mlq|mlfq> "
                "[--quantum N] [processes_file])\n"
            )
            return 1

        algo = args[0].lower()
        if algo not in self.VALID_ALGOS:
            stderr.write(
                f"sched: unknown algorithm '{args[0]}' "
                f"(expected one of: fcfs, sjn, priority, rr, mlq, mlfq)\n"
            )
            return 1

        quantum = 4
        file_path: Optional[str] = None
        i = 1
        while i < len(args):
            if args[i] in {"--quantum", "-q"}:
                if i + 1 >= len(args):
                    stderr.write("sched: option '--quantum' requires an integer argument\n")
                    return 1
                try:
                    quantum = int(args[i + 1])
                    if quantum <= 0:
                        raise ValueError
                except ValueError:
                    stderr.write(f"sched: invalid quantum value '{args[i + 1]}'\n")
                    return 1
                i += 2
            elif args[i].startswith("-"):
                stderr.write(f"sched: unknown option '{args[i]}'\n")
                return 1
            else:
                file_path = args[i]
                i += 1

        if file_path is not None and not os.path.exists(file_path):
            stderr.write(f"sched: cannot open '{file_path}': No such file or directory\n")
            return 1

        stdout.write(
            f"[Integration Adapter: Module 2 Scheduler] Dispatched algorithm='{algo.upper()}'"
            f"{f', quantum={quantum}' if algo == 'rr' else ''}"
            f"{f', input={file_path}' if file_path else ', input=stdin'}.\n"
            "  -> To plug in Member 2's implementation, provide `scheduler.py` with "
            "`run_sched(args, stdin, stdout, stderr)` or call `shell.registry.register('sched', fn)`.\n"
        )
        return 0

    def builtin_deadlock_adapter(
        self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO
    ) -> int:
        """
        Integration dispatcher for Module 3 (`deadlock` command — Member 3: Resources Lead).
        Example syntax from specification:
          `deadlock detect system.txt`
          `deadlock banker system.txt`
        Validates CLI arguments and delegates to `deadlock.run_deadlock` when present,
        or runs the built-in integration adapter so the shell works standalone.
        """
        if len(args) < 1:
            stderr.write("deadlock: missing mode (usage: deadlock <detect|banker> <system_file>)\n")
            return 1

        mode = args[0].lower()
        if mode not in self.VALID_DEADLOCK_MODES:
            stderr.write(
                f"deadlock: unknown mode '{args[0]}' (expected 'detect' or 'banker')\n"
            )
            return 1

        if len(args) < 2:
            stderr.write(f"deadlock {mode}: missing system state file operand\n")
            return 1

        file_path = args[1]
        if not os.path.exists(file_path):
            stderr.write(f"deadlock: cannot open '{file_path}': No such file or directory\n")
            return 1

        stdout.write(
            f"[Integration Adapter: Module 3 Deadlock] Dispatched mode='{mode}', "
            f"system_file='{file_path}'.\n"
            "  -> To plug in Member 3's implementation, provide `deadlock.py` with "
            "`run_deadlock(args, stdin, stdout, stderr)` or call `shell.registry.register('deadlock', fn)`.\n"
        )
        return 0

    # ========================================================================
    # 8. Utility Built-ins (`help`, `history`, `clear`, `true`, `false`, `exit`)
    # ========================================================================

    def builtin_help(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`help`: Display summary of supported MiniShell commands and operators."""
        help_text = (
            "MiniShell — CmpSc 123 Operating Systems Project (Shell Core & Integration)\n"
            "Built-in Commands:\n"
            "  pwd, cd [dir], ls [-l] [-a] [path...], mkdir [-p] <dir...>, rmdir <dir...>\n"
            "  touch <file...>, cp [-r] <src...> <dst>, mv <src...> <dst>, rm [-r] [-f] <target...>\n"
            "  cat [-n] [file...], chmod <octal_mode> <file...>, echo [-n] [args...]\n"
            "  env, export NAME=val, unset NAME, grep [-i] [-n] [-v] [-c] <pattern> [file...]\n"
            "  sched <algo> [--quantum N] <file>, deadlock <detect|banker> <file>\n"
            "  history, clear, true, false, help, exit\n"
            "Stream Redirection & Pipes:\n"
            "  cmd > file, cmd >> file, cmd < file, cmd 2> file, cmd 2>&1, cmd1 | cmd2\n"
            "Variables & Conditional Execution:\n"
            "  NAME=value, echo $NAME, cmd1 && cmd2, cmd1 || cmd2, cmd1 ; cmd2\n"
            "  if <cond>; then <cmd>; else <cmd>; fi\n"
        )
        stdout.write(help_text)
        return 0

    def builtin_history(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`history`: Print command history for the current session."""
        for idx, entry in enumerate(self.history, start=1):
            stdout.write(f"{idx:4d}  {entry}\n")
        return 0

    def builtin_clear(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`clear`: Clear the terminal screen."""
        stdout.write("\033[2J\033[H")
        return 0

    def builtin_true(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`true`: Return exit status 0."""
        return 0

    def builtin_false(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`false`: Return exit status 1."""
        return 1

    def builtin_exit(self, args: List[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
        """`exit [code]`: Exit MiniShell with optional numeric status code."""
        code = self.last_exit_code
        if args:
            try:
                code = int(args[0])
            except ValueError:
                stderr.write(f"exit: {args[0]}: numeric argument required\n")
                code = 2
        self.running = False
        return code


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for running MiniShell interactively or with `-c "<command>"` / script file."""
    args = argv if argv is not None else sys.argv[1:]

    if len(args) >= 2 and args[0] == "-c":
        shell = MiniShell(interactive=False)
        return shell.execute_line(args[1])

    if len(args) == 1 and args[0] not in {"-h", "--help"}:
        script_path = args[0]
        if not os.path.exists(script_path):
            sys.stderr.write(f"minishell: {script_path}: No such file or directory\n")
            return 127
        shell = MiniShell(interactive=False)
        status = 0
        with open(script_path, "r", encoding="utf-8") as f:
            for line in f:
                if not shell.running:
                    break
                status = shell.execute_line(line)
        return status

    if args and args[0] in {"-h", "--help"}:
        shell = MiniShell(interactive=False)
        shell.builtin_help([], sys.stdin, sys.stdout, sys.stderr)
        return 0

    shell = MiniShell(interactive=sys.stdin.isatty())
    return shell.run_repl()


if __name__ == "__main__":
    sys.exit(main())