# MiniShell + Simulated OS (CmpSc 123 Group Project — All 4 Members Integrated)

This package combines and integrates the code from **all 4 group members** into a single working MiniShell build:
- **Member 1 (Shell Lead — Denzel):** `minishell.py`, `test_shell_lead.py` — Interactive REPL, parser, file/directory built-ins, `chmod` & `ls -l`, stream redirection (`>`, `>>`, `<`, `2>`, `2>&1`), multi-stage pipelines (`|`), variables (`NAME=value`, `$NAME`, `$?`, `env`), conditionals (`&&`, `||`, `;`, bonus `if/then/else/fi`), and command integration registry.
- **Member 2 (Scheduler Lead — Accel):** `scheduler.py`, `samples/processes*.txt` — Process Control Block (PCB) simulator implementing all 6 CPU scheduling algorithms from scratch (`fcfs`, `sjn` with `--preemptive`, `priority` with `--preemptive`, `rr`, `mlq`, `mlfq`), Gantt chart, `--at T` PCB snapshots, and `--trace` state transitions.
- **Member 3 (Resources Lead — Gregorio):** `deadlock.py`, `util.py`, `samples/system*.txt`, `tests/test_deadlock.py` — Deadlock detection (`deadlock detect`), bonus recovery plan (process termination & preemption suggestions), Banker's safety check (`deadlock banker`), and resource-request verification (`--request`).
- **Member 4 (Docs & Testing Lead):** `grep_cmd.py`, `report.py`, `samples/notes.txt`, `samples/processes1-3.txt`, `tests/test_member4.py` — `grep` with `-i -n -v -c -o -E --groups`, Module 4 `compare` command across all 6 scheduling algorithms with ASCII bar charts, and 16 unit/CLI tests.

## 1. Quick Start (Run & Verify)

Requires **Python 3.8+** (standard library only — no external packages to install).

```bash
# Start interactive MiniShell (prompt: minishell>)
python3 minishell.py

# Run the complete 4-member automated demo script
python3 minishell.py demo.msh

# Run all 4 automated test suites (46 tests total: 9 + 17 + 16 + 4)
make test
```

## 2. Live Video Presentation Commands (Inside `python3 minishell.py` or Standalone)

### Member 1: Shell Lead (Module 1 — Shell Core, Redirection, Pipes & Variables)
```bash
pwd
mkdir demo_dir && cd demo_dir
touch report.txt notes.txt script.sh image.png
chmod 755 script.sh
chmod 640 report.txt
ls -l
echo "Process_A arrival=0 burst=5" > report.txt
echo "Process_B arrival=2 burst=3" >> report.txt
cat < report.txt
cat missing_file.txt 2> error.log
cat error.log
ls | grep txt
COURSE=CmpSc123
ROLE="Shell Lead"
echo "Course: $COURSE | Role: $ROLE"
true && echo "Success branch triggered"
false || echo "Fallback branch triggered"
if grep Process_A report.txt > /dev/null; then echo "Found Process_A!"; else echo "Missing!"; fi
cd .. && rm -rf demo_dir
```

### Member 2: Scheduler Lead (Module 2 — CPU Scheduling Simulator)
```bash
sched fcfs samples/processes1.txt
sched sjn samples/processes1.txt
sched sjn --preemptive --trace --at 3 samples/processes1.txt
sched priority samples/processes1.txt
sched rr --quantum 4 samples/processes1.txt
sched mlq --quantum 4 samples/processes2.txt
sched mlfq --quantum 4 samples/processes3.txt
sched fcfs samples/processes_single.txt
sched fcfs samples/processes_empty.txt
```

### Member 3: Resources Lead — Gregorio (Module 3 — Deadlock Detection & Banker's Algorithm)
```bash
deadlock banker samples/system_safe.txt
deadlock banker samples/system_safe.txt --request 1 1 0 2
deadlock banker samples/system_after_p1.txt --request 0 0 2 0
deadlock detect samples/system_deadlock.txt
deadlock banker < samples/system_single.txt
deadlock banker samples/system_bad.txt
```

### Member 4: Docs & Testing Lead (`grep` Regex/Groups & Module 4 `compare`)
```bash
grep -n -i deadlock samples/notes.txt
grep -E "[0-9]+-[0-9]+" samples/notes.txt
grep -oE "[0-9]+-[0-9]+" samples/notes.txt
grep -E --groups "([0-9]+)-([0-9]+)" samples/notes.txt
compare --quantum 4 samples/processes1.txt
compare --quantum 4 samples/processes2.txt
compare --quantum 2 samples/processes3.txt
compare < samples/processes2.txt
```
