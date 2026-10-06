"""The GitHub accounts the CLI is signed in to, read from `gh auth status --json hosts`."""

from __future__ import annotations

import json
from dataclasses import dataclass

#: The only host the card reads; an enterprise host's accounts are not offered.
HOST = "github.com"


@dataclass(frozen=True)
class GitHubAccount:
    login: str
    #: Whether `gh` itself uses this account when none is named.
    is_active: bool


def parse_accounts(raw: str) -> tuple[GitHubAccount, ...]:
    """The github.com accounts in one `gh auth status --json hosts` answer, in `gh`'s order.

    An answer that is not readable gives no accounts rather than raising: the list only feeds
    a menu, and the card works without it.
    """
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    hosts = loaded.get("hosts") if isinstance(loaded, dict) else None
    entries = hosts.get(HOST) if isinstance(hosts, dict) else None
    if not isinstance(entries, list):
        return ()
    return tuple(
        GitHubAccount(entry["login"], entry.get("active") is True)
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("login"), str) and entry["login"]
    )
