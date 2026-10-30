"""The source of "now", injected so that time-dependent code can be tested."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """The real wall clock."""

    def now(self) -> datetime:
        return datetime.now()


@dataclass
class FixedClock:
    """A clock that shows whatever it is told to; used by tests, demos and screenshots."""

    current: datetime

    def now(self) -> datetime:
        return self.current
