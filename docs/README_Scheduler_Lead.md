# MiniShell + Simulated OS (CmpSc 123 Project)

A small Bash-like shell written in Python 3 (standard library only) that also simulates
CPU scheduling and deadlock handling.

## Build and run

No build step. Python 3.8+ is needed.

```
python3 minishell.py              # interactive shell (prompt: minishell> ; type exit to quit)
python3 minishell.py demo.msh     # run a script of commands
python3 minishell.py -c "ls | grep txt"
python3 -m unittest -v test_minishell   # run all tests
```

## Files

| File | Purpose | Module |
|---|---|---|
| `minishell.py` | prompt loop, tokenizer, parser, built-ins, redirection, pipes, variables, conditionals | 1 |
| `grep_cmd.py` | grep-like search | 1 |
| `scheduler.py` | PCB, six scheduling algorithms, Gantt chart, comparison | 2, 4 |
| `deadlock.py` | detection, Banker's algorithm, request handling, recovery | 3 |
| `test_minishell.py` | unit tests (shell, grep, scheduler, deadlock, including edge cases) | tests |
| `processes*.txt`, `system*.txt` | sample inputs for the simulators | samples |
| `demo.msh` | demo script covering every module | demo |

## Command reference

**Files and directories:** `pwd`, `cd [dir|-]`, `ls [-l] [-a] [paths]`, `mkdir [-p]`, `rmdir`, `touch`,
`cp [-r]`, `mv`, `rm [-r] [-f]`, `cat [files]`

**Permissions:** `chmod 755 file` (numeric, 3-4 octal digits). Symbolic modes such as `u+x`, `go-w`, `a=r` also work.
`ls -l` shows permissions.

**Text:** `echo [-n]`, `wc [-l -w -c]`, `sort [-r -n]`, `head [-n N]`, `tail [-n N]`,
`grep [-i -v -n -c -o -F] PATTERN [files]`

**Variables:** `NAME=value`, `echo $NAME` / `${NAME}`, `$?` (last exit code), `env`, `unset NAME`, `export NAME=value`.
Single quotes stop expansion; double quotes allow it.

**Operators:** `>` `>>` `<` `2>` `2>&1`, pipes `a | b | c`, and `;` `&&` `||`.
Bonus: one-line `if cmd; then cmd; else cmd; fi` (nesting works).

**Other:** `help`, `clear`, `exit [code]`. Commands that are not built in (e.g. `date`) are run as real programs if they exist;
otherwise the shell prints `command not found`. Wildcards (`*.txt`) and `~` are expanded.

### grep
`grep PATTERN file` prints every line containing the text. The bonus regex features (`.`, `[a-z]`, `*`, `+`, `?`, `\` escapes, `(groups)`)
are on by default through Python's `re`; use `-F` for plain text only. `-o` prints only the matched part
(so you can see what a group matched). Exit code is 0 for a match, 1 for none, 2 for errors.

### sched - process scheduling (Module 2)
```
sched ALGO [--quantum N] [--preemptive] [--trace] [FILE]
sched compare [--quantum N] [FILE]
```
ALGO: `fcfs`, `sjn`, `priority`, `rr`, `mlq`, `mlfq`.
Processes come from `FILE`, a pipe (`cat processes1.txt | sched fcfs`), `--procs "P1,0,5,2;P2,1,3,1"`, or are typed in on a terminal.

Process file: one `PID arrival burst [priority]` per line (`#` comments allowed). Lower priority number = more important.

Each run prints the PCB table (states), a text Gantt chart, per-process turnaround / waiting / response times, and averages.
`--trace` also prints every process's state (New, Ready, Running, Terminated) at each context switch.
(The simulator is CPU-only, so the Waiting state for I/O is never entered.)

Design choices (documented so the demo can explain them):
* `sjn` and `priority` are non-preemptive by default; `--preemptive` gives SRTF / preemptive priority.
* `rr`: new arrivals join the queue before the process whose slice just ended.
* `mlq`: three fixed queues by priority (1-2: RR quantum Q, 3-4: RR quantum 2Q, 5+: FCFS). Higher queues always run first and preempt lower ones.
* `mlfq`: everything starts in Q0 (quantum Q); using a whole slice demotes to Q1 (2Q), then Q2 (FCFS). Higher queues preempt lower ones.
* Every algorithm produces a per-time-unit timeline; completion, waiting and turnaround are computed from that one timeline,
  so all algorithms are measured identically. `Turnaround = Completion - Arrival`, `Waiting = Turnaround - Burst`.

### deadlock - deadlock simulator (Module 3)
```
deadlock detect FILE
deadlock banker FILE [--request PID r1 r2 ...]
```
System file: `processes N`, `resources M`, then `allocation`, `max`, `available` (and optionally `request`) - see `system_safe.txt`.
* `detect` lists deadlocked processes (using the `request` matrix, or `max - allocation` if there is none) and prints a recovery suggestion (bonus).
* `banker` prints the Need matrix, the safety check steps, and the safe sequence (or says the state is unsafe).
  With `--request P1 1 0 2` it also says whether the request can be granted (and whether granting keeps the system safe).

## Sample inputs (at least 3 per simulator, each with an edge case)

| Simulator | Files |
|---|---|
| sched | `processes1.txt` (normal), `processes_convoy.txt` (convoy effect), `processes_idle.txt` (CPU idle gap), `processes_single.txt` (edge: 1 process), `processes_empty.txt` (edge: empty queue) |
| deadlock | `system_safe.txt` (safe), `system_unsafe.txt` (unsafe), `system_deadlock.txt` (real deadlock), `system_single.txt` (edge: 1 process) |

## Module 4 comparison

`sched compare processes1.txt` (also `processes_convoy.txt`) runs the same processes through all six algorithms and prints a table, bar chart and the best
algorithm for waiting, turnaround and response time. Use that output (your own data) in the written report.

## Error handling

Unknown commands, missing files, bad options and bad input files print a clear message and the shell keeps running; the main loop also
catches unexpected exceptions, so it should never crash. Failed commands set `$?` and work with `&&` / `||`.

## Limitations

* Pipes run one command after another and pass text between them (no real concurrency); external programs are run to completion and cannot be interactive.
* `if` statements must be written on one line (use `;` before `then`, `else`, `fi`).
* No background jobs (`&`), here-docs, or quoting/escaping inside `[...]` globs.
