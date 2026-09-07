# Cooperative Multi-Agent Gridworld

**CSC 4800 — Adrian Cardona**

This project is a deterministic, terminal-based simulation that compares two
ways for agents to collect packages in an 8 x 8 gridworld:

- **Baseline agents** work independently and do not communicate.
- **Coordinated agents** share package locations, claim targets, release
  completed targets, and yield to avoid local conflicts.

Both policies run on the same fixed scenarios, follow the same scoring rules,
and only see a local 3 x 3 area around themselves. This keeps the comparison
focused on what communication and coordination add to the agents' behavior.

## Requirements

- Python 3.10 or newer
- No third-party packages

Run all commands from the project root. On macOS and Linux, check the active
Python version with:

```bash
python3 --version
```

If `python` already points to Python 3.10 or newer on your system, you can use
it instead of `python3` in the commands below.

## Quick start

Run the tests first:

```bash
python3 simulator.py --run-tests
```

Then run either policy on the default scenario, seed 42:

```bash
python3 simulator.py --run-baseline
python3 simulator.py --run-coordinated
```

A single-policy run prints every action followed by a final summary. Add
`--summary-only` to hide the step-by-step trace:

```bash
python3 simulator.py --run-coordinated --seed 101 --summary-only
```

To compare both policies across all three scenarios, run:

```bash
python3 simulator.py --run-experiments
```

## Command reference

| Command | What it does |
| --- | --- |
| `python3 simulator.py --run-baseline` | Runs the independent policy. |
| `python3 simulator.py --run-coordinated` | Runs the communicating policy. |
| `python3 simulator.py --run-experiments` | Runs both policies on all fixed scenarios and prints a comparison table. |
| `python3 simulator.py --run-tests` | Runs the built-in test suite. |
| `python3 run_demo.py` | Runs a full baseline trace on seed 42. |
| `python3 simulator.py --help` | Shows every command-line option. |

Exactly one `--run-*` mode is required. For a baseline or coordinated run,
`--seed` can be `42`, `101`, or `2023` and defaults to `42`. Use
`--summary-only` with those single-policy runs when the trace is not needed.
The seed numbers select hard-coded scenarios; they do not generate random maps.

## Project structure

```text
.
├── simulator.py
├── run_demo.py
├── gridworld/
│   ├── agents.py
│   ├── environment.py
│   ├── models.py
│   ├── runner.py
│   └── scenarios.py
└── tests/
    └── test_environment.py
```

`simulator.py` is the main implementation. It contains the environment, data
models, agent policies, fixed scenarios, runner, command-line interface, and
tests. `run_demo.py` is a small shortcut for the baseline demo.

The files in `gridworld/` provide import-friendly names that point back to the
implementation in `simulator.py`. `tests/test_environment.py` exposes the
built-in test class to standard `unittest` discovery.

## World setup

Coordinates use `(row, column)`. Moving north lowers the row, and moving west
lowers the column.

Every scenario has the same basic setup:

- Grid size: 8 x 8
- Base: `(0, 0)`
- `Agent_1` start: `(0, 7)`
- `Agent_2` start: `(7, 0)`
- Packages: 4
- Obstacles: 5
- Turn limit: 60
- Carrying limit: 1 package per agent

The scenario seed selects these fixed obstacle and package locations:

| Seed | Obstacles | Packages |
| ---: | --- | --- |
| 42 | `(2, 2)`, `(2, 3)`, `(2, 4)`, `(4, 2)`, `(4, 4)` | `P1 (1, 5)`, `P2 (3, 3)`, `P3 (5, 6)`, `P4 (6, 1)` |
| 101 | `(2, 3)`, `(3, 3)`, `(4, 3)`, `(2, 5)`, `(4, 5)` | `P1 (1, 1)`, `P2 (3, 4)`, `P3 (5, 5)`, `P4 (6, 2)` |
| 2023 | `(3, 2)`, `(3, 3)`, `(3, 4)`, `(5, 2)`, `(5, 4)` | `P1 (1, 6)`, `P2 (4, 3)`, `P3 (6, 1)`, `P4 (4, 6)` |

## Agent and environment boundary

The environment owns the full map, score, package state, mailboxes, and true
agent positions. An agent only receives an immutable `Percept` containing its
local 3 x 3 view, the clock, its carried package, the previous action status,
and its current inbox. Absolute position is not included, so each agent keeps
an estimate and builds its own map from local observations.

An `Action` can combine three things in one turn:

- one movement: north, south, east, west, or wait;
- one interaction: pickup, drop, or none; and
- at most one message.

### PEAS description

| Part | This simulation |
| --- | --- |
| Performance | Deliver packages, limit movement costs, avoid invalid actions and collisions, and finish within 60 turns. |
| Environment | An 8 x 8 grid with one base, five obstacles, four packages, and two agents. |
| Actuators | Move or wait, pick up or drop a package, and send one message. |
| Sensors | A local 3 x 3 view, the clock, the carried package ID, the previous action status, and messages from the previous turn. |

## Turn order

Each turn follows the same order:

1. The environment creates a percept for each agent.
2. Both agents choose an action before any shared state changes.
3. The environment resolves all movement and collisions together.
4. Valid interactions are applied at each agent's final position.
5. Messages are staged and become available on the next turn.

Each message appears only in the recipient's next-turn inbox. The episode ends
when all packages are delivered or the 60-turn limit is reached. The final
unfinished-package penalty is applied once when the run ends.

## Environment rules and scoring

The team starts with a score of zero. Rewards and penalties are added as the
run continues:

| Event | Score change |
| --- | ---: |
| Deliver a package at the base | `+10` |
| Attempt a non-wait movement | `-1` |
| Move out of bounds or into an obstacle | additional `-2` |
| Attempt an invalid pickup or drop | `-2` |
| Create one collision pair | `-3` |
| Leave a package unfinished at the end | `-5` |

Waiting, successful pickup, a valid non-base drop, and communication have no
direct score cost.

Movement is blocked when agents try to enter the same cell, swap cells, or
enter a cell whose occupant does not successfully move away. If movement is
invalid or blocked, that agent's pickup or drop is not attempted. The reported
collision count records each unique agent pair involved in a collision on that
turn, not the number of individual agents that were blocked. For example, two
agents moving toward the same empty cell cost 5 points total: 1 point for each
movement attempt and 3 points for the collision pair.

An agent can pick up an available package only when it is not already carrying
one. Dropping at `(0, 0)` delivers the package and earns 10 points. Dropping on
another cell is allowed when that cell does not already hold a package, but the
package remains unfinished and must still be delivered later.

## Policy comparison

### Baseline policy

Each baseline agent keeps its own terrain and package memory. It uses an
A*-style search through known and still-unexplored cells, collects a known
package when possible, and returns carried packages to the base. When no
package is known, it explores using a fixed direction order. Baseline agents
do not inspect their inboxes or send messages.

### Coordinated policy

The coordinated agents use the same local mapping and route planning, with an
extra communication and conflict-avoidance layer:

- `DISCOVER` shares a package ID and location after an agent sees it.
- `CLAIM` shares the package an agent plans to collect and its Manhattan
  distance when the claim is created.
- `RELEASE` clears a claim after delivery, abandonment, or a lost claim.

Messages sent during turn `t` become visible during turn `t + 1`. Each action
can carry only one message, so later messages wait in the agent's queue. If two
agents claim the same package, the shorter recorded distance wins. If those
distances match, the lower agent number wins, so `Agent_1` wins a tie over
`Agent_2`.

Coordinated agents also yield when a planned move would enter an occupied cell.
The higher-numbered agent can wait when both agents could choose the same nearby
cell. This local rule helps prevent conflicts before the environment has to
block either move.

## Reading the output

A single-policy run prints one event for each agent on every turn. A trace line
looks like this:

```text
[00 | Agent_1 | clock=0, carrying=-, packages=- | received=-, sent=- | WEST/NONE | moved/not_attempted, pos=(0, 6)]
```

From left to right, it shows the turn, agent, percept summary, received and sent
messages, chosen movement and interaction, action result, and final position.
The package list contains only packages visible in that turn's local view. The
final position is included for debugging even though the agent does not receive
its absolute position.

Every run ends with a summary containing the policy, scenario seed, deliveries,
team score, collision count, and number of turns. `--run-experiments` prints the
same measurements as a Markdown table.

## Reproducible comparison

The current implementation produces this table with
`python3 simulator.py --run-experiments`:

| Map Seed | Policy | Deliveries | Team Score | Collision Attempts | Steps |
| ---: | --- | ---: | ---: | ---: | ---: |
| 42 | Baseline | 3 | -102 | 3 | 60 |
| 42 | Coordinated | 4 | -67 | 0 | 54 |
| 101 | Baseline | 3 | -102 | 3 | 60 |
| 101 | Coordinated | 4 | -61 | 0 | 52 |
| 2023 | Baseline | 3 | -120 | 9 | 60 |
| 2023 | Coordinated | 4 | -49 | 0 | 46 |

For these fixed scenarios, coordination delivers every package before the
60-turn limit and avoids the repeated conflicts seen in the baseline runs.
The score is useful alongside deliveries and steps because every movement,
invalid action, collision, and unfinished package changes the final total.

## Tests

The project includes 13 `unittest` cases covering local perception, movement
penalties, same-cell and swap collisions, pickup and delivery, legal package
drops, blocked interactions, next-turn messages, baseline silence, all three
coordination messages, claim tie-breaking, fixed scenario shape, and complete
coordinated runs.

Run them through the simulator:

```bash
python3 simulator.py --run-tests
```

They can also be discovered through the standard library test runner:

```bash
python3 -m unittest discover -s tests -v
```
