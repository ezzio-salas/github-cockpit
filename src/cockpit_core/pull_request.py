"""One open pull request, and the parsing of `gh`'s JSON into them."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PullRequest:
    """A single open pull request, as the widget shows it."""

    number: int
    title: str
    #: `owner/name`, shown on the line under the title.
    repo: str
    url: str
    is_draft: bool
    #: When it last changed, or None when `gh` did not report it.
    updated_at: datetime | None

    @property
    def reference(self) -> str:
        """`#412`, the short form shown beside the title."""
        return f"#{self.number}"


class ParseError(Exception):
    """`gh` answered, but not with a list of pull requests."""


def parse(text: str) -> list[PullRequest]:
    """Turns one `gh search prs --json ...` answer into pull requests.

    Rows missing a number, title, repo or url are skipped rather than guessed at, so a
    change in `gh`'s output costs at most a row. A reply that is not a JSON array raises.
    """
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as error:
        raise ParseError(f"not JSON: {error}") from error
    if not isinstance(rows, list):
        raise ParseError(f"expected a JSON array, got {type(rows).__name__}")

    pulls = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pull = _pull_request(row)
        if pull is not None:
            pulls.append(pull)
    return pulls


def _pull_request(row: dict) -> PullRequest | None:
    number = row.get("number")
    title = row.get("title")
    url = row.get("url")
    repository = row.get("repository")
    repo = repository.get("nameWithOwner") if isinstance(repository, dict) else None

    if not isinstance(number, int) or not title or not url or not repo:
        return None

    return PullRequest(
        number=number,
        title=str(title).strip(),
        repo=str(repo),
        url=str(url),
        is_draft=bool(row.get("isDraft", False)),
        updated_at=_timestamp(row.get("updatedAt")),
    )


def _timestamp(value: object) -> datetime | None:
    """Reads GitHub's `2026-02-01T12:05:49Z`; anything else becomes None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
