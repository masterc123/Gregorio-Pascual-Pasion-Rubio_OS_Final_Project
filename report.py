"""Module 4 (Docs and Testing Lead): run one process set through all six algorithms.

    compare [--quantum N] [--preemptive] [FILE]

Prints a table of average waiting / turnaround time, a text bar chart of each,
and names the best algorithm for each measure. Copy these tables into the report.
"""
import io
import sys

from scheduler import ORDER, SchedError, load_processes, parse_sched_options, simulate
from util import format_table

BAR_WIDTH = 40


def _bars(ctx, title, results, getter):
    ctx.println(title)
    top = max(getter(r) for r in results) or 1
    name_width = max(len(r.name) for r in results)
    for r in results:
        v = getter(r)
        bar = "#" * max(1, round(v / top * BAR_WIDTH)) if v else ""
        ctx.println(f"  {r.name:<{name_width}} {bar:<{BAR_WIDTH}} {v:.2f}")


def cmd_compare(args, ctx):
    opts = parse_sched_options(args, ctx, "compare")
    if opts is None:
        return 1
    if len(opts["operands"]) > 1 or opts["trace"] or opts["at"] is not None:
        ctx.error("usage: compare [--quantum N] [--preemptive] [FILE]")
        return 1
    procs = load_processes(opts["operands"][0] if opts["operands"] else None, ctx, "compare")
    if procs is None:
        return 1
    if not procs:
        ctx.println("No processes to compare.")
        return 0
    try:
        results = [simulate(a, procs, opts["quantum"], opts["preemptive"]) for a in ORDER]
    except SchedError as e:
        ctx.error(f"compare: {e}")
        return 1

    ctx.println(f"=== Comparison of {len(ORDER)} scheduling algorithms "
                f"({len(procs)} processes, quantum={opts['quantum']}) ===")
    rows = [(r.name, f"{r.avg_waiting():.2f}", f"{r.avg_turnaround():.2f}") for r in results]
    ctx.println(format_table(["Algorithm", "Avg waiting", "Avg turnaround"], rows))
    ctx.println()
    _bars(ctx, "Average waiting time", results, lambda r: r.avg_waiting())
    ctx.println()
    _bars(ctx, "Average turnaround time", results, lambda r: r.avg_turnaround())
    ctx.println()
    for label, getter in (("waiting time", lambda r: r.avg_waiting()),
                          ("turnaround time", lambda r: r.avg_turnaround())):
        best = min(getter(r) for r in results)
        winners = [r.name for r in results if abs(getter(r) - best) < 1e-9]
        names = "all algorithms tie" if len(winners) == len(results) else ", ".join(winners)
        ctx.println(f"Best average {label}: {names} ({best:.2f})")
    return 0


# ------------------------------------------------- standalone use (no shell needed)
class _CliCtx:
    """Minimal stand-in for the shell's context so this file also runs by itself."""

    _cache = False

    @property
    def stdin(self):
        """Redirected input (python3 report.py < file). Read once, only when needed."""
        if self._cache is False:
            self._cache = None if sys.stdin.isatty() else sys.stdin.read()
        return self._cache

    def println(self, text=""):
        print(text)

    def error(self, text):
        print(text, file=sys.stderr)


class _StreamCtx:
    """Adapter context connecting MiniShell's (stdin, stdout, stderr) streams to cmd_compare."""

    def __init__(self, stdin_stream, stdout_stream, stderr_stream):
        self._stdin_stream = stdin_stream
        self._stdout = stdout_stream
        self._stderr = stderr_stream
        self._cache = False

    @property
    def stdin(self):
        if self._cache is False:
            if self._stdin_stream is None or self._stdin_stream is sys.stdin:
                self._cache = None if sys.stdin.isatty() else sys.stdin.read()
            elif isinstance(self._stdin_stream, io.StringIO):
                val = self._stdin_stream.read()
                self._cache = val if val != "" else None
            else:
                self._cache = self._stdin_stream.read()
        return self._cache

    def println(self, text=""):
        self._stdout.write(f"{text}\n")

    def error(self, text):
        self._stderr.write(f"{text}\n")


def run_compare(args, stdin, stdout, stderr) -> int:
    """MiniShell IntegrationRegistry entry point for Module 4 (`compare` command)."""
    return cmd_compare(list(args), _StreamCtx(stdin, stdout, stderr))


if __name__ == "__main__":
    sys.exit(cmd_compare(sys.argv[1:], _CliCtx()))
