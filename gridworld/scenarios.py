"""Compatibility helpers for the seed 42 starter run."""

from simulator import Agent, make_agents, scenario_world


def starter_world():
    return scenario_world(42)


def starter_agents() -> dict[str, Agent]:
    return make_agents("baseline")


__all__ = ["starter_agents", "starter_world"]
