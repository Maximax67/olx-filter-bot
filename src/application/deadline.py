from dataclasses import dataclass
from typing import Self

from src.application.interfaces.clock import Clock


@dataclass(frozen=True, slots=True)
class Deadline:
    clock: Clock
    expires_at: float

    @classmethod
    def after(cls, clock: Clock, seconds: float) -> Self:
        return cls(clock=clock, expires_at=clock.monotonic() + seconds)

    def remaining(self) -> float:
        return max(0.0, self.expires_at - self.clock.monotonic())
