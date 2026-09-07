"""Shared data types for the gridworld.

Coordinates use (row, column). Row 0 is north and column 0 is west.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


Position = tuple[int, int]


class Terrain(Enum):
    EMPTY = "empty"
    OBSTACLE = "obstacle"
    BASE = "base"


class Direction(Enum):
    NORTH = (-1, 0)
    SOUTH = (1, 0)
    EAST = (0, 1)
    WEST = (0, -1)
    WAIT = (0, 0)

    @property
    def delta(self) -> Position:
        return self.value


class Interaction(Enum):
    NONE = "none"
    PICKUP = "pickup"
    DROP = "drop"


class MovementResult(Enum):
    WAITED = "waited"
    MOVED = "moved"
    INVALID_MOVE = "invalid_move"
    BLOCKED_COLLISION = "blocked_collision"


class InteractionResult(Enum):
    NOT_ATTEMPTED = "not_attempted"
    PICKED_UP = "picked_up"
    DROPPED = "dropped"
    INVALID_INTERACTION = "invalid_interaction"


class MessageKind(Enum):
    DISCOVER = "discover"
    CLAIM = "claim"
    RELEASE = "release"


@dataclass(frozen=True)
class Message:
    """A message that the other agents get on the next turn.

    The environment fills in the sender ID. The package location is optional.
    """

    kind: MessageKind
    package_location: Position | None = None
    sender: str | None = None


@dataclass(frozen=True)
class Action:
    """The move, interaction, and message an agent chooses."""

    move: Direction = Direction.WAIT
    interaction: Interaction = Interaction.NONE
    message: Message | None = None


@dataclass(frozen=True)
class CellView:
    terrain: Terrain
    package_present: bool
    agent_ids: tuple[str, ...]


@dataclass(frozen=True)
class ActionResult:
    movement: MovementResult
    interaction: InteractionResult


@dataclass(frozen=True)
class Percept:
    """The information an agent gets before choosing an action.

    visible_cells only has the in-bounds cells in its local 3 x 3 view.
    """

    time: int
    self_position: Position
    visible_cells: dict[Position, CellView]
    carrying: bool
    last_result: ActionResult
    messages: tuple[Message, ...]


@dataclass
class AgentState:
    position: Position
    carried_package: Position | None = None
    inbox: list[Message] = field(default_factory=list)
    last_result: ActionResult = field(
        default_factory=lambda: ActionResult(
            MovementResult.WAITED, InteractionResult.NOT_ATTEMPTED
        )
    )


@dataclass(frozen=True)
class Event:
    """One log entry for an agent's action."""

    time: int
    agent_id: str
    percept_summary: str
    received_messages: tuple[Message, ...]
    sent_message: Message | None
    action: Action
    result: ActionResult
    final_position: Position


@dataclass(frozen=True)
class EpisodeResult:
    score: int
    delivered_count: int
    collision_attempts: int
    steps: int
    events: tuple[Event, ...]
