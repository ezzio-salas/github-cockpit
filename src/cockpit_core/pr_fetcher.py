"""Reads open pull requests by running the GitHub CLI, the way the CLI is already signed in."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

#: Only what the card draws, so the reply stays small.
_FIELDS = "number,title,repository,url,isDraft,updatedAt"

#: Launchers do not always inherit a login shell's PATH, so look in the usual places first.
_INSTALL_DIRECTORIES = (
    Path.home() / ".local/bin",
    Path.home() / ".local/share/mise/shims",
    Path("/usr/local/bin"),
    Path("/usr/bin"),
)


class FetchError(Exception):
    """A read that did not produce pull requests."""


class CliNotFound(FetchError):
    """The `gh` executable was not found."""


class TimedOut(FetchError):
    """`gh` did not answer in time."""


class NotAuthenticated(FetchError):
    """`gh` is installed but not signed in."""


class CommandFailed(FetchError):
    """`gh` exited with an error for some other reason."""


class PullRequestFetcher:
    """Runs `gh search prs` for the two lists the card shows.

    Only the most recently updated few are asked for, because the card is a glance, not a
    queue: a list long enough to scroll would stop being readable at a glance.

    The command is resolved on each fetch, so a CLI installed while the widget runs is
    picked up without a restart.
    """

    def __init__(self, command: str = "gh", timeout: float = 20, limit: int = 5) -> None:
        self._command = command
        self._timeout = timeout
        self._limit = limit

    def fetch_mine(self) -> str:
        """Raw JSON for the open pull requests the signed-in user opened."""
        return self._search("--author=@me")

    def fetch_review_requested(self) -> str:
        """Raw JSON for the open pull requests waiting on the signed-in user's review."""
        return self._search("--review-requested=@me")

    def _search(self, who: str) -> str:
        return self._run([
            "search", "prs", who,
            "--state=open",
            f"--limit={self._limit}",
            f"--json={_FIELDS}",
            "--sort=updated",
        ])

    def _run(self, arguments: list[str]) -> str:
        executable = self._resolve()
        if executable is None:
            raise CliNotFound(self._command)

        # A pager or a colored answer would both corrupt the JSON.
        environment = {**os.environ, "GH_PAGER": "cat", "NO_COLOR": "1", "CLICOLOR": "0"}
        try:
            finished = subprocess.run(
                [str(executable), *arguments],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                stdin=subprocess.DEVNULL,
                env=environment,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise TimedOut(f"{self._command} did not answer in {self._timeout:g}s") from error
        except OSError as error:
            raise CommandFailed(str(error)) from error

        if finished.returncode != 0:
            message = (finished.stderr or finished.stdout or "").strip()
            if _is_authentication_failure(message):
                raise NotAuthenticated(message)
            raise CommandFailed(f"exit {finished.returncode}: {message}")
        return finished.stdout

    def _resolve(self) -> Path | None:
        """The `gh` executable: a path as given, or a bare name looked up by hand then on PATH."""
        if "/" in self._command:
            candidate = Path(self._command).expanduser()
            return candidate if _is_executable(candidate) else None

        for directory in _INSTALL_DIRECTORIES:
            candidate = directory / self._command
            if _is_executable(candidate):
                return candidate

        found = shutil.which(self._command)
        return Path(found) if found else None


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _is_authentication_failure(message: str) -> bool:
    lowered = message.lower()
    return "gh auth login" in lowered or "authentication" in lowered or "not logged" in lowered
