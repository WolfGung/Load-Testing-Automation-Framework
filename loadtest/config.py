"""Validated, file-based workload definitions; stage times exclude warm-up."""

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Profile:
    name: str
    purpose: str
    warmup_seconds: float
    spawn_rate: float
    think_seconds: float
    stages: list[dict]
    thresholds: dict

    @classmethod
    def read(cls, name):
        profile = cls(**json.loads((ROOT / "profiles" / f"{name}.json").read_text()))
        previous = 0
        if profile.warmup_seconds < 0 or profile.spawn_rate <= 0 or profile.think_seconds < 0:
            raise ValueError("Invalid warm-up, spawn rate or think time")
        if not profile.stages:
            raise ValueError("At least one stage is required")
        for stage in profile.stages:
            if stage["until_seconds"] <= previous or stage["users"] < 1:
                raise ValueError("Stages require increasing times and positive users")
            previous = stage["until_seconds"]
        return profile

    @property
    def duration(self):
        return self.warmup_seconds + self.stages[-1]["until_seconds"]

    def users_at(self, elapsed):
        if elapsed < self.warmup_seconds:
            return self.stages[0]["users"]
        for stage in self.stages:
            if elapsed - self.warmup_seconds < stage["until_seconds"]:
                return stage["users"]
        return None
