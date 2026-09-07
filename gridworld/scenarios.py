"""The starter map and agents used in the demo."""

from __future__ import annotations

from .agents import ExampleBaselineAgent
from .environment import GridWorld
from .models import Direction


def starter_world() -> GridWorld:
    """Create the 8 x 8 starter world."""

    return GridWorld(
        width=8,
        height=8,
        base=(0, 0),
        # This wall has one gap, so both agents have to share it.
        obstacles={
            (0, 3),
            (1, 3),
            (2, 3),
            (3, 3),
            (4, 3),
            (5, 3),
            (6, 3),
            (5, 5),
        },
        packages={(1, 1), (0, 6), (5, 6), (7, 6)},
        agent_positions={"robot-1": (0, 1), "robot-2": (2, 0)},
        horizon=60,
    )


def starter_agents() -> dict[str, ExampleBaselineAgent]:
    """Create the two basic agents."""

    return {
        "robot-1": ExampleBaselineAgent(
            (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
        ),
        "robot-2": ExampleBaselineAgent(
            (Direction.WEST, Direction.SOUTH, Direction.EAST, Direction.NORTH)
        ),
    }
