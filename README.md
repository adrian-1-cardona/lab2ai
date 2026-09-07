# Cooperative Multi-Agent Gridworld

**CSC 4800 — Adrian Cardona**

This project compares two ways for agents to work together while collecting
packages in an 8 x 8 gridworld:

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
`--seed` can be `42`, `101`, or `2023` and defaults to `42`. These numbers
select hard-coded scenarios; they do not generate random maps.

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

## How the simulation works

Each turn follows the same order:

1. The environment gives each agent an immutable local percept.
2. Both agents choose an action before the world changes.
3. The environment resolves movement and collisions together.
4. Valid pickup and drop interactions are applied.
5. Messages are staged for the next turn.

The environment owns the full map, score, package state, mailboxes, and true
agent positions. Agents never receive the environment object or their absolute
position. They estimate where they are and build their own maps from local
observations.

### PEAS description

| Part | This simulation |
| --- | --- |
| Performance | Deliver packages, limit movement costs, avoid invalid actions and collisions, and finish within 60 turns. |
| Environment | An 8 x 8 grid with one base, five obstacles, four packages, and two agents. |
| Actuators | Move north, south, east, or west; wait; pick up; drop; and send one message. |
| Sensors | A local 3 x 3 view, the clock, the carried package ID, the previous action status, and messages from the previous turn. |

## Policy comparison

The baseline policy keeps a local terrain and package map, plans routes through
known and unexplored cells, and brings any carried package back to the base. It
does not read or send messages.

The coordinated policy uses the same local mapping and route planning, then
adds package messages, deterministic claim handling, and local movement
yielding. It uses three message types:

- `DISCOVER` shares a package ID and location.
- `CLAIM` tells the other agent which package it plans to collect.
- `RELEASE` clears a claim when the package is delivered or abandoned.

Messages sent during turn `t` become visible during turn `t + 1`. If both
agents claim the same package, the shorter recorded Manhattan distance wins.
If the distances match, `Agent_1` wins the tie.

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
The score is still useful alongside deliveries and steps because every move,
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
