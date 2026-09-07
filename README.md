# CSC 4800: Adrian Cardona

## Cooperative Multi-Agent Gridworld

This project compares two ways for agents to collect packages in the same 8 x
8 world. The baseline agents work independently. The coordinated agents share
package discoveries, claim targets, and release those claims when the work is
done.

Everything needed to run the lab is in `simulator.py`. It only uses the Python
standard library.

### Run it

Use Python 3.10 or newer.

```bash
python simulator.py --run-tests
python simulator.py --run-coordinated --seed 42
python simulator.py --run-baseline --seed 42
python simulator.py --run-experiments
```

Single-policy runs print the full step log. Add `--summary-only` when only the
final numbers are needed.

### PEAS description

| Part | This simulation |
| --- | --- |
| Performance | Deliver packages, avoid invalid actions and collisions, and finish within 60 steps. |
| Environment | An 8 x 8 grid with one base, five obstacles, four packages, and two agents. |
| Actuators | Move north, south, east, or west; wait; pick up; drop; and send one message. |
| Sensors | A local 3 x 3 view, the clock, the carried package ID, the last action status, and the previous turn's messages. |

### Agent and environment boundary

The environment owns the full map, package state, score, mailboxes, and agent
locations. An agent never receives the environment object. Its `act()` method
only receives an immutable `Percept` with a 3 x 3 local view. Each agent builds
its own map from those views and keeps its estimated position in local memory.

The environment asks both agents for an action before changing the world. It
then resolves both moves together. A same-square attempt or a swap blocks both
agents. Pickup, drop, and delivery updates happen once in the shared state.

### Messages and claims

The coordinated policy uses three message types:

- `DISCOVER(package_id, location)` shares a package location.
- `CLAIM(package_id, agent_id, distance)` says which agent is taking it.
- `RELEASE(package_id)` clears the claim after delivery or after losing a tie.

Messages sent on step `t` are staged until both agents finish acting. They are
only visible in the recipient's percept on step `t + 1`.

If both agents claim the same package, the shorter Manhattan distance wins. If
the distances match, the lower agent number wins, so `Agent_1` wins a tie over
`Agent_2`. Both agents run that rule using their own local state.

The baseline policy does not read messages, send messages, or track claims. It
uses the same local navigation code so the comparison stays focused on the
coordination behavior.

### Maps and scoring

Seeds 42, 101, and 2023 select three fixed maps. Each map has exactly five
obstacles and four packages. The obstacle groups leave a one-cell channel in
the middle of the map, which gives both agents a bottleneck to handle.

The team starts at zero and uses these rules:

- `+10` for each delivery
- `-1` for each attempted move
- `-2` for an invalid move or interaction
- `-3` for each collision event
- `-5` for every package still unfinished at the end

The current fixed run is reproducible:

| Map Seed | Policy | Deliveries | Team Score | Collision Attempts | Steps |
| ---: | --- | ---: | ---: | ---: | ---: |
| 42 | Baseline | 3 | -102 | 3 | 60 |
| 42 | Coordinated | 4 | -67 | 0 | 54 |
| 101 | Baseline | 3 | -102 | 3 | 60 |
| 101 | Coordinated | 4 | -61 | 0 | 52 |
| 2023 | Baseline | 3 | -120 | 9 | 60 |
| 2023 | Coordinated | 4 | -49 | 0 | 46 |

The score stays negative because movement costs are larger than the delivery
reward on an 8 x 8 map. The useful comparison is that coordination completes
all four deliveries sooner and avoids repeated conflicts.

### What the tests cover

`python simulator.py --run-tests` checks the local percept boundary,
same-square collisions, swap collisions, one-time pickup and delivery,
next-turn message delivery, baseline silence, all three coordination messages,
the tie-break rule, the fixed map shape, and full coordinated runs on all three
maps.

### Pull request and commit wording

If the work needs to be split into separate pull requests, these titles keep
the history simple and match the wording used in this project:

| Pull request | Commit wording |
| --- | --- |
| Build the simulator and world rules | Add the local percept and shared world state; Resolve movement, collisions, and package updates; Delay messages until the next turn |
| Add the independent baseline | Add local exploration and package memory; Bring carried packages back to the base |
| Add coordination and package claims | Share package discoveries; Track claims in each agent; Settle matching claims with the distance and agent ID rule |
| Add the fixed maps, logs, and tests | Add the three repeatable maps; Print readable step logs and result tables; Cover the world rules and both policies |

These are plain descriptions on purpose, without category prefixes.
