#!/usr/bin/env python3
"""Configure Railway for the AnO Discord bot (env vars + optional discord-bot service).

Requires:
  RAILWAY_TOKEN — account or workspace token
  RAILWAY_PROJECT_ID — default: Affairs & Order production project

Optional:
  BOT_API_SECRET — if unset, generates a new secret and sets it on web + discord-bot
  RAILWAY_ENVIRONMENT_ID — if unset, uses the production environment
  GITHUB_REPO — default Manbo04/AnO-Reborn

Usage:
  RAILWAY_TOKEN=... python3 scripts/railway_discord_bot_setup.py
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import urllib.error
import urllib.request

GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"
DEFAULT_PROJECT_ID = "0165e9df-ef94-41b3-ab57-c596994a3165"
DEFAULT_GITHUB_REPO = "Manbo04/AnO-Reborn"
BOT_START_COMMAND = "python scripts/run_discord_bot_if_leader.py"
# Railway service name in production (see natural-gratitude project canvas).
BOT_SERVICE_NAME = os.getenv("RAILWAY_BOT_SERVICE_NAME", "bot")


def _gql(token: str, query: str, variables: dict | None = None) -> dict:
    body = {"query": query}
    if variables:
        body["variables"] = variables
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GraphQL HTTP {exc.code}: {detail}") from exc
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload.get("data") or {}


def _project_environments(token: str, project_id: str) -> list[dict]:
    data = _gql(
        token,
        """
        query($id: String!) {
          project(id: $id) {
            environments { edges { node { id name } } }
          }
        }
        """,
        {"id": project_id},
    )
    edges = data.get("project", {}).get("environments", {}).get("edges", [])
    return [e["node"] for e in edges]


def _project_services(token: str, project_id: str) -> list[dict]:
    data = _gql(
        token,
        """
        query($id: String!) {
          project(id: $id) {
            services { edges { node { id name } } }
          }
        }
        """,
        {"id": project_id},
    )
    edges = data.get("project", {}).get("services", {}).get("edges", [])
    return [e["node"] for e in edges]


def _upsert_var(
    token: str,
    project_id: str,
    environment_id: str,
    service_id: str,
    name: str,
    value: str,
) -> None:
    _gql(
        token,
        """
        mutation($input: VariableUpsertInput!) {
          variableUpsert(input: $input)
        }
        """,
        {
            "input": {
                "projectId": project_id,
                "environmentId": environment_id,
                "serviceId": service_id,
                "name": name,
                "value": value,
                "skipDeploys": True,
            }
        },
    )


def _create_github_service(
    token: str, project_id: str, repo: str, branch: str = "master"
) -> str:
    owner, name = repo.split("/", 1)
    data = _gql(
        token,
        """
        mutation($input: ServiceCreateInput!) {
          serviceCreate(input: $input) {
            id
            name
          }
        }
        """,
        {
            "input": {
                "projectId": project_id,
                "name": BOT_SERVICE_NAME,
                "source": {"repo": name, "owner": owner, "branch": branch},
            }
        },
    )
    svc = data.get("serviceCreate") or {}
    return svc["id"]


def _set_start_command(
    token: str,
    service_id: str,
    environment_id: str,
    start_command: str,
) -> None:
    _gql(
        token,
        """
        mutation($serviceId: String!, $environmentId: String!, $start: String!) {
          serviceInstanceUpdate(
            serviceId: $serviceId
            environmentId: $environmentId
            input: { startCommand: $start }
          )
        }
        """,
        {
            "serviceId": service_id,
            "environmentId": environment_id,
            "start": start_command,
        },
    )


def _get_service_variables(
    token: str, project_id: str, environment_id: str, service_id: str
) -> dict:
    data = _gql(
        token,
        """
        query($projectId: String!, $environmentId: String!, $serviceId: String!) {
          variables(
            projectId: $projectId
            environmentId: $environmentId
            serviceId: $serviceId
          )
        }
        """,
        {
            "projectId": project_id,
            "environmentId": environment_id,
            "serviceId": service_id,
        },
    )
    return data.get("variables") or {}


def _delete_var(
    token: str,
    project_id: str,
    environment_id: str,
    service_id: str,
    name: str,
) -> None:
    try:
        _gql(
            token,
            """
            mutation($input: VariableDeleteInput!) {
              variableDelete(input: $input)
            }
            """,
            {
                "input": {
                    "projectId": project_id,
                    "environmentId": environment_id,
                    "serviceId": service_id,
                    "name": name,
                    "skipDeploys": True,
                }
            },
        )
    except Exception:
        pass


def _redeploy(token: str, service_id: str, environment_id: str) -> None:
    _gql(
        token,
        """
        mutation($serviceId: String!, $environmentId: String!) {
          serviceInstanceDeployV2(
            serviceId: $serviceId
            environmentId: $environmentId
          )
        }
        """,
        {"serviceId": service_id, "environmentId": environment_id},
    )


def main() -> None:
    token = os.getenv("RAILWAY_TOKEN", "").strip()
    if not token:
        print("SKIP: RAILWAY_TOKEN not set")
        sys.exit(0)

    project_id = os.getenv("RAILWAY_PROJECT_ID", DEFAULT_PROJECT_ID)
    repo = os.getenv("GITHUB_REPO", DEFAULT_GITHUB_REPO)
    bot_secret = os.getenv("BOT_API_SECRET", "").strip() or secrets.token_hex(32)
    base_url = os.getenv(
        "BOT_API_BASE_URL", "https://affairsandorder.com"
    ).rstrip("/")

    envs = _project_environments(token, project_id)
    env_id = os.getenv("RAILWAY_ENVIRONMENT_ID", "").strip()
    if not env_id:
        for env in envs:
            if env.get("name", "").lower() == "production":
                env_id = env["id"]
                break
        if not env_id and envs:
            env_id = envs[0]["id"]
    if not env_id:
        print("ERROR: No Railway environment found")
        sys.exit(1)

    services = _project_services(token, project_id)
    by_name = {s["name"]: s["id"] for s in services}
    web_id = by_name.get("web")
    if not web_id:
        for s in services:
            if "web" in s["name"].lower():
                web_id = s["id"]
                break
    if not web_id:
        print("ERROR: web service not found in project")
        sys.exit(1)

    bot_id = by_name.get(BOT_SERVICE_NAME)
    if not bot_id:
        print(f"Creating service {BOT_SERVICE_NAME}...")
        try:
            bot_id = _create_github_service(token, project_id, repo)
            print(f"  created service id={bot_id}")
        except Exception as exc:
            print(f"WARN: could not create discord-bot service: {exc}")
            bot_id = None

    print("Setting BOT_API_SECRET on web service...")
    _upsert_var(token, project_id, env_id, web_id, "BOT_API_SECRET", bot_secret)
    _upsert_var(
        token, project_id, env_id, web_id, "BOT_API_BASE_URL", base_url
    )

    if bot_id:
        print(f"Configuring {BOT_SERVICE_NAME} service (start command + database mode)...")
        web_vars = _get_service_variables(token, project_id, env_id, web_id)
        db_url = web_vars.get("DATABASE_PUBLIC_URL") or web_vars.get("DATABASE_URL")
        if db_url:
            _upsert_var(token, project_id, env_id, bot_id, "DATABASE_URL", db_url)
            print("  copied DATABASE_URL from web to bot (direct DB mode)")
        else:
            _upsert_var(token, project_id, env_id, bot_id, "BOT_API_SECRET", bot_secret)
            _upsert_var(token, project_id, env_id, bot_id, "BOT_API_BASE_URL", base_url)
            print("  set BOT_API_* on bot (no DATABASE_URL on web to copy)")
        for obsolete in ("DISCORD_BOT_URL", "PORT"):
            _delete_var(token, project_id, env_id, bot_id, obsolete)
        try:
            _set_start_command(token, bot_id, env_id, BOT_START_COMMAND)
        except Exception as exc:
            print(f"WARN: start command update: {exc}")
        try:
            _redeploy(token, bot_id, env_id)
            print(f"Triggered {BOT_SERVICE_NAME} deploy")
        except Exception as exc:
            print(f"WARN: bot redeploy: {exc}")

    try:
        _redeploy(token, web_id, env_id)
        print("Triggered web redeploy")
    except Exception as exc:
        print(f"WARN: web redeploy: {exc}")

    print("BOT_API_SECRET configured (store in your password manager if newly generated).")
    if not os.getenv("BOT_API_SECRET"):
        print(f"Generated BOT_API_SECRET={bot_secret}")


if __name__ == "__main__":
    main()
