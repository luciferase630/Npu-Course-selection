from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PopulationAssignment:
    selector: str
    agent: str


@dataclass(frozen=True)
class Population:
    assignments: tuple[PopulationAssignment, ...]

    @classmethod
    def parse(cls, value: str) -> "Population":
        if not value:
            return cls((PopulationAssignment("background", "behavioral"),))
        assignments = []
        for raw_part in value.split(","):
            part = raw_part.strip()
            if not part:
                continue
            if "=" not in part:
                raise ValueError(f"population part must contain '=': {part}")
            selector, agent = [item.strip() for item in part.split("=", 1)]
            if not selector or not agent:
                raise ValueError(f"invalid population assignment: {part}")
            assignments.append(PopulationAssignment(selector=selector, agent=agent))
        if not assignments:
            raise ValueError("population must include at least one assignment")
        return cls(tuple(assignments))

    @property
    def background_agent(self) -> str:
        for assignment in self.assignments:
            if assignment.selector == "background":
                return assignment.agent
        return "behavioral"

    @property
    def focal_assignments(self) -> dict[str, str]:
        result = {}
        for assignment in self.assignments:
            if assignment.selector.startswith("focal:"):
                result[assignment.selector.split(":", 1)[1]] = assignment.agent
        return result
