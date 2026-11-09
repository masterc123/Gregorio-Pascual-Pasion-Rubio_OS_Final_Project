# Module 3: Deadlock Simulator (Resources Lead)

Detection and Banker's algorithm for the MiniShell project. Pure Python 3.8+, no packages to install.
Files: `deadlock.py` (all the logic), `util.py` (table printing and number parsing), `samples/`, `tests/`.

## Run it

Standalone, from this folder:

```
python3 deadlock.py detect samples/system_deadlock.txt
python3 deadlock.py detect samples/system_safe.txt
python3 deadlock.py banker samples/system_safe.txt
python3 deadlock.py banker samples/system_safe.txt --request 1 1 0 2
python3 deadlock.py banker samples/system_after_p1.txt --request 0 0 2 0
python3 deadlock.py banker < samples/system_single.txt        # input from redirection also works
python3 -m unittest discover -s tests -v                      # 17 tests
```
(On Windows use `python` or `py` instead of `python3`.)

Inside MiniShell the same command works as `deadlock detect FILE` and `deadlock banker FILE [--request P R1 R2 ...]`:
copy `deadlock.py` into the MiniShell folder (it replaces the one there) and nothing else needs changing.

## Input file

```
processes 5          # number of processes (called P0, P1, ... in order)
resources 3          # number of resource types
allocation           # n rows of m numbers: what each process holds now
0 1 0
...
max                  # n rows: the most each process may ever need (required for banker)
7 5 3
...
request              # OPTIONAL n rows: what each process is waiting for right now
...
available            # one row of m numbers: free units of each resource
3 3 2
```
`#` starts a comment. `detect` uses the `request` matrix if there is one, otherwise it treats `Need = Max - Allocation`
as the outstanding request.

## Exit status

0 = no deadlock / state safe / request granted. 1 = deadlock / unsafe / request denied. 2 = bad input or bad usage.

## The algorithms (what to explain in the demo)

**Detection** (`detect`)
1. `Work = Available`. A process that holds nothing is marked finished (it cannot be part of a deadlock).
2. Find an unfinished process whose request is `<= Work`. Assume it finishes: `Work = Work + its Allocation`, mark it finished.
3. Repeat until no such process exists. Processes that are still unfinished are **deadlocked**.
4. Bonus recovery: terminate the process holding the most resources, release its resources, run detection again,
   and repeat until no deadlock is left. It also suggests preempting that process's resources instead.

**Banker's safety check** (`banker`)
1. `Need = Max - Allocation`. `Work = Available`.
2. Find an unfinished process with `Need <= Work`; it can run to completion, so `Work = Work + Allocation`. Record it.
3. If all processes get recorded, the state is **safe** and the recorded order is the **safe sequence**.
   If some cannot, the state is **unsafe**.

**Resource request** (`banker ... --request P R1 R2 ...`)
1. If `Request > Need`: error, the process exceeded its declared maximum.
2. If `Request > Available`: the process must wait.
3. Otherwise pretend to grant it (`Available -= Request`, `Allocation += Request`, `Need -= Request`) and run the safety check.
   Safe: **granted**. Unsafe: **denied** (the pretend allocation is thrown away).

## Samples (also your 3+ test inputs with an edge case)

| File | What it shows |
|---|---|
| `system_safe.txt` | safe state, safe sequence `< P1, P3, P4, P0, P2 >`; `--request 1 1 0 2` is granted |
| `system_after_p1.txt` | same system after that grant; `--request 0 0 2 0` is denied (unsafe), `--request 4 3 3 0` must wait |
| `system_deadlock.txt` | real deadlock (P0 -> P1 -> P2 -> P0 circular wait), banker says unsafe |
| `system_single.txt`, `system_empty.txt` | edge cases: one process, zero processes |
| `system_bad.txt` | invalid file: a clear error message and exit status 2 |

## Suggested 2-minute demo order

1. `python3 deadlock.py banker samples/system_safe.txt`  (safe, show the sequence and the steps)
2. `python3 deadlock.py banker samples/system_safe.txt --request 1 1 0 2`  (granted)
3. `python3 deadlock.py banker samples/system_after_p1.txt --request 0 0 2 0`  (denied, unsafe)
4. `python3 deadlock.py detect samples/system_deadlock.txt`  (deadlock found + recovery suggestion)
5. `python3 deadlock.py banker samples/system_bad.txt`  (error case)
