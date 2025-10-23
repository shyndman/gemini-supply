#!/usr/bin/env -S uv run
"""Call Home Assistant endpoints using gemini-supply config."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

import requests

from gemini_supply.config import AppConfig, HomeAssistantShoppingListConfig, load_config


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Call Home Assistant endpoints using gemini-supply config.",
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=None,
    help="Path to config.yaml (defaults to gemini-supply standard location)",
  )
  parser.add_argument(
    "--timeout",
    type=float,
    default=10.0,
    help="HTTP timeout in seconds (default: 10)",
  )

  subparsers = parser.add_subparsers(dest="mode", required=True)

  endpoint = subparsers.add_parser("endpoint", help="Call an arbitrary REST endpoint")
  endpoint.add_argument("path", help="Path relative to the Home Assistant base URL")
  endpoint.add_argument(
    "--method",
    choices=("GET", "POST", "DELETE"),
    default="GET",
    help="HTTP method to use (default: GET)",
  )
  endpoint.add_argument(
    "--data",
    help="JSON payload for POST/DELETE requests",
  )

  service = subparsers.add_parser("service", help="Invoke a Home Assistant service")
  service.add_argument("service_name", help="Service in domain.service form")
  service.add_argument(
    "--entity-id",
    help="Entity ID to target (convenience shortcut)",
  )
  service.add_argument(
    "--target",
    help="Raw JSON target block (overrides --entity-id)",
  )
  service.add_argument(
    "--data",
    help="JSON payload for the service data block",
  )

  return parser


def _load_app_config(path: Path | None) -> AppConfig:
  try:
    return load_config(path)
  except Exception as exc:
    print(f"failed to load config: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc


def _resolve_home_assistant(cfg: AppConfig) -> HomeAssistantShoppingListConfig:
  shopping_cfg = cfg.shopping_list
  if not isinstance(shopping_cfg, HomeAssistantShoppingListConfig):
    print("config shopping_list provider must be 'home_assistant'", file=sys.stderr)
    raise SystemExit(1)
  return shopping_cfg


def _load_json(arg: str | None, description: str) -> object | None:
  if arg is None:
    return None
  try:
    return json.loads(arg)
  except json.JSONDecodeError as exc:
    print(f"failed to parse {description} as JSON: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc


def _prepare_headers(token: str) -> Mapping[str, str]:
  return {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
  }


def _request(
  *,
  url: str,
  method: str,
  headers: Mapping[str, str],
  payload: object | None,
  timeout: float,
) -> tuple[int, Mapping[str, str], bytes]:
  try:
    response = requests.request(
      method=method,
      url=url,
      headers=dict(headers),
      json=payload,
      timeout=timeout,
    )
    return response.status_code, dict(response.headers), response.content
  except requests.exceptions.RequestException as exc:
    print(f"request failed: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc


def _print_response(status: int, headers: Mapping[str, str], body: bytes) -> None:
  print(f"Status: {status}")
  if headers:
    print("Headers:")
    for key, value in headers.items():
      print(f"  {key}: {value}")

  if not body:
    print("\n<empty body>")
    return

  text = body.decode("utf-8", errors="replace")
  try:
    parsed = json.loads(text)
  except json.JSONDecodeError:
    print("\n" + text)
    return

  pretty = json.dumps(parsed, indent=2, sort_keys=True)
  print("\n" + pretty)


def _call_endpoint(
  *,
  base_url: str,
  token: str,
  args: argparse.Namespace,
) -> None:
  path = args.path.lstrip("/")
  url = f"{base_url}/{path}"
  if args.method in {"POST", "DELETE"}:
    payload = _load_json(args.data, "endpoint data")
  else:
    payload = None
    if args.data is not None:
      print("--data is only valid with POST or DELETE", file=sys.stderr)
      raise SystemExit(1)

  status, headers, body = _request(
    url=url,
    method=args.method,
    headers=_prepare_headers(token),
    payload=payload,
    timeout=args.timeout,
  )
  _print_response(status, headers, body)


def _call_service(
  *,
  base_url: str,
  token: str,
  args: argparse.Namespace,
) -> None:
  service_name = args.service_name
  if "." not in service_name:
    print("service name must be in domain.service form", file=sys.stderr)
    raise SystemExit(1)
  domain, service = service_name.split(".", 1)
  target = None
  if args.target and args.entity_id:
    print("specify either --target or --entity-id, not both", file=sys.stderr)
    raise SystemExit(1)
  if args.target:
    target = _load_json(args.target, "service target")
  elif args.entity_id:
    target = {"entity_id": args.entity_id}

  data_block = _load_json(args.data, "service data")

  payload: dict[str, object] = {}
  if target is not None:
    payload["target"] = target
  if data_block is not None:
    payload["data"] = data_block

  url = f"{base_url}/api/services/{domain}/{service}"
  status, headers, body = _request(
    url=url,
    method="POST",
    headers=_prepare_headers(token),
    payload=payload if payload else None,
    timeout=args.timeout,
  )
  _print_response(status, headers, body)


def main() -> None:
  parser = _build_parser()
  args = parser.parse_args()

  cfg = _load_app_config(args.config)
  ha_cfg = _resolve_home_assistant(cfg)

  base_url = ha_cfg.url.rstrip("/")
  token = ha_cfg.token

  if args.mode == "endpoint":
    _call_endpoint(base_url=base_url, token=token, args=args)
    return

  if args.mode == "service":
    _call_service(base_url=base_url, token=token, args=args)
    return

  parser.error("unhandled mode")


if __name__ == "__main__":
  main()
