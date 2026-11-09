"""Module 2 (Scheduler Lead): PCB table and the six CPU-scheduling algorithms.

Input file format (one process per line, '#' starts a comment, a header line is ok):

    # PID  ARRIVAL  BURST  PRIORITY
    P1     0        8      3

Priority: a SMALLER number means a HIGHER priority. PRIORITY is optional (default 1).

Design
------
Every algorithm only produces a list of Gantt segments (pid, start, end), where
pid is None for idle time. Completion/turnaround/waiting times and the process
states are then derived from the segments in one place (_finalize), so all six
algorithms are measured in exactly the same way:

    Turnaround = Completion - Arrival        Waiting = Turnaround - Burst
"""
import io
import os
import sys
from collections import deque

from util import format_table, os_error_text, parse_int, read_text_file

ALGO_NAMES = {
    "fcfs": "FCFS",
    "sjn": "SJN",
    "priority": "Priority",
    "rr": "Round-Robin",
    "mlq": "Multilevel Queue",
    "mlfq": "Multilevel Feedback Queue",
}
ORDER = ["fcfs", "sjn", "priority", "rr", "mlq", "mlfq"]
ALIASES = {"sjf": "sjn", "prio": "priority", "roundrobin": "rr", "round-robin": "rr"}

# Multilevel queue layout (3 queues, a lower queue only runs when all higher ones are empty):
#   Q0: Round-Robin, quantum Q      (priority 1-2 in MLQ; every new process in MLFQ)
#   Q1: Round-Robin, quantum 2*Q    (priority 3-4 in MLQ)
#   Q2: FCFS (runs to completion)   (priority 5+ in MLQ)
MLQ_LIMITS = (2, 4)


class SchedError(Exception):
    """Bad input or bad option for the scheduling simulator."""


# --------------------------------------------------------------------- PCB
class PCB:
    """Process Control Block: everything the 'OS' remembers about a process."""

    def __init__(self, pid, arrival, burst, priority=1, order=0):
        self.pid = pid
        self.arrival = arrival
        self.burst = burst
        self.priority = priority
        self.order = order            # position in the input (tie breaker)
        self.state = "New"            # New, Ready, Running, Waiting, Terminated
        self.remaining = burst
        self.start = None             # first time on the CPU
        self.completion = None

    def copy(self):
        return PCB(self.pid, self.arrival, self.burst, self.priority, self.order)

    @property
    def turnaround(self):
        return self.completion - self.arrival

    @property
    def waiting(self):
        return self.turnaround - self.burst

    @property
    def response(self):
        return self.start - self.arrival


class Result:
    def __init__(self, algo, name, procs, segments):
        self.algo, self.name, self.procs, self.segments = algo, name, procs, segments

    def avg_waiting(self):
        return sum(p.waiting for p in self.procs) / len(self.procs) if self.procs else 0.0

    def avg_turnaround(self):
        return sum(p.turnaround for p in self.procs) / len(self.procs) if self.procs else 0.0


# ------------------------------------------------------------------- input
def parse_processes(text):
    """Parse the process file text into a list of PCB objects."""
    procs, seen, first = [], set(), True
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.replace(",", " ").split()
        if first:
            first = False
            if parts[0].lower() in ("pid", "id", "process", "name", "proc"):   # header line
                continue
        if not 3 <= len(parts) <= 4:
            raise SchedError(f"line {lineno}: expected 'PID ARRIVAL BURST [PRIORITY]'")
        pid = parts[0]
        nums = [parse_int(x) for x in parts[1:]]
        if any(v is None for v in nums):
            raise SchedError(f"line {lineno}: arrival, burst and priority must be whole numbers")
        arrival, burst = nums[0], nums[1]
        priority = nums[2] if len(nums) > 2 else 1
        if arrival < 0:
            raise SchedError(f"line {lineno}: arrival time of {pid} cannot be negative")
        if burst <= 0:
            raise SchedError(f"line {lineno}: burst time of {pid} must be at least 1")
        if pid in seen:
            raise SchedError(f"line {lineno}: duplicate PID '{pid}'")
        seen.add(pid)
        procs.append(PCB(pid, arrival, burst, priority, len(procs)))
    return procs


# -------------------------------------------------------------- algorithms
def _fcfs(ps):
    segs, t = [], 0
    for p in sorted(ps, key=lambda p: (p.arrival, p.order)):
        if t < p.arrival:
            segs.append((None, t, p.arrival))
            t = p.arrival
        segs.append((p.pid, t, t + p.burst))
        t += p.burst
    return segs


def _nonpreemptive(ps, key):
    """Whenever the CPU is free, run the ready process with the smallest key to the end."""
    remaining = sorted(ps, key=lambda p: (p.arrival, p.order))
    segs, t = [], 0
    while remaining:
        ready = [p for p in remaining if p.arrival <= t]
        if not ready:
            nxt = min(p.arrival for p in remaining)
            segs.append((None, t, nxt))
            t = nxt
            continue
        p = min(ready, key=lambda q: (key(q), q.arrival, q.order))
        segs.append((p.pid, t, t + p.burst))
        t += p.burst
        remaining.remove(p)
    return segs


def _preemptive(ps, key):
    """Preemptive version: re-decide every time a new process arrives.

    key(p, remaining_time) -> smaller value runs first (SRTF or preemptive Priority).
    """
    rem = {p.pid: p.burst for p in ps}
    segs, t, left = [], 0, len(ps)
    while left:
        ready = [p for p in ps if p.arrival <= t and rem[p.pid] > 0]
        if not ready:
            nxt = min(p.arrival for p in ps if rem[p.pid] > 0)
            segs.append((None, t, nxt))
            t = nxt
            continue
        p = min(ready, key=lambda q: (key(q, rem[q.pid]), q.arrival, q.order))
        future = [q.arrival for q in ps if q.arrival > t and rem[q.pid] > 0]
        run = rem[p.pid] if not future else min(rem[p.pid], min(future) - t)
        segs.append((p.pid, t, t + run))
        rem[p.pid] -= run
        t += run
        if rem[p.pid] == 0:
            left -= 1
    return segs


def _round_robin(ps, quantum):
    pending = sorted(ps, key=lambda p: (p.arrival, p.order))
    rem = {p.pid: p.burst for p in ps}
    queue, segs, t = deque(), [], 0
    while pending or queue:
        while pending and pending[0].arrival <= t:      # admit new arrivals
            queue.append(pending.pop(0))
        if not queue:                                   # CPU idle until next arrival
            segs.append((None, t, pending[0].arrival))
            t = pending[0].arrival
            continue
        p = queue.popleft()
        run = min(quantum, rem[p.pid])
        segs.append((p.pid, t, t + run))
        t += run
        rem[p.pid] -= run
        while pending and pending[0].arrival <= t:      # arrivals during the slice go first
            queue.append(pending.pop(0))
        if rem[p.pid] > 0:
            queue.append(p)
    return segs


def _multilevel(ps, quantum, feedback):
    """Shared engine for the Multilevel Queue (feedback=False) and Feedback Queue (True).

    * The CPU always serves the highest non-empty queue.
    * A running process is preempted when a process arrives for a HIGHER queue.
      It then goes back to the FRONT of its own queue (no demotion).
    * MLQ: queue is fixed by priority.  MLFQ: everybody starts in Q0 and a process
      that uses up its whole quantum is demoted one level.
    """
    quanta = [quantum, 2 * quantum, None]            # None = FCFS (run to completion)
    if feedback:
        level = {p.pid: 0 for p in ps}
    else:
        level = {p.pid: (0 if p.priority <= MLQ_LIMITS[0] else
                         1 if p.priority <= MLQ_LIMITS[1] else 2) for p in ps}
    rem = {p.pid: p.burst for p in ps}
    pending = sorted(ps, key=lambda p: (p.arrival, p.order))
    queues = [deque(), deque(), deque()]
    segs, t = [], 0

    def admit():
        while pending and pending[0].arrival <= t:
            p = pending.pop(0)
            queues[level[p.pid]].append(p)

    while True:
        admit()
        k = next((i for i, q in enumerate(queues) if q), None)
        if k is None:
            if not pending:
                break
            segs.append((None, t, pending[0].arrival))
            t = pending[0].arrival
            continue
        p = queues[k].popleft()
        q = quanta[k]
        run = rem[p.pid] if q is None else min(q, rem[p.pid])
        higher = [x.arrival for x in pending if level[x.pid] < k]
        preempted = bool(higher) and min(higher) < t + run
        if preempted:
            run = min(higher) - t
        segs.append((p.pid, t, t + run))
        t += run
        rem[p.pid] -= run
        admit()
        if rem[p.pid] == 0:
            continue
        if preempted:
            queues[k].appendleft(p)
        elif feedback:                                  # used the full quantum: demote
            level[p.pid] = min(k + 1, 2)
            queues[level[p.pid]].append(p)
        else:
            queues[k].append(p)
    return segs


def _merge(segs):
    """Join neighbouring segments of the same process (or idle)."""
    out = []
    for pid, s, e in segs:
        if s == e:
            continue
        if out and out[-1][0] == pid and out[-1][2] == s:
            out[-1] = (pid, out[-1][1], e)
        else:
            out.append((pid, s, e))
    return out


def _finalize(ps, segs):
    for p in ps:
        mine = [s for s in segs if s[0] == p.pid]
        p.start, p.completion = mine[0][1], mine[-1][2]
        p.remaining, p.state = 0, "Terminated"


def simulate(algo, procs, quantum=4, preemptive=False):
    """Run one algorithm on COPIES of procs and return a Result."""
    algo = ALIASES.get(algo, algo)
    if algo not in ALGO_NAMES:
        raise SchedError(f"unknown algorithm '{algo}' (use fcfs, sjn, priority, rr, mlq, mlfq)")
    if quantum < 1:
        raise SchedError("the time quantum must be at least 1")
    ps = [p.copy() for p in procs]
    name = ALGO_NAMES[algo]
    if algo == "sjn" and preemptive:
        name = "SJN (preemptive, SRTF)"
    elif algo == "priority" and preemptive:
        name = "Priority (preemptive)"
    elif algo in ("rr", "mlq", "mlfq"):
        name += f" (quantum={quantum})"
    if not ps:
        return Result(algo, name, ps, [])

    if algo == "fcfs":
        segs = _fcfs(ps)
    elif algo == "sjn":
        segs = (_preemptive(ps, lambda p, r: r) if preemptive
                else _nonpreemptive(ps, lambda p: p.burst))
    elif algo == "priority":
        segs = (_preemptive(ps, lambda p, r: p.priority) if preemptive
                else _nonpreemptive(ps, lambda p: p.priority))
    elif algo == "rr":
        segs = _round_robin(ps, quantum)
    else:
        segs = _multilevel(ps, quantum, feedback=(algo == "mlfq"))
    segs = _merge(segs)
    _finalize(ps, segs)
    return Result(algo, name, ps, segs)


# ----------------------------------------------------- states and reporting
def state_at(p, segments, t):
    """State of process p at time t, derived from the Gantt chart."""
    if t < p.arrival:
        return "New"
    if t >= p.completion:
        return "Terminated"
    for pid, s, e in segments:
        if pid == p.pid and s <= t < e:
            return "Running"
    return "Ready"


def remaining_at(p, segments, t):
    done = sum(max(0, min(e, t) - s) for pid, s, e in segments if pid == p.pid)
    return p.burst - done


def state_changes(result):
    """List of (time, pid, old_state, new_state) in chronological order."""
    ev = []
    for p in result.procs:
        ev.append((p.arrival, 1, p.pid, "New", "Ready"))
        for pid, s, e in result.segments:
            if pid != p.pid:
                continue
            ev.append((s, 2, p.pid, "Ready", "Running"))
            ev.append((e, 0, p.pid, "Running", "Terminated" if e == p.completion else "Ready"))
    ev.sort(key=lambda x: (x[0], x[1]))
    return [(t, pid, a, b) for t, _, pid, a, b in ev]


def render_gantt(segments):
    """Two-line text Gantt chart: process boxes on top, time marks below."""
    if not segments:
        return "(nothing ran)"
    total = segments[-1][2] - segments[0][1]
    scale = 1 if total <= 40 else 40 / total
    top, bottom = "", ""
    for pid, s, e in segments:
        label = pid if pid is not None else "idle"
        width = max(len(label) + 2, len(str(s)), len(str(e)), int(round((e - s) * scale)))
        top += "|" + label.center(width)
        bottom += str(s).ljust(width + 1)
    return top + "|\n" + bottom + str(segments[-1][2])


def pcb_table(procs, state=None):
    rows = [(p.pid, p.arrival, p.burst, p.priority, state or p.state) for p in procs]
    return format_table(["PID", "Arrival", "Burst", "Priority", "State"], rows)


def print_result(result, ctx, trace=False, at=None):
    ctx.println(f"=== [Module 2 Scheduler] {result.name} ===")
    if not result.procs:
        ctx.println("No processes to schedule.")
        return
    ctx.println("PCB table (before scheduling):")
    ctx.println(pcb_table(result.procs, "New"))
    ctx.println()
    ctx.println("Gantt chart:")
    ctx.println(render_gantt(result.segments))
    ctx.println()
    rows = [(p.pid, p.arrival, p.burst, p.priority, p.completion, p.turnaround,
             p.waiting, p.response, p.state) for p in result.procs]
    ctx.println("Results (PCB table after scheduling):")
    ctx.println(format_table(["PID", "Arrival", "Burst", "Priority", "Completion",
                              "Turnaround", "Waiting", "Response", "State"], rows))
    ctx.println()
    ctx.println(f"Average waiting time:    {result.avg_waiting():.2f}")
    ctx.println(f"Average turnaround time: {result.avg_turnaround():.2f}")
    if at is not None:
        ctx.println()
        ctx.println(f"PCB snapshot at t={at}:")
        snap = [(p.pid, state_at(p, result.segments, at), remaining_at(p, result.segments, at))
                for p in result.procs]
        ctx.println(format_table(["PID", "State", "Remaining"], snap))
    if trace:
        ctx.println()
        ctx.println("State transitions:")
        for t, pid, a, b in state_changes(result):
            ctx.println(f"  t={t:<4} {pid}: {a} -> {b}")


# ------------------------------------------------------------ shell command
SCHED_USAGE = ("usage: sched ALGO [--quantum N] [--preemptive] [--trace] [--at T] [FILE]\n"
               "       ALGO = fcfs | sjn | priority | rr | mlq | mlfq | show")


def parse_sched_options(args, ctx, cmd):
    """Shared option parser for `sched` and `compare`. Returns dict or None on error."""
    opts = {"quantum": 4, "preemptive": False, "trace": False, "at": None, "operands": []}
    i = 0
    while i < len(args):
        a = args[i]
        value = None
        if a in ("--quantum", "-q", "--at"):
            if i + 1 >= len(args):
                ctx.error(f"{cmd}: option {a} needs a value")
                return None
            value = args[i + 1]
            i += 1
        elif a.startswith("--quantum=") or a.startswith("--at="):
            a, value = a.split("=", 1)
        if a in ("--quantum", "-q"):
            n = parse_int(value)
            if n is None or n < 1:
                ctx.error(f"{cmd}: the quantum must be a whole number >= 1")
                return None
            opts["quantum"] = n
        elif a == "--at":
            n = parse_int(value)
            if n is None or n < 0:
                ctx.error(f"{cmd}: --at needs a time >= 0")
                return None
            opts["at"] = n
        elif a in ("--preemptive", "-p"):
            opts["preemptive"] = True
        elif a == "--trace":
            opts["trace"] = True
        elif a.startswith("-") and a != "-":
            ctx.error(f"{cmd}: unknown option '{a}'")
            return None
        else:
            opts["operands"].append(a)
        i += 1
    return opts


def load_processes(filename, ctx, cmd):
    """Read processes from FILE, from redirected/piped input, or by asking the user."""
    if filename and filename != "-":
        resolved = filename
        if not os.path.exists(resolved):
            candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", filename)
            if os.path.exists(candidate):
                resolved = candidate
        try:
            text = read_text_file(resolved)
        except OSError as e:
            ctx.error(f"{cmd}: {filename}: {os_error_text(e)}")
            return None
    elif ctx.stdin is not None:
        text = ctx.stdin
    else:
        ctx.println("Enter processes as 'PID ARRIVAL BURST [PRIORITY]', blank line to finish:")
        lines = []
        while True:
            try:
                line = input("process> ")
            except EOFError:
                break
            if not line.strip():
                break
            lines.append(line)
        text = "\n".join(lines)
    try:
        return parse_processes(text)
    except SchedError as e:
        ctx.error(f"{cmd}: {e}")
        return None


def cmd_sched(args, ctx):
    if args and args[0].lower() in ("compare", "all"):
        from report import cmd_compare
        return cmd_compare(args[1:], ctx)
    opts = parse_sched_options(args, ctx, "sched")
    if opts is None:
        return 1
    ops = opts["operands"]
    if not ops or len(ops) > 2:
        ctx.error(SCHED_USAGE)
        return 1
    algo = ALIASES.get(ops[0].lower(), ops[0].lower())
    if algo != "show" and algo not in ALGO_NAMES:
        ctx.error(f"sched: unknown algorithm '{ops[0]}'\n{SCHED_USAGE}")
        return 1
    procs = load_processes(ops[1] if len(ops) > 1 else None, ctx, "sched")
    if procs is None:
        return 1
    if algo == "show":
        ctx.println("PCB table:")
        ctx.println(pcb_table(procs, "New") if procs else "No processes loaded.")
        return 0
    try:
        result = simulate(algo, procs, opts["quantum"], opts["preemptive"])
    except SchedError as e:
        ctx.error(f"sched: {e}")
        return 1
    print_result(result, ctx, opts["trace"], opts["at"])
    return 0


class _StreamCtx:
    """Adapter context connecting MiniShell's (stdin, stdout, stderr) streams to cmd_sched."""

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


def run_sched(args, stdin, stdout, stderr) -> int:
    """MiniShell IntegrationRegistry entry point for Module 2 (`sched` command)."""
    ctx = _StreamCtx(stdin, stdout, stderr)
    return cmd_sched(list(args), ctx)


def sched_command(args, stdin=None):
    """Tuple-returning entry point (stdout_str, stderr_str, exit_code) for compatibility."""
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    ctx = _StreamCtx(None, out_buf, err_buf, override_stdin=stdin)
    code = cmd_sched(list(args), ctx)
    return out_buf.getvalue(), err_buf.getvalue(), code


if __name__ == "__main__":
    sys.exit(run_sched(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr))
