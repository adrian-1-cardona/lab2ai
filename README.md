# CSC 4800: Adrian Cardona

## Cooperative Multi-Agent Gridworld

This project implements a small environment in which two robots collect
packages and return them to a common base. The design follows the Russell and
Norvig agent model: each agent receives a local percept, retains any internal
state it chooses, and returns one action at each time step.

The included `ExampleBaselineAgent` is an intentionally weak, independent
agent. It has local memory and a simple exploration rule, but it does **not**
communicate, claim packages, or coordinate traffic. It is a comparison point,
not a solution to the lab. `CoordinatedAgentTemplate` is a runnable shell with
the coordination work left as TODOs for students.

### Run it

The project uses only the Python standard library and Python 3.10 or later.

```bash
python run_demo.py
python -m unittest discover -s tests -v
```

### What is included

| Path | Purpose |
| --- | --- |
| `gridworld/environment.py` | Environment mechanics, scoring, local perception, simultaneous moves, messages, and event logs. |
| `gridworld/models.py` | The `Percept`, `Action`, `Message`, and result data structures. |
| `gridworld/agents.py` | The independent baseline example and the incomplete coordinated-agent template. |
| `gridworld/runner.py` | A loop that asks each agent for its own action, then advances the world. |
| `gridworld/scenarios.py` | One 8 x 8 starter map with four packages, obstacles, and a bottleneck. |
| `tests/test_environment.py` | Mechanics checks students can run while extending their policy. |

### Environment contract

- Coordinates are `(row, column)`; row 0 is north and column 0 is west.
- Each agent sees only in-bounds cells in a local 3 x 3 window, its carrying
  state, its last action result, the current time, and incoming messages.
- An `Action` can request a move, a pickup/drop interaction, and one optional
  broadcast message in the same time step.
- Moves resolve simultaneously. Same-destination moves, swaps, and moves into
  an agent that stays in place are blocked and logged as collision attempts.
- A message sent at time `t` is available when the recipient next chooses an
  action at time `t + 1`.
- The team score is `+10` per delivered package, `-1` per attempted move, `-2`
  per invalid move or interaction, `-3` per collision attempt, and `-5` per
  unfinished package at the end of the episode.

`run_demo.py` prints a short event log. The full log is available as
`EpisodeResult.events`; each event records the time, agent, percept summary,
received and sent messages, action, result, and final position.

### Student starting point

1. Run the supplied independent baseline and record its deliveries, score,
   collision attempts, and steps.
2. Implement the TODOs in `CoordinatedAgentTemplate` (or create an agent class
   with the same `reset()` and `act()` methods).
3. Define local rules for `DISCOVER`, `CLAIM`, and `RELEASE` messages. Keep
   package knowledge and claims in each agent's own state; do not read the
   whole environment from the agent.
4. Compare the policy against the baseline on the starter map and on any
   additional fixed maps or seeds required by the lab.
5. Extend the tests for any new behavior that needs a contract check.

The environment intentionally does not enforce a particular claim policy.
Deciding how claims are made, respected, released, or repaired after a failed
attempt is the core multi-agent design problem for the lab.
