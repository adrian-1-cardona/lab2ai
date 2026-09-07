"""Runs an episode and creates the event log."""

from __future__ import annotations

from typing import Mapping, Protocol

from .environment import GridWorld
from .models import Action, EpisodeResult, Percept, Terrain


class Agent(Protocol):
    def reset(self, agent_id: str) -> None: ...

    def act(self, percept: Percept) -> Action: ...


def run_episode(env: GridWorld, agents: Mapping[str, Agent]) -> EpisodeResult:
    """Run the agents until they finish or run out of time."""

    if set(agents) != set(env.agent_ids):
        raise ValueError("agents must match the environment's agent IDs exactly")

    env.reset()
    for agent_id in env.agent_ids:
        agents[agent_id].reset(agent_id)

    while env.time < env.horizon and not env.is_complete():
        percepts = {agent_id: env.observe(agent_id) for agent_id in env.agent_ids}
        actions = {
            agent_id: agents[agent_id].act(percepts[agent_id])
            for agent_id in env.agent_ids
        }
        summaries = {
            agent_id: summarize_percept(percepts[agent_id]) for agent_id in env.agent_ids
        }
        env.step(actions, summaries)

    return env.finish()


def summarize_percept(percept: Percept) -> str:
    """Summarize what an agent could see during its turn."""

    visible_packages = sorted(
        position
        for position, cell in percept.visible_cells.items()
        if cell.package_present
    )
    visible_base = next(
        (
            position
            for position, cell in percept.visible_cells.items()
            if cell.terrain is Terrain.BASE
        ),
        None,
    )
    return (
        f"pos={percept.self_position}; carrying={percept.carrying}; "
        f"visible_packages={visible_packages}; base={visible_base}; "
        f"messages={len(percept.messages)}"
    )
