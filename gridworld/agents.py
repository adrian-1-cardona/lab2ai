"""The basic agent and the template for the coordinated agent."""

from __future__ import annotations

from .models import Action, Direction, Interaction, Percept, Position, Terrain


class ExampleBaselineAgent:
    """A simple agent to use as the baseline.

    It remembers packages and the base after it sees them. It does not send
    messages, claim packages, or use a full map.
    """

    def __init__(self, exploration_order: tuple[Direction, ...] | None = None) -> None:
        self.exploration_order = exploration_order or (
            Direction.NORTH,
            Direction.EAST,
            Direction.SOUTH,
            Direction.WEST,
        )
        if not self.exploration_order or Direction.WAIT in self.exploration_order:
            raise ValueError("exploration_order must contain non-WAIT directions")
        self.reset("")

    def reset(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.known_packages: set[Position] = set()
        self.base_location: Position | None = None
        self._exploration_cursor = 0

    def act(self, percept: Percept) -> Action:
        """Choose an action using only the agent's local view."""

        self._update_memory(percept)

        if percept.carrying:
            if percept.self_position == self.base_location:
                return Action(interaction=Interaction.DROP)
            if self.base_location is not None:
                return Action(move=self._move_toward(percept, self.base_location))
            return Action(move=self._explore(percept))

        current_cell = percept.visible_cells[percept.self_position]
        if current_cell.package_present:
            return Action(interaction=Interaction.PICKUP)

        if self.known_packages:
            target = min(
                self.known_packages,
                key=lambda position: self._manhattan(percept.self_position, position),
            )
            if target != percept.self_position:
                move = self._move_toward(percept, target)
                if move is not Direction.WAIT:
                    return Action(move=move)

        return Action(move=self._explore(percept))

    def _update_memory(self, percept: Percept) -> None:
        for position, cell in percept.visible_cells.items():
            if cell.terrain is Terrain.BASE:
                self.base_location = position
            if cell.package_present:
                self.known_packages.add(position)
            elif position in self.known_packages:
                # Remove a package if another agent already picked it up.
                self.known_packages.remove(position)

    def _move_toward(self, percept: Percept, target: Position) -> Direction:
        row, column = percept.self_position
        target_row, target_column = target
        preferred: list[Direction] = []
        if target_row < row:
            preferred.append(Direction.NORTH)
        elif target_row > row:
            preferred.append(Direction.SOUTH)
        if target_column < column:
            preferred.append(Direction.WEST)
        elif target_column > column:
            preferred.append(Direction.EAST)

        for direction in (*preferred, *self.exploration_order):
            if self._can_enter(percept, direction):
                return direction
        return Direction.WAIT

    def _explore(self, percept: Percept) -> Direction:
        for offset in range(len(self.exploration_order)):
            index = (self._exploration_cursor + offset) % len(self.exploration_order)
            direction = self.exploration_order[index]
            if self._can_enter(percept, direction):
                self._exploration_cursor = (index + 1) % len(self.exploration_order)
                return direction
        return Direction.WAIT

    @staticmethod
    def _can_enter(percept: Percept, direction: Direction) -> bool:
        row_delta, column_delta = direction.delta
        destination = (
            percept.self_position[0] + row_delta,
            percept.self_position[1] + column_delta,
        )
        cell = percept.visible_cells.get(destination)
        if cell is None or cell.terrain is Terrain.OBSTACLE:
            return False
        return not cell.agent_ids

    @staticmethod
    def _manhattan(first: Position, second: Position) -> int:
        return abs(first[0] - second[0]) + abs(first[1] - second[1])


class CoordinatedAgentTemplate:
    """Starting point for the coordinated agent.

    It waits until the coordination rules below are added.
    """

    def reset(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.known_packages: set[Position] = set()
        self.claimed_by: dict[Position, str] = {}

    def act(self, percept: Percept) -> Action:
        # TODO: update memory using the cells the agent can see.
        # TODO: read the messages from the other agent.
        # TODO: pick a target without taking another agent's claim.
        # TODO: send DISCOVER, CLAIM, or RELEASE when needed.
        # TODO: return the move, interaction, and message.
        return Action()
