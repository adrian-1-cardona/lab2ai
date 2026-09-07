"""Run the basic agents on the starter map."""

from __future__ import annotations

from gridworld.runner import run_episode
from gridworld.scenarios import starter_agents, starter_world


def _message_label(message) -> str:
    if message is None:
        return "-"
    return f"{message.kind.value}@{message.package_location}"


def main() -> None:
    world = starter_world()
    result = run_episode(world, starter_agents())

    print("CSC4880 Cooperative Multi-Agent Gridworld")
    print("Independent baseline example (not a coordinated solution)")
    print()
    print(f"Steps: {result.steps}")
    print(f"Packages delivered: {result.delivered_count}")
    print(f"Collision attempts: {result.collision_attempts}")
    print(f"Team score: {result.score}")
    print()
    print("First 16 event-log entries")
    for event in result.events[:16]:
        print(
            f"t={event.time:02d} {event.agent_id:7} "
            f"action=({event.action.move.name},{event.action.interaction.name}) "
            f"sent={_message_label(event.sent_message)} "
            f"result=({event.result.movement.value},{event.result.interaction.value}) "
            f"pos={event.final_position}"
        )


if __name__ == "__main__":
    main()
