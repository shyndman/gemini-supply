from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import pytest

from gemini_supply import AuthManager
from gemini_supply.computers import CamoufoxHost


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


@pytest.mark.asyncio
async def test_auth_manager_skips_when_session_valid() -> None:
  host = HostStub(pages=[PageStub(authenticated=True)])

  async def fake_flow(host: CamoufoxHost) -> None:
    stub = cast(HostStub, host)
    stub.flow_calls += 1
    for page in stub.context.pages:
      page.authenticated = True

  manager = AuthManager(cast(CamoufoxHost, host), auth_flow=fake_flow)
  await manager.ensure_authenticated()
  assert host.flow_calls == 0


@pytest.mark.asyncio
async def test_auth_manager_single_flight() -> None:
  host = HostStub(pages=[PageStub(authenticated=False)])

  async def fake_flow(host: CamoufoxHost) -> None:
    stub = cast(HostStub, host)
    stub.flow_calls += 1
    for page in stub.context.pages:
      page.authenticated = True
    await asyncio.sleep(0)

  manager = AuthManager(cast(CamoufoxHost, host), auth_flow=fake_flow)
  await asyncio.gather(
    manager.ensure_authenticated(),
    manager.ensure_authenticated(),
    manager.ensure_authenticated(),
  )
  assert host.flow_calls == 1


@pytest.mark.asyncio
async def test_auth_manager_checks_new_page_when_empty() -> None:
  host = HostStub(pages=[], new_page_authenticated=True)

  async def fake_flow(host: CamoufoxHost) -> None:
    stub = cast(HostStub, host)
    stub.flow_calls += 1

  manager = AuthManager(cast(CamoufoxHost, host), auth_flow=fake_flow)
  await manager.ensure_authenticated()
  assert host.flow_calls == 0
  assert host.created_pages, "Expected AuthManager to open a page when none existed."
  assert host.created_pages[0].closed is False
  assert host.created_pages[0].url.startswith("about:blank#keepalive")
