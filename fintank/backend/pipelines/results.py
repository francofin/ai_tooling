"""What every pipeline stage reports back, so the runner and the checks act on
counts instead of reading printed progress lines."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

FAILED_ITEMS_CAP = 200  # keeps reports readable when a whole feed is down
_SECRET_PARAM = re.compile(r"(api_?key=)[^&\s'\"]+", re.IGNORECASE)


def redact(text: str) -> str:
    """Mask API keys inside URLs before an error message reaches a report or
    an email — requests puts the full URL, apikey included, in HTTPError."""
    return _SECRET_PARAM.sub(r"\1***", text)


@dataclass
class StageResult:
    name: str
    attempted: int = 0
    saved: int = 0
    failed: int = 0
    no_data: int = 0
    failed_items: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    @property
    def failure_rate(self) -> float:
        return self.failed / self.attempted if self.attempted else 0.0

    def record(self, ok: bool, item: str | None = None) -> None:
        """Count one attempt; a failure may name the item that failed."""
        self.attempted += 1
        if ok:
            self.saved += 1
        else:
            self.failed += 1
            if item is not None:
                self.failed_items.append(item)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["failure_rate"] = round(self.failure_rate, 4)
        data["failed_items"] = self.failed_items[:FAILED_ITEMS_CAP]
        data["failed_items_truncated"] = len(self.failed_items) > FAILED_ITEMS_CAP
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "StageResult":
        names = ("name", "attempted", "saved", "failed", "no_data",
                 "failed_items", "detail")
        return cls(**{k: data[k] for k in names if k in data})
