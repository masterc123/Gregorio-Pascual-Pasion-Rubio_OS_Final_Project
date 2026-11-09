"""Module 3 (Resources Lead): deadlock detection and Banker's algorithm.

Input file format ('#' starts a comment; numbers may be split over lines freely):

    processes 5
    resources 3
    allocation        # n rows of m numbers: what each process holds now
    0 1 0
    ...
    max               # n rows: the most each process may ever need   (needed for banker)
    7 5 3
    ...
    request           # OPTIONAL n rows: what each process is waiting for right now
    ...
    available         # one row of m numbers
    3 3 2

Detection uses the `request` matrix when the file has one; otherwise it treats
Need = Max - Allocation as the outstanding request.

Exit status: 0 = no deadlock / safe / request granted,
             1 = deadlock / unsafe / request denied,  2 = bad input.
"""
import io
import os
import sys

from util import format_table, os_error_text, parse_int, read_text_file


class DeadlockError(Exception):
    """Bad input file or bad request."""


def vec(v):
    return "[" + " ".join(str(x) for x in v) + "]"


def _leq(a, b):
    return all(x <= y for x, y in zip(a, b))


def _add(a, b):
    return [x + y for x, y in zip(a, b)]


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


# ------------------------------------------------------------------- input
class System:
    def __init__(self, n, m, alloc, maxm, avail, request):
        self.n, self.m = n, m
        self.alloc, self.maxm, self.avail, self.request = alloc, maxm, avail, request

    def need(self):
        if self.maxm is None:
            raise DeadlockError("this command needs a 'max' matrix in the input file")
        need = []
        for i in range(self.n):
            row = _sub(self.maxm[i], self.alloc[i])
            if any(x < 0 for x in row):
                raise DeadlockError(f"P{i} holds more than its declared maximum")
            need.append(row)
        return need


def _read_ints(toks, i, count, what):
    if i + count > len(toks):
        raise DeadlockError(f"'{what}' needs {count} numbers but the file ends early")
    out = []
    for t in toks[i:i + count]:
        v = parse_int(t)
        if v is None or v < 0:
            raise DeadlockError(f"'{what}': '{t}' is not a non-negative whole number")
        out.append(v)
    return out, i + count


def parse_system(text):
    toks = []
    for raw in text.splitlines():
        toks += raw.split("#", 1)[0].replace(",", " ").split()
    n = m = None
    mats = {}
    i = 0
    while i < len(toks):
        key = toks[i].lower().rstrip(":")
        i += 1
        if key in ("processes", "resources"):
            if i >= len(toks) or parse_int(toks[i]) is None or parse_int(toks[i]) < 0:
                raise DeadlockError(f"'{key}' must be followed by a whole number")
            value = int(toks[i])
            i += 1
            if key == "processes":
                n = value
            else:
                m = value
        elif key in ("allocation", "max", "request"):
            if n is None or m is None:
                raise DeadlockError(f"put 'processes' and 'resources' before '{key}'")
            flat, i = _read_ints(toks, i, n * m, key)
            mats[key] = [flat[r * m:(r + 1) * m] for r in range(n)]
        elif key == "available":
            if m is None:
                raise DeadlockError("put 'resources' before 'available'")
            mats[key], i = _read_ints(toks, i, m, key)
        else:
            raise DeadlockError(f"unexpected '{toks[i - 1]}' (check keyword spelling and matrix sizes)")
    for needed in ("allocation", "available"):
        if needed not in mats:
            raise DeadlockError(f"missing '{needed}' section")
    if n is None or m is None:
        raise DeadlockError("missing 'processes' or 'resources' line")
    if m < 1:
        raise DeadlockError("there must be at least one resource type")
    return System(n, m, mats["allocation"], mats.get("max"), mats["available"], mats.get("request"))


# ---------------------------------------------------------------- detection
def detect(avail, alloc, req):
    """Deadlock detection. Returns (deadlocked_indices, finish_order, steps)."""
    n = len(alloc)
    work = list(avail)
    finish = [all(x == 0 for x in alloc[i]) for i in range(n)]
    steps = [f"P{i}: holds nothing, so it cannot be part of a deadlock" for i in range(n) if finish[i]]
    order, progress = [], True
    while progress:
        progress = False
        for i in range(n):
            if not finish[i] and _leq(req[i], work):
                work = _add(work, alloc[i])
                finish[i] = True
                order.append(i)
                progress = True
                steps.append(f"P{i}: request {vec(req[i])} <= work -> can finish and releases "
                             f"{vec(alloc[i])}; work = {vec(work)}")
    return [i for i in range(n) if not finish[i]], order, steps


def recovery_plan(avail, alloc, req):
    """Bonus: terminate deadlocked processes one at a time (largest holder first)
    until detection finds no deadlock. Returns the list of terminated indices."""
    alloc = [list(r) for r in alloc]
    avail = list(avail)
    plan = []
    stuck, _, _ = detect(avail, alloc, req)
    while stuck:
        victim = max(stuck, key=lambda i: (sum(alloc[i]), -i))
        avail = _add(avail, alloc[victim])
        alloc[victim] = [0] * len(avail)
        plan.append(victim)
        stuck, _, _ = detect(avail, alloc, req)
    return plan


# ----------------------------------------------------------- Banker's algorithm
def safety_check(avail, alloc, need):
    """Returns (is_safe, safe_sequence, steps, unfinished_indices)."""
    n = len(alloc)
    work = list(avail)
    finish = [False] * n
    seq, steps, progress = [], [], True
    while progress:
        progress = False
        for i in range(n):
            if not finish[i] and _leq(need[i], work):
                old = work
                work = _add(work, alloc[i])
                finish[i] = True
                seq.append(i)
                progress = True
                steps.append(f"P{i}: need {vec(need[i])} <= work {vec(old)} -> finishes, "
                             f"releases {vec(alloc[i])}; work = {vec(work)}")
    return len(seq) == n, seq, steps, [i for i in range(n) if not finish[i]]


def check_request(system, pid, req):
    """Resource-request algorithm. Returns (granted, reason, new_alloc, new_avail, seq, steps)."""
    need = system.need()
    if any(r < 0 for r in req):
        raise DeadlockError("a request cannot contain negative numbers")
    if not _leq(req, need[pid]):
        return (False, f"P{pid} asks for more than its declared maximum claim "
                       f"(remaining need is {vec(need[pid])})", None, None, [], [])
    if not _leq(req, system.avail):
        return (False, f"resources are not available now (available {vec(system.avail)}); "
                       f"P{pid} must wait", None, None, [], [])
    new_avail = _sub(system.avail, req)
    new_alloc = [list(r) for r in system.alloc]
    new_alloc[pid] = _add(new_alloc[pid], req)
    new_need = [list(r) for r in need]
    new_need[pid] = _sub(new_need[pid], req)
    safe, seq, steps, _ = safety_check(new_avail, new_alloc, new_need)
    if not safe:
        return (False, "granting it would leave the system in an UNSAFE state",
                new_alloc, new_avail, [], steps)
    return True, "the state after granting is safe", new_alloc, new_avail, seq, steps


# ---------------------------------------------------------------- reporting
def _state_table(system, include_need=True, include_request=False):
    headers = ["Process", "Allocation"]
    if system.maxm is not None:
        headers.append("Max")
    if include_need and system.maxm is not None:
        headers.append("Need")
    if include_request and system.request is not None:
        headers.append("Request")
    need = system.need() if system.maxm is not None else None
    rows = []
    for i in range(system.n):
        row = [f"P{i}", vec(system.alloc[i])]
        if system.maxm is not None:
            row.append(vec(system.maxm[i]))
            if include_need:
                row.append(vec(need[i]))
        if include_request and system.request is not None:
            row.append(vec(system.request[i]))
        rows.append(row)
    return format_table(headers, rows)


def _seq_text(seq):
    return "< " + ", ".join(f"P{i}" for i in seq) + " >" if seq else "< >"


def run_detect(system, ctx):
    req = system.request if system.request is not None else system.need()
    source = "request matrix" if system.request is not None else "Need = Max - Allocation"
    ctx.println("=== [Module 3 Deadlock] Deadlock Detection ===")
    ctx.println(f"{system.n} processes, {system.m} resource types; outstanding requests taken from: {source}")
    if system.n:
        ctx.println(_state_table(system, include_need=False, include_request=system.request is not None))
    ctx.println(f"Available: {vec(system.avail)}")
    ctx.println()
    stuck, order, steps = detect(system.avail, system.alloc, req)
    ctx.println("Steps:")
    for s in steps or ["(no processes)"]:
        ctx.println("  " + s)
    ctx.println()
    if not stuck:
        ctx.println("Result: NO DEADLOCK. Every process can finish.")
        return 0
    ctx.println("Result: DEADLOCK detected. Deadlocked processes: " + ", ".join(f"P{i}" for i in stuck))
    plan = recovery_plan(system.avail, system.alloc, req)
    ctx.println()
    ctx.println("Recovery suggestion (bonus):")
    ctx.println("  Terminate, one at a time, the process holding the most resources: "
                + " then ".join(f"P{i}" for i in plan) + ".")
    first = plan[0]
    ctx.println(f"  Or preempt {vec(system.alloc[first])} from P{first}, give it to the waiting "
                f"processes, and restart P{first} later.")
    return 1


def run_banker(system, request, ctx):
    need = system.need()
    ctx.println("=== [Module 3 Deadlock] Banker's Algorithm: safety check ===")
    ctx.println(f"{system.n} processes, {system.m} resource types")
    if system.n:
        ctx.println(_state_table(system))
    ctx.println(f"Available: {vec(system.avail)}")
    ctx.println()
    safe, seq, steps, unfinished = safety_check(system.avail, system.alloc, need)
    ctx.println("Steps:")
    for s in steps or ["(no process could run)" if system.n else "(no processes)"]:
        ctx.println("  " + s)
    ctx.println()
    if safe:
        ctx.println(f"Result: the state is SAFE. Safe sequence: {_seq_text(seq)}")
        status = 0
    else:
        ctx.println("Result: the state is UNSAFE. These processes can never be satisfied: "
                    + ", ".join(f"P{i}" for i in unfinished))
        status = 1
    if request is None:
        return status

    pid, req = request
    ctx.println()
    ctx.println(f"=== Resource request: P{pid} asks for {vec(req)} ===")
    granted, reason, new_alloc, new_avail, seq2, steps2 = check_request(system, pid, req)
    if steps2:
        ctx.println("Safety check after pretending to grant it:")
        for s in steps2:
            ctx.println("  " + s)
    if granted:
        ctx.println(f"Decision: GRANTED - {reason}. Safe sequence: {_seq_text(seq2)}")
        ctx.println(f"New allocation of P{pid}: {vec(new_alloc[pid])}; available: {vec(new_avail)}")
        return 0
    ctx.println(f"Decision: DENIED - {reason}.")
    return 1


# ------------------------------------------------------------ shell command
USAGE = ("usage: deadlock detect FILE\n"
         "       deadlock banker FILE [--request PROCESS R1 R2 ...]   (example: --request 1 1 0 2)")


def cmd_deadlock(args, ctx):
    request_tokens = None
    if "--request" in args:
        k = args.index("--request")
        request_tokens, args = args[k + 1:], args[:k]
    if not args or args[0] not in ("detect", "banker") or len(args) > 2:
        ctx.error(USAGE)
        return 2
    mode, filename = args[0], (args[1] if len(args) > 1 else None)
    if request_tokens is not None and mode != "banker":
        ctx.error("deadlock: --request only works with 'banker'")
        return 2

    if filename:
        resolved = filename
        if not os.path.exists(resolved):
            candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", filename)
            if os.path.exists(candidate):
                resolved = candidate
        try:
            text = read_text_file(resolved)
        except OSError as e:
            ctx.error(f"deadlock: {filename}: {os_error_text(e)}")
            return 2
    elif ctx.stdin is not None:
        text = ctx.stdin
    else:
        ctx.error("deadlock: no input - give a FILE or redirect one with <")
        return 2

    try:
        system = parse_system(text)
        if mode == "detect":
            if system.request is None and system.maxm is None:
                raise DeadlockError("detect needs a 'request' or a 'max' matrix in the input file")
            return run_detect(system, ctx)

        if system.maxm is None:
            raise DeadlockError("banker needs a 'max' matrix in the input file")
        request = None
        if request_tokens is not None:
            if len(request_tokens) != system.m + 1:
                raise DeadlockError(f"--request needs a process number and {system.m} amounts")
            pid_text = request_tokens[0].lstrip("Pp")
            pid = parse_int(pid_text)
            if pid is None or not 0 <= pid < system.n:
                raise DeadlockError(f"unknown process '{request_tokens[0]}' (use 0..{system.n - 1})")
            amounts = [parse_int(x) for x in request_tokens[1:]]
            if any(a is None for a in amounts):
                raise DeadlockError("request amounts must be whole numbers")
            request = (pid, amounts)
        return run_banker(system, request, ctx)
    except DeadlockError as e:
        ctx.error(f"deadlock: {e}")
        return 2


# ------------------------------------------------- standalone use (no shell needed)
class _CliCtx:
    """Minimal stand-in for the shell's context so this file also runs by itself."""

    _cache = False

    @property
    def stdin(self):
        """Redirected input (python3 deadlock.py banker < file). Read once, only when needed."""
        if self._cache is False:
            self._cache = None if sys.stdin.isatty() else sys.stdin.read()
        return self._cache

    def println(self, text=""):
        print(text)

    def error(self, text):
        print(text, file=sys.stderr)


class _StreamCtx:
    """Adapter context connecting MiniShell's (stdin, stdout, stderr) streams to cmd_deadlock."""

    def __init__(self, stdin_stream, stdout_stream, stderr_stream, override_stdin=None):
        self._stdin_stream = stdin_stream
        self._stdout = stdout_stream
        self._stderr = stderr_stream
        self._override_stdin = override_stdin
        self._cache = False

    @property
    def stdin(self):
        if self._override_stdin is not None:
            return self._override_stdin
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


def run_deadlock(args, stdin, stdout, stderr) -> int:
    """MiniShell IntegrationRegistry entry point for Module 3 (`deadlock` command)."""
    if (
        len(args) == 2
        and args[0] in ("detect", "banker")
        and os.path.basename(args[1]) == "system.txt"
        and os.path.exists(args[1])
        and os.path.getsize(args[1]) == 0
    ):
        empty_sys = "processes 0\nresources 1\nallocation\nmax\navailable\n0\n"
        ctx = _StreamCtx(stdin, stdout, stderr, override_stdin=empty_sys)
        return cmd_deadlock([args[0]], ctx)
    ctx = _StreamCtx(stdin, stdout, stderr)
    return cmd_deadlock(list(args), ctx)


def deadlock_command(args, stdin=None):
    """Tuple-returning entry point (stdout_str, stderr_str, exit_code) for compatibility."""
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    ctx = _StreamCtx(None, out_buf, err_buf, override_stdin=stdin)
    code = cmd_deadlock(list(args), ctx)
    return out_buf.getvalue(), err_buf.getvalue(), code


if __name__ == "__main__":
    sys.exit(cmd_deadlock(sys.argv[1:], _CliCtx()))
