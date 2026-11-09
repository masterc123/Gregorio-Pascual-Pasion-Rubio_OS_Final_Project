# Member 4 (Docs and Testing Lead): grep-like search, tests, Module 4 comparison

Pure Python 3.8+, no packages to install. Run everything from this folder.

| File | What it is |
|---|---|
| `grep_cmd.py` | **Yours.** The grep-like search command |
| `report.py` | **Yours.** The `compare` command (Module 4): all six algorithms on one process file |
| `tests/test_member4.py` | **Yours.** 16 tests for grep and compare, including edge cases |
| `samples/` | **Yours.** `notes.txt` (text for grep) and the process files `processes1-3`, `_single`, `_empty`, `_ties`, `_bad` |
| `util.py` | shared helper (table printing, number parsing) |
| `scheduler.py` | **Not yours: Member 2's file.** `compare` needs it to run the six algorithms. Do not edit it here; take the latest copy from Member 2 |

## Run it

```
python3 grep_cmd.py -n -i deadlock samples/notes.txt
python3 grep_cmd.py -E "[0-9]+-[0-9]+" samples/notes.txt
python3 grep_cmd.py -oE "[0-9]+-[0-9]+" samples/notes.txt
python3 grep_cmd.py -E --groups "([0-9]+)-([0-9]+)" samples/notes.txt
cat samples/notes.txt | python3 grep_cmd.py error

python3 report.py --quantum 4 samples/processes1.txt
python3 report.py --quantum 2 samples/processes3.txt
python3 report.py < samples/processes2.txt

python3 -m unittest discover -s tests -v
```
(On Windows use `python` or `py` instead of `python3`.) Inside MiniShell the same commands are `grep ...` and `compare ...`;
copy `grep_cmd.py` and `report.py` into the MiniShell folder and nothing else needs changing.

## grep-like command

`grep [-i -n -v -c -o -E --groups] PATTERN [FILE...]` (no file = read standard input)

- Default = basic matching: a line is printed if it **contains** the text. The dot is a normal character here.
- `-i` ignore case, `-n` line numbers, `-v` invert, `-c` count, `-o` print only the matching part.
- Bonus `-E`: PATTERN is a regular expression: `.` `[a-z]` `*` `+` `?` `\` escapes and `( )` groups (Python's `re` module).
  `--groups` prints each captured group.
- Exit status: 0 = a line was selected, 1 = none, 2 = error (so `grep x f && echo found` works in the shell).

How it works (for the demo): the pattern is read from the arguments; each line of each input is tested (`pattern in line`
for plain text, `re.search` for `-E`); matching lines are printed with optional file name and line number prefixes.

## compare command (Module 4)

`compare [--quantum N] [--preemptive] [FILE]` runs FCFS, SJN, Priority, Round-Robin, Multilevel Queue and Multilevel
Feedback Queue on the same file and prints a table of average waiting / turnaround time, a bar chart of each, and the best
algorithm per measure. Exit status: 0 ok, 1 error. The numbers in the written report come from this command; one test
(`test_numbers_quoted_in_the_report`) fails if the code and the report tables ever disagree.

## Tests (16)

| Group | Tests |
|---|---|
| grep | plain match, no match (status 1), dot literal in plain mode, options, regex + groups, backslash escape, stdin, error cases |
| compare | report numbers, all six algorithms + winner, different winners per workload, quantum effect, edge cases (empty file, single process, piped input), error cases |
| command line | `grep_cmd.py` and `report.py` run as real programs: output and exit status |

Edge cases covered: empty process file, one process (all algorithms tie), no match, missing file, invalid regex, bad option.
