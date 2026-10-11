"""Caller-supplied, source-backed city membership; no inferred route existence."""
from dataclasses import dataclass
from datetime import date
from .core import code, link


@dataclass(frozen=True)
class CityAirports:
    city: str
    airports: tuple[str, ...]
    source_url: str
    checked_on: date

    def __post_init__(self):
        if not self.city.strip() or not self.airports:
            raise ValueError("도시와 공항 후보가 필요합니다")
        for airport in self.airports:
            code(airport)
        link(self.source_url)

    def select(self, include=None, exclude=()) -> tuple[str, ...]:
        chosen = self.airports if include is None else tuple(include)
        if set(chosen) - set(self.airports) or set(exclude) - set(self.airports):
            raise ValueError("도시 후보 목록에 없는 공항입니다")
        result = tuple(dict.fromkeys(a for a in chosen if a not in exclude))
        if not result:
            raise ValueError("목적지 공항을 하나 이상 선택해야 합니다")
        return result
