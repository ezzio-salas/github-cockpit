"""The latest comments on the pull requests the card shows, and which of them is news."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from .pull_request import ParseError, parse_timestamp

#: One GraphQL request for every pull request on the card. Conversation comments, review
#: summaries and inline review comments all count; only the last few of each are asked for,
#: because only the newest one is ever shown.
COMMENTS_QUERY = """
query($ids: [ID!]!) {
  viewer { login }
  nodes(ids: $ids) {
    ... on PullRequest {
      number
      repository { nameWithOwner }
      comments(last: 3) { nodes { author { login } body createdAt url } }
      reviews(last: 3) {
        nodes {
          author { login } body submittedAt url
          comments(last: 1) { nodes { author { login } body createdAt url } }
        }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class PullRequestComment:
    """One comment, already reduced to the plain text the bubble shows."""

    number: int
    repo: str
    author: str
    text: str
    created_at: datetime
    url: str

    @property
    def reference(self) -> str:
        return f"#{self.number}"


@dataclass(frozen=True)
class CommentReading:
    """Who is signed in, and the recent comments on the card's pull requests."""

    viewer: str
    comments: tuple[PullRequestComment, ...]


def parse_comments(text: str) -> CommentReading:
    """Reads the answer to `COMMENTS_QUERY`.

    A comment missing its author, time, url or any readable text is skipped, as a pull request
    row is. An answer without `data` raises `ParseError`.
    """
    try:
        answer = json.loads(text)
    except json.JSONDecodeError as error:
        raise ParseError(f"not JSON: {error}") from error
    data = answer.get("data") if isinstance(answer, dict) else None
    if not isinstance(data, dict):
        raise ParseError("expected a GraphQL answer with data")

    viewer = _dig(data, "viewer", "login")
    comments = []
    for pull in _list(data.get("nodes")):
        number = pull.get("number")
        repo = _dig(pull, "repository", "nameWithOwner")
        if not isinstance(number, int) or isinstance(number, bool) or not isinstance(repo, str):
            continue
        for node, time_key in _comment_nodes(pull):
            comment = _comment(node, time_key, number, repo)
            if comment is not None:
                comments.append(comment)
    viewer = viewer if isinstance(viewer, str) else ""
    return CommentReading(viewer=viewer, comments=tuple(comments))


def _comment_nodes(pull: dict) -> list[tuple[dict, str]]:
    found = [(node, "createdAt") for node in _list(_dig(pull, "comments", "nodes"))]
    for review in _list(_dig(pull, "reviews", "nodes")):
        found.append((review, "submittedAt"))
        found.extend((node, "createdAt") for node in _list(_dig(review, "comments", "nodes")))
    return found


def _comment(node: dict, time_key: str, number: int, repo: str) -> PullRequestComment | None:
    author = _dig(node, "author", "login")
    body = node.get("body")
    created_at = parse_timestamp(node.get(time_key))
    url = node.get("url")
    text = excerpt(body) if isinstance(body, str) else ""
    if not isinstance(author, str) or not text or created_at is None or not isinstance(url, str):
        return None
    return PullRequestComment(number, repo, author, text, created_at, url)


def _dig(value: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _list(value: object) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CODE_FENCE = re.compile(r"^\s*```.*$", re.MULTILINE)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TAG = re.compile(r"<[^>]+>")
#: Heading hashes, quote marks, bullets, task boxes and list numbers at the start of a line.
_LINE_MARKER = re.compile(
    r"^\s*(?:#{1,6}\s+|>\s?|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+\.\s+)", re.MULTILINE
)
_EMPHASIS = re.compile(r"\*\*|__|~~|`|(?<!\w)[*_]|[*_](?!\w)")
_WHITESPACE = re.compile(r"\s+")


def excerpt(markdown: str) -> str:
    """Markdown and HTML reduced to one line of plain text, for a bubble a few lines tall.

    Bots hide metadata in HTML comments and wrap footers in tags, so both go; a link keeps its
    words and loses its address; emphasis markers go but a snake_case name keeps its underscores.
    """
    text = _HTML_COMMENT.sub(" ", markdown)
    text = _CODE_FENCE.sub(" ", text)
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _TAG.sub(" ", text)
    text = _LINE_MARKER.sub("", text)
    text = _EMPHASIS.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


class CommentWatch:
    """Decides which comment, if any, is news worth a bubble.

    The first reading announces its newest comment, so a launch shows where things stand.
    After that only a comment newer than every one already seen is announced. The signed-in
    person's own comments are never news to them.
    """

    def __init__(self) -> None:
        self._latest_seen: datetime | None = None

    def announce(self, reading: CommentReading) -> PullRequestComment | None:
        viewer = reading.viewer.casefold()
        others = [comment for comment in reading.comments if comment.author.casefold() != viewer]
        if not others:
            return None
        newest = max(others, key=lambda comment: comment.created_at)
        if self._latest_seen is not None and newest.created_at <= self._latest_seen:
            return None
        self._latest_seen = newest.created_at
        return newest
