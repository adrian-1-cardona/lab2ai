"""Cooperative multi-agent gridworld for CSC 4800 Lab 2.

The environment owns the world. Agents only receive a local percept and keep
their own memory between turns.
"""

from __future__ import annotations

import argparse
import heapq
import re
import unittest
from abc import ABC, abstractmethod
from collections import Counter, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from itertools import count
from typing import Iterable, Mapping, Sequence


Position = tuple[int, int]
GRID_SIZE = 8
BASE: Position = (0, 0)
HORIZON = 60
AGENT_STARTS = {"Agent_1": (0, 7), "Agent_2": (7, 0)}


class Terrain(Enum):
    EMPTY = "empty"
    OBSTACLE = "obstacle"
    BASE = "base"
    OUT_OF_BOUNDS = "out_of_bounds"


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
    DELIVERED = "delivered"
    INVALID_INTERACTION = "invalid_interaction"


class MessageKind(Enum):
    DISCOVER = "DISCOVER"
    CLAIM = "CLAIM"
    RELEASE = "RELEASE"


@dataclass(frozen=True)
class Message:
    kind: MessageKind
    package_id: str
    package_location: Position | None = None
    agent_id: str | None = None
    distance: int | None = None
    sender: str | None = None


@dataclass(frozen=True)
class Action:
    move: Direction = Direction.WAIT
    interaction: Interaction = Interaction.NONE
    message: Message | None = None


@dataclass(frozen=True)
class CellView:
    terrain: Terrain
    package_id: str | None = None
    agent_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Percept:
    carried_item_id: str | None
    last_action_status: bool
    clock: int
    local_grid: tuple[tuple[CellView, ...], ...]
    inbox: tuple[Message, ...]


@dataclass(frozen=True)
class ActionResult:
    movement: MovementResult
    interaction: InteractionResult

    @property
    def succeeded(self) -> bool:
        return (
            self.movement
            not in {
                MovementResult.INVALID_MOVE,
                MovementResult.BLOCKED_COLLISION,
            }
            and self.interaction is not InteractionResult.INVALID_INTERACTION
        )


@dataclass
class PackageState:
    package_id: str
    position: Position | None
    carried_by: str | None = None
    delivered: bool = False


@dataclass
class AgentState:
    position: Position
    carried_item_id: str | None = None
    last_result: ActionResult = field(
        default_factory=lambda: ActionResult(
            MovementResult.WAITED, InteractionResult.NOT_ATTEMPTED
        )
    )


@dataclass(frozen=True)
class Event:
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


@dataclass(frozen=True)
class Scenario:
    seed: int
    obstacles: frozenset[Position]
    packages: tuple[Position, ...]


SCENARIOS: dict[int, Scenario] = {
    42: Scenario(
        seed=42,
        obstacles=frozenset({(2, 2), (2, 3), (2, 4), (4, 2), (4, 4)}),
        packages=((1, 5), (3, 3), (5, 6), (6, 1)),
    ),
    101: Scenario(
        seed=101,
        obstacles=frozenset({(2, 3), (3, 3), (4, 3), (2, 5), (4, 5)}),
        packages=((1, 1), (3, 4), (5, 5), (6, 2)),
    ),
    2023: Scenario(
        seed=2023,
        obstacles=frozenset({(3, 2), (3, 3), (3, 4), (5, 2), (5, 4)}),
        packages=((1, 6), (4, 3), (6, 1), (4, 6)),
    ),
}


class GridWorld:
    """Owns the shared state and resolves every joint action."""

    def __init__(
        self,
        *,
        width: int,
        height: int,
        base: Position,
        obstacles: Iterable[Position],
        packages: Mapping[str, Position] | Iterable[Position],
        agent_positions: Mapping[str, Position],
        horizon: int = HORIZON,
    ) -> None:
        self.width = width
        self.height = height
        self.base = base
        self.obstacles = set(obstacles)
        self.initial_packages = self._name_packages(packages)
        self.initial_agent_positions = dict(agent_positions)
        self.horizon = horizon
        self._validate_world()
        self.reset()

    @staticmethod
    def _name_packages(
        packages: Mapping[str, Position] | Iterable[Position],
    ) -> dict[str, Position]:
        if isinstance(packages, Mapping):
            return dict(packages)
        return {
            f"P{index}": position
            for index, position in enumerate(sorted(packages), start=1)
        }

    @property
    def agent_ids(self) -> tuple[str, ...]:
        return tuple(self.states)

    @property
    def remaining_packages(self) -> set[Position]:
        return {
            package.position
            for package in self.packages.values()
            if not package.delivered
            and package.carried_by is None
            and package.position is not None
        }

    @property
    def delivered_packages(self) -> list[str]:
        return [
            package.package_id
            for package in self.packages.values()
            if package.delivered
        ]

    def reset(self) -> None:
        self.states = {
            agent_id: AgentState(position)
            for agent_id, position in self.initial_agent_positions.items()
        }
        self.packages = {
            package_id: PackageState(package_id, position)
            for package_id, position in self.initial_packages.items()
        }
        self.score = 0
        self.collision_attempts = 0
        self.time = 0
        self.events: list[Event] = []
        self._active_inboxes = {agent_id: [] for agent_id in self.states}
        self._staging_queue = {agent_id: [] for agent_id in self.states}
        self._finalized = False

    def observe(self, agent_id: str) -> Percept:
        state = self._require_agent(agent_id)
        package_at = {
            package.position: package.package_id
            for package in self.packages.values()
            if not package.delivered and package.carried_by is None
        }
        occupants = self._occupants_by_position()
        rows: list[tuple[CellView, ...]] = []

        for row_offset in (-1, 0, 1):
            row: list[CellView] = []
            for column_offset in (-1, 0, 1):
                position = (
                    state.position[0] + row_offset,
                    state.position[1] + column_offset,
                )
                if not self._in_bounds(position):
                    row.append(CellView(Terrain.OUT_OF_BOUNDS))
                    continue
                row.append(
                    CellView(
                        terrain=self._terrain_at(position),
                        package_id=package_at.get(position),
                        agent_ids=tuple(sorted(occupants.get(position, ()))),
                    )
                )
            rows.append(tuple(row))

        return Percept(
            carried_item_id=state.carried_item_id,
            last_action_status=state.last_result.succeeded,
            clock=self.time,
            local_grid=tuple(rows),
            inbox=tuple(self._active_inboxes[agent_id]),
        )

    def step(
        self,
        actions: Mapping[str, Action],
        percept_summaries: Mapping[str, str] | None = None,
    ) -> tuple[Event, ...]:
        if self._finalized:
            raise RuntimeError("reset the world before running another step")

        unknown_agents = set(actions) - set(self.states)
        if unknown_agents:
            raise KeyError(f"unknown agent IDs: {sorted(unknown_agents)}")

        percept_summaries = percept_summaries or {}
        resolved = {
            agent_id: actions.get(agent_id, Action()) for agent_id in self.agent_ids
        }
        before = {agent_id: state.position for agent_id, state in self.states.items()}
        received = {
            agent_id: tuple(messages)
            for agent_id, messages in self._active_inboxes.items()
        }

        intended = dict(before)
        movement_results: dict[str, MovementResult] = {}
        valid_movers: set[str] = set()

        for agent_id, action in resolved.items():
            if action.move is Direction.WAIT:
                movement_results[agent_id] = MovementResult.WAITED
                continue

            self.score -= 1
            destination = self._translate(before[agent_id], action.move)
            if not self._in_bounds(destination) or destination in self.obstacles:
                self.score -= 2
                movement_results[agent_id] = MovementResult.INVALID_MOVE
                continue

            intended[agent_id] = destination
            movement_results[agent_id] = MovementResult.MOVED
            valid_movers.add(agent_id)

        blocked, collision_pairs = self._find_collision_blocks(
            before, intended, valid_movers
        )
        self.collision_attempts += len(collision_pairs)
        self.score -= 3 * len(collision_pairs)

        for agent_id in blocked:
            movement_results[agent_id] = MovementResult.BLOCKED_COLLISION
        for agent_id in valid_movers - blocked:
            self.states[agent_id].position = intended[agent_id]

        interaction_results: dict[str, InteractionResult] = {}
        for agent_id, action in resolved.items():
            if action.interaction is not Interaction.NONE and movement_results[
                agent_id
            ] in {
                MovementResult.INVALID_MOVE,
                MovementResult.BLOCKED_COLLISION,
            }:
                interaction_results[agent_id] = InteractionResult.NOT_ATTEMPTED
            else:
                interaction_results[agent_id] = self._resolve_interaction(
                    agent_id, action.interaction
                )

        self._staging_queue = {agent_id: [] for agent_id in self.states}
        sent_messages: dict[str, Message | None] = {}
        for agent_id, action in resolved.items():
            sent = self._stamp_message(agent_id, action.message)
            sent_messages[agent_id] = sent
            if sent is None:
                continue
            for recipient_id in self.agent_ids:
                if recipient_id != agent_id:
                    self._staging_queue[recipient_id].append(sent)

        step_events: list[Event] = []
        for agent_id, state in self.states.items():
            result = ActionResult(
                movement_results[agent_id], interaction_results[agent_id]
            )
            state.last_result = result
            step_events.append(
                Event(
                    time=self.time,
                    agent_id=agent_id,
                    percept_summary=percept_summaries.get(agent_id, "not recorded"),
                    received_messages=received[agent_id],
                    sent_message=sent_messages[agent_id],
                    action=resolved[agent_id],
                    result=result,
                    final_position=state.position,
                )
            )

        self.events.extend(step_events)
        self.time += 1
        # Staged messages become active only after both agents have acted.
        self._active_inboxes = self._staging_queue
        return tuple(step_events)

    def is_complete(self) -> bool:
        return all(package.delivered for package in self.packages.values())

    def finish(self) -> EpisodeResult:
        if not self._finalized:
            unfinished = sum(
                not package.delivered for package in self.packages.values()
            )
            self.score -= 5 * unfinished
            self._finalized = True

        return EpisodeResult(
            score=self.score,
            delivered_count=len(self.delivered_packages),
            collision_attempts=self.collision_attempts,
            steps=self.time,
            events=tuple(self.events),
        )

    def _resolve_interaction(
        self, agent_id: str, interaction: Interaction
    ) -> InteractionResult:
        if interaction is Interaction.NONE:
            return InteractionResult.NOT_ATTEMPTED

        state = self.states[agent_id]
        if interaction is Interaction.PICKUP:
            package = next(
                (
                    item
                    for item in self.packages.values()
                    if item.position == state.position
                    and item.carried_by is None
                    and not item.delivered
                ),
                None,
            )
            if state.carried_item_id is None and package is not None:
                package.position = None
                package.carried_by = agent_id
                state.carried_item_id = package.package_id
                return InteractionResult.PICKED_UP
            self.score -= 2
            return InteractionResult.INVALID_INTERACTION

        if interaction is Interaction.DROP:
            if state.carried_item_id is None:
                self.score -= 2
                return InteractionResult.INVALID_INTERACTION

            package = self.packages[state.carried_item_id]
            if state.position == self.base:
                package.position = self.base
                package.carried_by = None
                package.delivered = True
                state.carried_item_id = None
                self.score += 10
                return InteractionResult.DELIVERED

            occupied_by_package = any(
                item.position == state.position
                and item.carried_by is None
                and not item.delivered
                for item in self.packages.values()
            )
            if not occupied_by_package:
                package.position = state.position
                package.carried_by = None
                state.carried_item_id = None
                return InteractionResult.DROPPED

            self.score -= 2
            return InteractionResult.INVALID_INTERACTION

        raise ValueError(f"unsupported interaction: {interaction}")

    def _find_collision_blocks(
        self,
        before: Mapping[str, Position],
        intended: Mapping[str, Position],
        valid_movers: set[str],
    ) -> tuple[set[str], set[tuple[str, str]]]:
        blocked: set[str] = set()
        collisions: set[tuple[str, str]] = set()
        movers = sorted(valid_movers)

        for index, first_id in enumerate(movers):
            for second_id in movers[index + 1 :]:
                same_destination = intended[first_id] == intended[second_id]
                swap = (
                    intended[first_id] == before[second_id]
                    and intended[second_id] == before[first_id]
                )
                if same_destination or swap:
                    blocked.update((first_id, second_id))
                    collisions.add((first_id, second_id))

        changed = True
        while changed:
            changed = False
            moving = valid_movers - blocked
            for mover_id in sorted(moving):
                for occupant_id, occupant_position in before.items():
                    if (
                        mover_id == occupant_id
                        or intended[mover_id] != occupant_position
                    ):
                        continue
                    if occupant_id not in moving:
                        blocked.add(mover_id)
                        collisions.add(tuple(sorted((mover_id, occupant_id))))
                        changed = True
                        break

        return blocked, collisions

    def _stamp_message(self, agent_id: str, message: Message | None) -> Message | None:
        if message is None:
            return None
        if not message.package_id:
            raise ValueError("messages need a package ID")
        if message.kind is MessageKind.DISCOVER and message.package_location is None:
            raise ValueError("DISCOVER messages need a package location")
        if message.kind is MessageKind.CLAIM and message.distance is None:
            raise ValueError("CLAIM messages need the claimant's distance")
        claimant = agent_id if message.kind is MessageKind.CLAIM else message.agent_id
        return replace(message, sender=agent_id, agent_id=claimant)

    def _terrain_at(self, position: Position) -> Terrain:
        if position == self.base:
            return Terrain.BASE
        if position in self.obstacles:
            return Terrain.OBSTACLE
        return Terrain.EMPTY

    def _occupants_by_position(self) -> dict[Position, list[str]]:
        occupants: dict[Position, list[str]] = {}
        for agent_id, state in self.states.items():
            occupants.setdefault(state.position, []).append(agent_id)
        return occupants

    def _translate(self, position: Position, direction: Direction) -> Position:
        return (
            position[0] + direction.delta[0],
            position[1] + direction.delta[1],
        )

    def _in_bounds(self, position: Position) -> bool:
        return 0 <= position[0] < self.height and 0 <= position[1] < self.width

    def _require_agent(self, agent_id: str) -> AgentState:
        try:
            return self.states[agent_id]
        except KeyError as error:
            raise KeyError(f"unknown agent: {agent_id}") from error

    def _validate_world(self) -> None:
        if self.width <= 0 or self.height <= 0 or self.horizon <= 0:
            raise ValueError("width, height, and horizon must be positive")
        if len(self.initial_agent_positions) < 2:
            raise ValueError("the simulation needs at least two agents")

        groups = {
            "base": {self.base},
            "obstacles": self.obstacles,
            "packages": set(self.initial_packages.values()),
            "agents": set(self.initial_agent_positions.values()),
        }
        for label, positions in groups.items():
            for position in positions:
                if not self._in_bounds(position):
                    raise ValueError(f"{label} has an out-of-bounds cell: {position}")

        if len(set(self.initial_agent_positions.values())) != len(
            self.initial_agent_positions
        ):
            raise ValueError("agents must start in different cells")
        if len(set(self.initial_packages.values())) != len(self.initial_packages):
            raise ValueError("packages must start in different cells")
        if self.base in self.obstacles:
            raise ValueError("the base cannot be an obstacle")
        if set(self.initial_packages.values()) & self.obstacles:
            raise ValueError("a package cannot start in an obstacle")
        if set(self.initial_agent_positions.values()) & self.obstacles:
            raise ValueError("an agent cannot start in an obstacle")


class Agent(ABC):
    @abstractmethod
    def reset(self, agent_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def act(self, percept: Percept) -> Action:
        raise NotImplementedError


class LocalAgent(Agent):
    """Shared local memory and navigation used by both policies."""

    def __init__(
        self,
        start: Position = (0, 0),
        *,
        width: int = GRID_SIZE,
        height: int = GRID_SIZE,
        exploration_order: Sequence[Direction] | None = None,
    ) -> None:
        self.start = start
        self.width = width
        self.height = height
        self.exploration_order = tuple(
            exploration_order
            or (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
        )
        if not self.exploration_order or Direction.WAIT in self.exploration_order:
            raise ValueError("exploration directions cannot include WAIT")
        self.reset("")

    def reset(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.position = self.start
        self.known_terrain: dict[Position, Terrain] = {BASE: Terrain.BASE}
        self.known_packages: dict[str, Position] = {}
        self.visit_count: Counter[Position] = Counter()
        self.carried_item_id: str | None = None
        self._previous_action = Action()
        self._visible_agents: dict[str, Position] = {}
        self._previous_carried_item: str | None = None
        self._failed_destination: Position | None = None

    def act(self, percept: Percept) -> Action:
        self._update_position(percept.last_action_status)
        self._previous_carried_item = self.carried_item_id
        self.carried_item_id = percept.carried_item_id
        visible_packages, missing_packages = self._read_local_grid(percept.local_grid)
        self.visit_count[self.position] += 1
        self._after_observation(percept, visible_packages, missing_packages)
        action = self._decide(percept)
        self._previous_action = action
        return action

    @abstractmethod
    def _decide(self, percept: Percept) -> Action:
        raise NotImplementedError

    def _after_observation(
        self,
        percept: Percept,
        visible_packages: Mapping[str, Position],
        missing_packages: set[str],
    ) -> None:
        return None

    def _update_position(self, previous_action_succeeded: bool) -> None:
        if (
            previous_action_succeeded
            and self._previous_action.move is not Direction.WAIT
        ):
            self.position = self._translate(self.position, self._previous_action.move)
            self._failed_destination = None
        elif self._previous_action.move is not Direction.WAIT:
            self._failed_destination = self._translate(
                self.position, self._previous_action.move
            )
        else:
            self._failed_destination = None

    def _read_local_grid(
        self, local_grid: tuple[tuple[CellView, ...], ...]
    ) -> tuple[dict[str, Position], set[str]]:
        visible_packages: dict[str, Position] = {}
        seen_positions: set[Position] = set()
        self._visible_agents = {}

        for row_index, row in enumerate(local_grid):
            for column_index, cell in enumerate(row):
                position = (
                    self.position[0] + row_index - 1,
                    self.position[1] + column_index - 1,
                )
                if cell.terrain is Terrain.OUT_OF_BOUNDS:
                    continue
                seen_positions.add(position)
                self.known_terrain[position] = cell.terrain
                if cell.package_id is not None:
                    visible_packages[cell.package_id] = position
                    self.known_packages[cell.package_id] = position
                for agent_id in cell.agent_ids:
                    if agent_id != self.agent_id:
                        self._visible_agents[agent_id] = position

        missing: set[str] = set()
        for package_id, position in tuple(self.known_packages.items()):
            if (
                position in seen_positions
                and package_id not in visible_packages
                and package_id != self.carried_item_id
            ):
                missing.add(package_id)
                del self.known_packages[package_id]
        return visible_packages, missing

    def _move_toward(self, target: Position) -> Direction:
        if target == self.position:
            return Direction.WAIT

        frontier: list[tuple[int, int, int, Position]] = []
        order = count()
        heapq.heappush(
            frontier,
            (self._manhattan(self.position, target), 0, next(order), self.position),
        )
        came_from: dict[Position, tuple[Position, Direction]] = {}
        best_cost = {self.position: 0}

        while frontier:
            _, cost, _, current = heapq.heappop(frontier)
            if current == target:
                break
            if cost != best_cost[current]:
                continue

            for direction in self.exploration_order:
                neighbor = self._translate(current, direction)
                if not self._can_plan_through(neighbor, target):
                    continue
                new_cost = cost + 1
                if new_cost >= best_cost.get(neighbor, self.width * self.height + 1):
                    continue
                best_cost[neighbor] = new_cost
                came_from[neighbor] = (current, direction)
                priority = new_cost + self._manhattan(neighbor, target)
                heapq.heappush(frontier, (priority, new_cost, next(order), neighbor))

        if target not in came_from:
            return Direction.WAIT
        current = target
        while came_from[current][0] != self.position:
            current = came_from[current][0]
        return came_from[current][1]

    def _explore(self) -> Direction:
        candidates = [
            (row, column)
            for row in range(self.height)
            for column in range(self.width)
            if self.known_terrain.get((row, column)) is not Terrain.OBSTACLE
        ]
        candidates.sort(
            key=lambda position: (
                self.visit_count[position],
                self._manhattan(self.position, position),
                position,
            )
        )
        move = Direction.WAIT
        for target in candidates:
            if target == self.position:
                continue
            move = self._move_toward(target)
            if move is not Direction.WAIT:
                break
        if (
            move is Direction.WAIT
            and self._failed_destination is not None
            and self.known_terrain.get(self._failed_destination) is not Terrain.OBSTACLE
            and _agent_rank(self.agent_id) == 1
        ):
            for direction in self.exploration_order:
                if (
                    self._translate(self.position, direction)
                    == self._failed_destination
                ):
                    return direction
        return move

    def _can_plan_through(self, position: Position, target: Position) -> bool:
        if not (0 <= position[0] < self.height and 0 <= position[1] < self.width):
            return False
        if self.known_terrain.get(position) is Terrain.OBSTACLE:
            return False
        if position == self._failed_destination:
            return False
        return position not in self._visible_agents.values()

    @staticmethod
    def _translate(position: Position, direction: Direction) -> Position:
        return (
            position[0] + direction.delta[0],
            position[1] + direction.delta[1],
        )

    @staticmethod
    def _manhattan(first: Position, second: Position) -> int:
        return abs(first[0] - second[0]) + abs(first[1] - second[1])


class BaselineAgent(LocalAgent):
    """Independent policy. It never reads or sends messages."""

    def _decide(self, percept: Percept) -> Action:
        if self.carried_item_id is not None:
            if self.position == BASE:
                return Action(interaction=Interaction.DROP)
            move = self._travel(BASE)
            interaction = (
                Interaction.DROP
                if self._translate(self.position, move) == BASE
                else Interaction.NONE
            )
            return Action(move=move, interaction=interaction)

        current_package = self._package_at(self.position)
        if current_package is not None:
            return Action(interaction=Interaction.PICKUP)

        if self.known_packages:
            target = min(
                self.known_packages.values(),
                key=lambda position: (
                    self._manhattan(self.position, position),
                    position,
                ),
            )
            move = self._travel(target)
            interaction = (
                Interaction.PICKUP
                if self._translate(self.position, move) == target
                else Interaction.NONE
            )
            return Action(move=move, interaction=interaction)
        return Action(move=self._explore())

    def _after_observation(
        self,
        percept: Percept,
        visible_packages: Mapping[str, Position],
        missing_packages: set[str],
    ) -> None:
        if (
            self._previous_carried_item is not None
            and self.carried_item_id is None
            and self.position == BASE
        ):
            self.known_packages.pop(self._previous_carried_item, None)

    def _package_at(self, position: Position) -> str | None:
        return next(
            (
                package_id
                for package_id, package_position in self.known_packages.items()
                if package_position == position
            ),
            None,
        )

    def _travel(self, target: Position) -> Direction:
        move = self._move_toward(target)
        if (
            move is Direction.WAIT
            and self._failed_destination is not None
            and _agent_rank(self.agent_id) == 1
        ):
            for direction in self.exploration_order:
                if (
                    self._translate(self.position, direction)
                    == self._failed_destination
                ):
                    return direction
        return move


@dataclass(frozen=True)
class Claim:
    agent_id: str
    distance: int


class CoordinatedAgent(BaselineAgent):
    """Shares discoveries and uses one deterministic claim rule."""

    def reset(self, agent_id: str) -> None:
        super().reset(agent_id)
        self.claims: dict[str, Claim] = {}
        self.target_package_id: str | None = None
        self._announced: set[str] = set()
        self._outbox: deque[Message] = deque()

    def _after_observation(
        self,
        percept: Percept,
        visible_packages: Mapping[str, Position],
        missing_packages: set[str],
    ) -> None:
        self._read_messages(percept.inbox)

        for package_id, position in sorted(visible_packages.items()):
            if package_id not in self._announced:
                self._outbox.append(Message(MessageKind.DISCOVER, package_id, position))
                self._announced.add(package_id)

        for package_id in missing_packages:
            if package_id == self.target_package_id:
                self._release_target(package_id)
            elif self.claims.get(package_id, Claim("", 0)).agent_id == self.agent_id:
                self._queue_release(package_id)
            self.claims.pop(package_id, None)

        if (
            self._previous_carried_item is not None
            and self.carried_item_id is None
            and self.position == BASE
        ):
            finished_id = self._previous_carried_item
            self.known_packages.pop(finished_id, None)
            self.claims.pop(finished_id, None)
            self._queue_release(finished_id)
            if self.target_package_id == finished_id:
                self.target_package_id = None

    def _decide(self, percept: Percept) -> Action:
        if self.carried_item_id is not None:
            if self.position == BASE:
                return self._send_with(Action(interaction=Interaction.DROP))
            move = self._coordinated_move(BASE)
            interaction = (
                Interaction.DROP
                if self._translate(self.position, move) == BASE
                else Interaction.NONE
            )
            return self._send_with(Action(move=move, interaction=interaction))

        self._check_target()
        if self.target_package_id is None:
            self._choose_target()

        if self.target_package_id is not None:
            target = self.known_packages[self.target_package_id]
            if target == self.position:
                return self._send_with(Action(interaction=Interaction.PICKUP))
            move = self._coordinated_move(target)
            interaction = (
                Interaction.PICKUP
                if self._translate(self.position, move) == target
                else Interaction.NONE
            )
            return self._send_with(Action(move=move, interaction=interaction))

        return self._send_with(Action(move=self._coordinated_explore()))

    def _read_messages(self, messages: Iterable[Message]) -> None:
        for message in messages:
            if message.kind is MessageKind.DISCOVER:
                if message.package_location is not None:
                    self.known_packages.setdefault(
                        message.package_id, message.package_location
                    )
                continue

            if message.kind is MessageKind.RELEASE:
                claim = self.claims.get(message.package_id)
                if claim is not None and claim.agent_id == message.sender:
                    self.claims.pop(message.package_id, None)
                    self.known_packages.pop(message.package_id, None)
                continue

            claimant = message.agent_id or message.sender
            if claimant is None or message.distance is None:
                continue
            incoming = Claim(claimant, message.distance)
            current = self.claims.get(message.package_id)
            if current is None or self._claim_key(incoming) < self._claim_key(current):
                self.claims[message.package_id] = incoming
                if (
                    self.target_package_id == message.package_id
                    and incoming.agent_id != self.agent_id
                ):
                    self._queue_release(message.package_id)
                    self.target_package_id = None

    def _check_target(self) -> None:
        package_id = self.target_package_id
        if package_id is None:
            return
        if package_id not in self.known_packages:
            self._release_target(package_id)
            return
        claim = self.claims.get(package_id)
        if claim is not None and claim.agent_id != self.agent_id:
            self._queue_release(package_id)
            self.target_package_id = None

    def _choose_target(self) -> None:
        available = [
            (package_id, position)
            for package_id, position in self.known_packages.items()
            if self.claims.get(package_id, Claim(self.agent_id, 0)).agent_id
            == self.agent_id
        ]
        if not available:
            return
        package_id, position = min(
            available,
            key=lambda item: (
                self._manhattan(self.position, item[1]),
                item[0],
            ),
        )
        distance = self._manhattan(self.position, position)
        self.target_package_id = package_id
        self.claims[package_id] = Claim(self.agent_id, distance)
        self._outbox.append(
            Message(
                MessageKind.CLAIM,
                package_id,
                package_location=position,
                agent_id=self.agent_id,
                distance=distance,
            )
        )

    def _release_target(self, package_id: str) -> None:
        if self.claims.get(package_id, Claim("", 0)).agent_id == self.agent_id:
            self._queue_release(package_id)
        self.claims.pop(package_id, None)
        if self.target_package_id == package_id:
            self.target_package_id = None

    def _queue_release(self, package_id: str) -> None:
        if not any(
            message.kind is MessageKind.RELEASE and message.package_id == package_id
            for message in self._outbox
        ):
            self._outbox.append(Message(MessageKind.RELEASE, package_id))

    def _send_with(self, action: Action) -> Action:
        if not self._outbox:
            return action
        return replace(action, message=self._outbox.popleft())

    def _coordinated_move(self, target: Position) -> Direction:
        move = self._travel(target)
        if move is Direction.WAIT:
            return move
        destination = self._translate(self.position, move)
        for other_id, other_position in self._visible_agents.items():
            if destination == other_position:
                return Direction.WAIT
            could_choose_same_cell = self._manhattan(destination, other_position) == 1
            if could_choose_same_cell and _agent_rank(self.agent_id) > _agent_rank(
                other_id
            ):
                return Direction.WAIT
        return move

    def _coordinated_explore(self) -> Direction:
        move = self._explore()
        if move is Direction.WAIT or self.position == BASE:
            return move
        destination = self._translate(self.position, move)
        for other_id, other_position in self._visible_agents.items():
            if destination == other_position:
                return Direction.WAIT
            if self._manhattan(destination, other_position) == 1 and _agent_rank(
                self.agent_id
            ) > _agent_rank(other_id):
                return Direction.WAIT
        return move

    @staticmethod
    def _claim_key(claim: Claim) -> tuple[int, tuple[int, str]]:
        return claim.distance, (_agent_rank(claim.agent_id), claim.agent_id)


def _agent_rank(agent_id: str) -> int:
    match = re.search(r"(\d+)$", agent_id)
    return int(match.group(1)) if match else 10**9


# These names keep the starter imports working.
ExampleBaselineAgent = BaselineAgent
CoordinatedAgentTemplate = CoordinatedAgent


def scenario_world(seed: int) -> GridWorld:
    try:
        scenario = SCENARIOS[seed]
    except KeyError as error:
        raise ValueError(f"seed must be one of {sorted(SCENARIOS)}") from error
    packages = {
        f"P{index}": position
        for index, position in enumerate(scenario.packages, start=1)
    }
    return GridWorld(
        width=GRID_SIZE,
        height=GRID_SIZE,
        base=BASE,
        obstacles=scenario.obstacles,
        packages=packages,
        agent_positions=AGENT_STARTS,
        horizon=HORIZON,
    )


def make_agents(policy: str) -> dict[str, Agent]:
    orders = {
        "Agent_1": (
            Direction.WEST,
            Direction.SOUTH,
            Direction.NORTH,
            Direction.EAST,
        ),
        "Agent_2": (
            Direction.NORTH,
            Direction.EAST,
            Direction.WEST,
            Direction.SOUTH,
        ),
    }
    agent_type = BaselineAgent if policy == "baseline" else CoordinatedAgent
    return {
        agent_id: agent_type(start, exploration_order=orders[agent_id])
        for agent_id, start in AGENT_STARTS.items()
    }


def summarize_percept(percept: Percept) -> str:
    visible = sorted(
        cell.package_id
        for row in percept.local_grid
        for cell in row
        if cell.package_id is not None
    )
    return (
        f"clock={percept.clock}, carrying={percept.carried_item_id or '-'}, "
        f"packages={visible or '-'}"
    )


def run_episode(env: GridWorld, agents: Mapping[str, Agent]) -> EpisodeResult:
    if set(agents) != set(env.agent_ids):
        raise ValueError("agents must match the environment IDs")

    env.reset()
    for agent_id, agent in agents.items():
        agent.reset(agent_id)

    while env.time < env.horizon and not env.is_complete():
        percepts = {agent_id: env.observe(agent_id) for agent_id in env.agent_ids}
        actions = {
            agent_id: agents[agent_id].act(percepts[agent_id])
            for agent_id in env.agent_ids
        }
        summaries = {
            agent_id: summarize_percept(percept)
            for agent_id, percept in percepts.items()
        }
        env.step(actions, summaries)
    return env.finish()


def message_label(message: Message | None) -> str:
    if message is None:
        return "-"
    return f"{message.kind.value}({message.package_id})"


def format_event(event: Event) -> str:
    received = ",".join(message_label(message) for message in event.received_messages)
    received = received or "-"
    action = f"{event.action.move.name}/{event.action.interaction.name}"
    result = f"{event.result.movement.value}/{event.result.interaction.value}"
    communication = f"received={received}, sent={message_label(event.sent_message)}"
    return (
        f"[{event.time:02d} | {event.agent_id} | {event.percept_summary} | "
        f"{communication} | {action} | {result}, pos={event.final_position}]"
    )


def run_policy(policy: str, seed: int, *, trace: bool = True) -> EpisodeResult:
    result = run_episode(scenario_world(seed), make_agents(policy))
    if trace:
        for event in result.events:
            print(format_event(event))
    print(
        f"\n{policy.title()} on seed {seed}: "
        f"{result.delivered_count} deliveries, score {result.score}, "
        f"{result.collision_attempts} collisions, {result.steps} steps"
    )
    return result


def print_experiment_table() -> None:
    print(
        "| Map Seed | Policy | Deliveries | Team Score | Collision Attempts | Steps |"
    )
    print("| ---: | --- | ---: | ---: | ---: | ---: |")
    for seed in SCENARIOS:
        for policy in ("baseline", "coordinated"):
            result = run_episode(scenario_world(seed), make_agents(policy))
            print(
                f"| {seed} | {policy.title()} | {result.delivered_count} | "
                f"{result.score} | {result.collision_attempts} | {result.steps} |"
            )


class SimulatorTests(unittest.TestCase):
    def make_world(
        self,
        *,
        packages: Mapping[str, Position] | None = None,
        positions: Mapping[str, Position] | None = None,
    ) -> GridWorld:
        return GridWorld(
            width=3,
            height=3,
            base=(0, 0),
            obstacles=set(),
            packages=packages or {},
            agent_positions=positions or {"Agent_1": (1, 0), "Agent_2": (1, 2)},
            horizon=10,
        )

    def test_percept_is_an_exact_local_window(self) -> None:
        world = self.make_world(packages={"P1": (2, 2)})
        percept = world.observe("Agent_1")
        self.assertEqual(len(percept.local_grid), 3)
        self.assertTrue(all(len(row) == 3 for row in percept.local_grid))
        self.assertNotIn(
            "P1",
            {cell.package_id for row in percept.local_grid for cell in row},
        )

    def test_same_destination_blocks_both_agents(self) -> None:
        world = self.make_world()
        world.step(
            {
                "Agent_1": Action(move=Direction.EAST),
                "Agent_2": Action(move=Direction.WEST),
            }
        )
        self.assertEqual(world.states["Agent_1"].position, (1, 0))
        self.assertEqual(world.states["Agent_2"].position, (1, 2))
        self.assertEqual(world.collision_attempts, 1)
        self.assertEqual(world.score, -5)

    def test_swap_blocks_both_agents(self) -> None:
        world = self.make_world(positions={"Agent_1": (1, 0), "Agent_2": (1, 1)})
        world.step(
            {
                "Agent_1": Action(move=Direction.EAST),
                "Agent_2": Action(move=Direction.WEST),
            }
        )
        self.assertEqual(world.states["Agent_1"].position, (1, 0))
        self.assertEqual(world.states["Agent_2"].position, (1, 1))
        self.assertEqual(world.collision_attempts, 1)

    def test_pickup_and_delivery_happen_once(self) -> None:
        world = self.make_world(
            packages={"P1": (1, 0)},
            positions={"Agent_1": (1, 0), "Agent_2": (2, 2)},
        )
        world.step(
            {"Agent_1": Action(interaction=Interaction.PICKUP), "Agent_2": Action()}
        )
        world.step({"Agent_1": Action(move=Direction.NORTH), "Agent_2": Action()})
        world.step(
            {"Agent_1": Action(interaction=Interaction.DROP), "Agent_2": Action()}
        )
        world.step(
            {"Agent_1": Action(interaction=Interaction.DROP), "Agent_2": Action()}
        )
        self.assertEqual(world.delivered_packages, ["P1"])
        self.assertEqual(world.finish().delivered_count, 1)

    def test_package_can_be_dropped_on_an_empty_cell(self) -> None:
        world = self.make_world(
            packages={"P1": (1, 0)},
            positions={"Agent_1": (1, 0), "Agent_2": (2, 2)},
        )
        world.step(
            {"Agent_1": Action(interaction=Interaction.PICKUP), "Agent_2": Action()}
        )
        world.step({"Agent_1": Action(move=Direction.EAST), "Agent_2": Action()})
        world.step(
            {"Agent_1": Action(interaction=Interaction.DROP), "Agent_2": Action()}
        )
        self.assertEqual(world.packages["P1"].position, (1, 1))
        self.assertFalse(world.packages["P1"].delivered)

    def test_blocked_move_does_not_apply_its_interaction(self) -> None:
        world = self.make_world(packages={"P1": (1, 0)})
        world.step(
            {"Agent_1": Action(interaction=Interaction.PICKUP), "Agent_2": Action()}
        )
        world.step(
            {
                "Agent_1": Action(move=Direction.EAST, interaction=Interaction.DROP),
                "Agent_2": Action(move=Direction.WEST),
            }
        )
        self.assertEqual(world.states["Agent_1"].carried_item_id, "P1")
        self.assertIsNone(world.packages["P1"].position)
        self.assertEqual(
            world.states["Agent_1"].last_result.interaction,
            InteractionResult.NOT_ATTEMPTED,
        )

    def test_invalid_move_uses_both_move_penalties(self) -> None:
        world = self.make_world(positions={"Agent_1": (0, 0), "Agent_2": (2, 2)})
        world.step({"Agent_1": Action(move=Direction.NORTH), "Agent_2": Action()})
        self.assertEqual(world.score, -3)
        self.assertEqual(
            world.states["Agent_1"].last_result.movement,
            MovementResult.INVALID_MOVE,
        )

    def test_a_message_arrives_on_the_next_turn_only(self) -> None:
        world = self.make_world()
        self.assertEqual(world.observe("Agent_2").inbox, ())
        world.step(
            {
                "Agent_1": Action(
                    message=Message(MessageKind.DISCOVER, "P1", package_location=(2, 2))
                ),
                "Agent_2": Action(),
            }
        )
        inbox = world.observe("Agent_2").inbox
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0].sender, "Agent_1")
        world.step({"Agent_1": Action(), "Agent_2": Action()})
        self.assertEqual(world.observe("Agent_2").inbox, ())

    def test_baseline_never_sends_messages(self) -> None:
        result = run_episode(scenario_world(42), make_agents("baseline"))
        self.assertTrue(all(event.sent_message is None for event in result.events))

    def test_coordinated_agents_use_all_three_message_types(self) -> None:
        kinds: set[MessageKind] = set()
        for seed in SCENARIOS:
            result = run_episode(scenario_world(seed), make_agents("coordinated"))
            kinds.update(
                event.sent_message.kind
                for event in result.events
                if event.sent_message is not None
            )
        self.assertEqual(kinds, set(MessageKind))

    def test_claim_tie_goes_to_agent_one(self) -> None:
        claim_one = Claim("Agent_1", 3)
        claim_two = Claim("Agent_2", 3)
        self.assertLess(
            CoordinatedAgent._claim_key(claim_one),
            CoordinatedAgent._claim_key(claim_two),
        )

    def test_fixed_scenarios_match_the_lab_shape(self) -> None:
        self.assertEqual(set(SCENARIOS), {42, 101, 2023})
        for seed in SCENARIOS:
            world = scenario_world(seed)
            self.assertEqual((world.width, world.height), (8, 8))
            self.assertEqual(len(world.obstacles), 5)
            self.assertEqual(len(world.packages), 4)
            self.assertEqual(world.initial_agent_positions, AGENT_STARTS)

    def test_coordinated_policy_finishes_each_fixed_map(self) -> None:
        for seed in SCENARIOS:
            result = run_episode(scenario_world(seed), make_agents("coordinated"))
            self.assertEqual(result.delivered_count, 4)
            self.assertLess(result.steps, HORIZON)


def run_tests() -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SimulatorTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-baseline", action="store_true")
    mode.add_argument("--run-coordinated", action="store_true")
    mode.add_argument("--run-experiments", action="store_true")
    mode.add_argument("--run-tests", action="store_true")
    parser.add_argument("--seed", type=int, choices=tuple(SCENARIOS), default=42)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="hide the step log for a single run",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.run_tests:
        return 0 if run_tests() else 1
    if args.run_experiments:
        print_experiment_table()
        return 0
    policy = "baseline" if args.run_baseline else "coordinated"
    run_policy(policy, args.seed, trace=not args.summary_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
