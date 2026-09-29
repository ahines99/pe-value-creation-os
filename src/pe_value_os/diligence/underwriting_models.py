"""Version-aware parsing without changing legacy underwriting serializations."""

from typing import Any

from pydantic import TypeAdapter

from .interactions import InteractionCase
from .underwriting import UnderwritingCase

UnderwritingModel = UnderwritingCase | InteractionCase
_ADAPTER: TypeAdapter[UnderwritingModel] = TypeAdapter(UnderwritingModel)


def parse_underwriting(value: Any) -> UnderwritingModel:
    return _ADAPTER.validate_python(value)


def read_underwriting(value: str | bytes) -> UnderwritingModel:
    return _ADAPTER.validate_json(value)
