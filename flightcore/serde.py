"""Strict JSON boundary. All money is supplied as strings, never binary floats."""
from dataclasses import asdict
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
import json

from .core import Conditions, Passengers, TimeWindow, Segment, Leg, Quote, Provenance, ReferenceCandidate


def dumps(value, **kwargs):
    def default(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        if isinstance(obj, (date, datetime, time)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, Enum):
            return obj.value
        raise TypeError(type(obj).__name__)
    return json.dumps(value, default=default, ensure_ascii=False, **kwargs)


def amount(value):
    if not isinstance(value, str):
        raise ValueError("JSON 금액은 문자열이어야 합니다")
    return Decimal(value)


def check_booleans(data, names, nullable=False):
    for name in names:
        if name in data and type(data[name]) is not bool and not (nullable and data[name] is None):
            raise ValueError(f"{name}: JSON boolean이 필요합니다")


def conditions_from_dict(data):
    d = dict(data)
    check_booleans(d, ("direct_only", "allow_origin_change", "allow_destination_change", "compare_oneways", "arrival_expansion"))
    for key in ("origins", "destinations"):
        d[key] = tuple(d[key])
    for key in ("start", "end", "return_deadline"):
        if d.get(key):
            d[key] = date.fromisoformat(d[key])
    if "passengers" in d:
        d["passengers"] = Passengers(**d["passengers"])
    for key in ("outbound_window", "inbound_window"):
        if d.get(key):
            d[key] = TimeWindow(time.fromisoformat(d[key]["start"]), time.fromisoformat(d[key]["end"]))
    return Conditions(**d)


def quote_from_dict(data):
    d = dict(data)
    check_booleans(d, ("cached", "baggage_confirmed"))
    check_booleans(d, ("taxes_included", "mandatory_fees_included"), nullable=True)
    d["amount"] = amount(d["amount"])
    if d.get("extra_mandatory_fee") is not None:
        d["extra_mandatory_fee"] = amount(d["extra_mandatory_fee"])
    if d.get("expires_at"):
        d["expires_at"] = datetime.fromisoformat(d["expires_at"])
    d["passengers"] = Passengers(**d.get("passengers", {}))
    p = dict(d["provenance"])
    p["observed_at"] = datetime.fromisoformat(p["observed_at"])
    d["provenance"] = Provenance(**p)
    legs = []
    for leg in d["legs"]:
        segments = []
        for raw in leg["segments"]:
            s = dict(raw)
            s["departure"] = datetime.fromisoformat(s["departure"])
            s["arrival"] = datetime.fromisoformat(s["arrival"])
            segments.append(Segment(**s))
        legs.append(Leg(tuple(segments)))
    d["legs"] = tuple(legs)
    return Quote(**d)


def reference_from_dict(data):
    d = dict(data)
    d["amount"] = amount(d["amount"])
    for key in ("fetched_at", "found_at", "expires_at"):
        if d.get(key):
            d[key] = datetime.fromisoformat(d[key])
    return ReferenceCandidate(**d)
