"""Tests for the gridworld rules."""

from __future__ import annotations

import unittest

from gridworld.agents import ExampleBaselineAgent
from gridworld.environment import GridWorld
from gridworld.models import (
    Action,
    Direction,
    Interaction,
    InteractionResult,
    Message,
    MessageKind,
    MovementResult,
)


class GridWorldContractTests(unittest.TestCase):
    def make_world(
        self,
        *,
        packages: set[tuple[int, int]] | None = None,
        agent_positions: dict[str, tuple[int, int]] | None = None,
    ) -> GridWorld:
        return GridWorld(
            width=3,
            height=3,
            base=(0, 0),
            obstacles=set(),
            packages=packages or set(),
            agent_positions=agent_positions or {"alpha": (1, 0), "beta": (1, 2)},
            horizon=10,
        )

    def test_local_percept_contains_no_more_than_a_three_by_three_window(self) -> None:
        world = self.make_world(packages={(2, 2)})

        percept = world.observe("alpha")

        self.assertLessEqual(len(percept.visible_cells), 9)
        self.assertNotIn((2, 2), percept.visible_cells)

    def test_same_destination_blocks_both_agents(self) -> None:
        world = self.make_world()

        world.step(
            {
                "alpha": Action(move=Direction.EAST),
                "beta": Action(move=Direction.WEST),
            }
        )

        self.assertEqual(world.states["alpha"].position, (1, 0))
        self.assertEqual(world.states["beta"].position, (1, 2))
        self.assertEqual(world.collision_attempts, 2)
        self.assertEqual(
            world.states["alpha"].last_result.movement,
            MovementResult.BLOCKED_COLLISION,
        )
        self.assertEqual(
            world.states["beta"].last_result.movement,
            MovementResult.BLOCKED_COLLISION,
        )

    def test_attempted_swap_is_also_blocked(self) -> None:
        world = self.make_world(
            agent_positions={"alpha": (1, 0), "beta": (1, 1)}
        )

        world.step(
            {
                "alpha": Action(move=Direction.EAST),
                "beta": Action(move=Direction.WEST),
            }
        )

        self.assertEqual(world.states["alpha"].position, (1, 0))
        self.assertEqual(world.states["beta"].position, (1, 1))
        self.assertEqual(world.collision_attempts, 2)

    def test_message_sent_at_t_is_available_at_the_next_decision(self) -> None:
        world = self.make_world()
        message = Message(MessageKind.DISCOVER, package_location=(2, 2))

        world.step({"alpha": Action(message=message), "beta": Action()})

        beta_percept = world.observe("beta")
        self.assertEqual(beta_percept.time, 1)
        self.assertEqual(
            beta_percept.messages,
            (Message(MessageKind.DISCOVER, package_location=(2, 2), sender="alpha"),),
        )

        world.step({"alpha": Action(), "beta": Action()})
        self.assertEqual(world.observe("beta").messages, ())

    def test_claim_message_keeps_its_package_location_and_sender(self) -> None:
        world = self.make_world()
        world.step(
            {
                "alpha": Action(
                    message=Message(MessageKind.CLAIM, package_location=(2, 2))
                ),
                "beta": Action(),
            }
        )

        self.assertEqual(
            world.observe("beta").messages,
            (Message(MessageKind.CLAIM, package_location=(2, 2), sender="alpha"),),
        )

    def test_a_package_is_delivered_exactly_once(self) -> None:
        world = self.make_world(
            packages={(1, 0)}, agent_positions={"alpha": (1, 0), "beta": (2, 2)}
        )

        world.step({"alpha": Action(interaction=Interaction.PICKUP), "beta": Action()})
        self.assertEqual(world.states["alpha"].carried_package, (1, 0))

        world.step(
            {
                "alpha": Action(move=Direction.NORTH, interaction=Interaction.DROP),
                "beta": Action(),
            }
        )
        self.assertEqual(world.delivered_packages, [(1, 0)])
        self.assertIsNone(world.states["alpha"].carried_package)

        world.step({"alpha": Action(interaction=Interaction.DROP), "beta": Action()})
        self.assertEqual(world.delivered_packages, [(1, 0)])
        self.assertEqual(
            world.states["alpha"].last_result.interaction,
            InteractionResult.INVALID_INTERACTION,
        )
        self.assertEqual(world.finish().delivered_count, 1)


class ExampleAgentTests(unittest.TestCase):
    def test_baseline_picks_up_a_visible_package_in_its_cell(self) -> None:
        world = GridWorld(
            width=3,
            height=3,
            base=(0, 0),
            obstacles=set(),
            packages={(1, 1)},
            agent_positions={"alpha": (1, 1), "beta": (2, 2)},
            horizon=10,
        )
        agent = ExampleBaselineAgent()
        agent.reset("alpha")

        action = agent.act(world.observe("alpha"))

        self.assertEqual(action.interaction, Interaction.PICKUP)


if __name__ == "__main__":
    unittest.main()
