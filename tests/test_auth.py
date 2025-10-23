from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class PageStub:
  def __init__(self, authenticated: bool) -> None:
    self.authenticated = authenticated
    self.url = "https://www.metro.ca/en/home"
    self.closed = False

  async def close(self) -> None:
    self.closed = True

  async def wait_for_load_state(self, *_: object, **__: object) -> None:
    return None

  async def goto(self, url: str, **__: object) -> None:
    self.url = url

  def is_closed(self) -> bool:
    return self.closed


class ContextStub:
  def __init__(self, pages: list[PageStub] | None = None) -> None:
    self.pages: list[PageStub] = pages or []


class HostStub:
  def __init__(
    self,
    *,
    pages: list[PageStub] | None = None,
    new_page_authenticated: bool = True,
  ) -> None:
    self.context = ContextStub(pages)
    self.new_page_authenticated = new_page_authenticated
    self.flow_calls = 0
    self.created_pages: list[PageStub] = []

  async def is_authenticated(self, page: PageStub) -> bool:
    return page.authenticated

  async def new_page(self) -> PageStub:
    page = PageStub(self.new_page_authenticated)
    self.context.pages.append(page)
    self.created_pages.append(page)
    return page

  def unrestricted(self):
    @asynccontextmanager
    async def _noop() -> AsyncIterator[None]:
      yield

    return _noop()
