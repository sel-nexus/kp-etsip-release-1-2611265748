"""Provide bounded list contracts shared by inventory endpoints."""
from typing import Generic, TypeVar
from fastapi import Query
from pydantic import BaseModel, Field

Item = TypeVar("Item")


class Page(BaseModel, Generic[Item]):
    """Return the filtered total independently of the current page's items."""
    items: list[Item]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=100)


class Pagination:
    """Validate query pagination before a repository performs skip/limit."""
    def __init__(self, page: int = Query(1, ge=1, le=21474836), pageSize: int = Query(25, ge=1, le=100)) -> None:
        """Bound page offsets to Mongo's signed integer range."""
        self.page = page
        self.pageSize = pageSize
