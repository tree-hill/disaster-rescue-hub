"""通用分页响应 Schema。

对照 API_SPEC §0.3 / §0.6：
    {
      "items": [...],
      "total": 25,
      "page": 1,
      "page_size": 20
    }

后续 task / auction / alert 等所有 List 接口复用本 schema，避免每个领域重写。
"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    total: int
    page: int
    page_size: int
