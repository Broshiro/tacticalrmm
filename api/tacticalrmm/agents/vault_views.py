"""
Vaultwarden integration for the TRMM remote session credential panel.

The Vaultwarden master token is NEVER sent to the browser.  This view
proxies the Vaultwarden API server-side, filters results to the
agent's client, and returns a safe subset of fields.

Configuration (set in the TRMM server .env / docker-compose env):
    VAULTWARDEN_URL            e.g. https://vault.example.com
    VAULTWARDEN_CLIENT_ID      personal API key client_id
    VAULTWARDEN_CLIENT_SECRET  personal API key client_secret

A future settings UI will migrate these to CoreSettings so they can
be configured from the TRMM web UI without touching the server.
"""

import os

import requests
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tacticalrmm.helpers import notify_error

from .models import Agent
from .permissions import MeshPerms

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VW_URL = os.environ.get("VAULTWARDEN_URL", "").rstrip("/")
_VW_CLIENT_ID = os.environ.get("VAULTWARDEN_CLIENT_ID", "")
_VW_CLIENT_SECRET = os.environ.get("VAULTWARDEN_CLIENT_SECRET", "")


def _get_vw_token() -> str:
    """Authenticate with Vaultwarden and return a short-lived bearer token."""
    resp = requests.post(
        f"{_VW_URL}/identity/connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": _VW_CLIENT_ID,
            "client_secret": _VW_CLIENT_SECRET,
            "scope": "api",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _fetch_ciphers(token: str) -> list:
    """Fetch all login ciphers the API key has access to."""
    resp = requests.get(
        f"{_VW_URL}/api/ciphers",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("Data", [])


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


class AgentVaultCreds(APIView):
    """
    GET /agents/<agent_id>/vaultcreds/

    Returns Vaultwarden login items scoped to the agent's client name.
    Uses the same MeshPerms permission as the remote desktop session so
    only users who can take control can see credentials.

    Response: list of objects:
        { id, name, username, password, notes }

    Returns 200 + empty list if Vaultwarden is not configured.
    Returns 503 if Vaultwarden is configured but unreachable.
    """

    permission_classes = [IsAuthenticated, MeshPerms]

    def get(self, request, agent_id: str):
        agent = get_object_or_404(Agent, agent_id=agent_id)

        # --- guard: Vaultwarden not configured ---
        if not all([_VW_URL, _VW_CLIENT_ID, _VW_CLIENT_SECRET]):
            return Response([])

        client_name = agent.client.name.lower().strip()

        try:
            token = _get_vw_token()
            ciphers = _fetch_ciphers(token)
        except requests.RequestException as exc:
            return notify_error(f"Vaultwarden unreachable: {exc}")
        except (KeyError, ValueError) as exc:
            return notify_error(f"Vaultwarden response parse error: {exc}")

        # --- filter to this client ---
        # Match cipher name contains client name OR client name contains cipher
        # folder prefix.  Case-insensitive.  Type 1 = Login (skip Notes/Cards).
        results = []
        for cipher in ciphers:
            if cipher.get("Type") != 1:
                continue

            cipher_name = (cipher.get("Name") or "").lower().strip()
            login = cipher.get("Login") or {}

            # Scope: include if client name appears in the cipher name,
            # or if there is no client name (show all when client unknown).
            if client_name and client_name not in cipher_name:
                continue

            results.append(
                {
                    "id": cipher.get("Id"),
                    "name": cipher.get("Name"),
                    "username": login.get("Username") or "",
                    "password": login.get("Password") or "",
                    "notes": cipher.get("Notes") or "",
                }
            )

        return Response(results)
