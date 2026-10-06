"""Reads open pull requests by running the GitHub CLI, the way the CLI is already signed in."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .accounts import HOST
from .comments import COMMENTS_QUERY

#: Only what the card draws, so the reply stays small.
_FIELDS = "id,number,title,repository,url,isDraft,updatedAt"

#: Launchers do not always inherit a login shell's PATH, so look in the usual places first.
_INSTALL_DIRECTORIES = (
    Path.home() / ".local/bin",
    Path.home() / ".local/share/mise/shims",
    Path("/usr/local/bin"),
    Path("/usr/bin"),
)

#: Each would override the account `gh` was asked for, or the one it has active, unseen.
_TOKEN_VARIABLES = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")


class FetchError(Exception):
    """A read that did not produce pull requests."""


class CliNotFound(FetchError):
    """The `gh` executable was not found."""


class TimedOut(FetchError):
    """`gh` did not answer in time."""


class NotAuthenticated(FetchError):
    """`gh` is installed but not signed in."""


class NoAccess(FetchError):
    """`gh` is signed in, but an organization refuses the account, such as for SAML SSO."""


class CommandFailed(FetchError):
    """`gh` exited with an error for some other reason."""


class PullRequestFetcher:
    """Runs `gh search prs` for the two lists the card shows.

    Only the most recently updated few are asked for, because the card is a glance, not a
    queue: a list long enough to scroll would stop being readable at a glance.

    The command is resolved on each fetch, so a CLI installed while the widget runs is
    picked up without a restart.

    With an `account`, each call runs as that account without switching the one `gh` has
    active, which terminals keep using: its token is read from the keyring for that call and
    handed only to that one process, never stored or logged.
    """

    def __init__(
        self, command: str = "gh", account: str | None = None, timeout: float = 20, limit: int = 5
    ) -> None:
        self._command = command
        self._account = account
        self._timeout = timeout
        self._limit = limit

    @property
    def account(self) -> str | None:
        """The account every call runs as, or None for the one `gh` has active."""
        return self._account

    def fetch_accounts(self) -> str:
        """Raw JSON for the github.com accounts `gh` is signed in to; no token is asked for."""
        arguments = ["auth", "status", "--json", "hosts", "--hostname", HOST]
        return self._run(arguments, as_account=False)

    def fetch_mine(self) -> str:
        """Raw JSON for the open pull requests the signed-in user opened."""
        return self._search("--author=@me")

    def fetch_review_requested(self) -> str:
        """Raw JSON for the open pull requests waiting on the signed-in user's review."""
        return self._search("--review-requested=@me")

    def fetch_comments(self, node_ids: list[str]) -> str:
        """Raw GraphQL JSON for the latest comments on the given pull requests."""
        arguments = ["api", "graphql", "-f", f"query={COMMENTS_QUERY}"]
        for node_id in node_ids:
            arguments += ["-f", f"ids[]={node_id}"]
        return self._run(arguments)

    def _search(self, who: str) -> str:
        return self._run([
            "search", "prs", who,
            "--state=open",
            f"--limit={self._limit}",
            f"--json={_FIELDS}",
            "--sort=updated",
        ])

    def _run(self, arguments: list[str], as_account: bool = True) -> str:
        executable = self._resolve()
        if executable is None:
            raise CliNotFound(self._command)

        environment = {
            **{name: value for name, value in os.environ.items() if name not in _TOKEN_VARIABLES},
            # A pager or a colored answer would both corrupt the JSON.
            "GH_PAGER": "cat",
            "NO_COLOR": "1",
            "CLICOLOR": "0",
        }
        if as_account and self._account is not None:
            environment["GH_TOKEN"] = self._token(executable, environment)
        return self._execute(executable, arguments, environment)

    def _token(self, executable: Path, environment: dict[str, str]) -> str:
        """The keyring's token for the chosen account."""
        arguments = ["auth", "token", "--hostname", HOST, "--user", self._account]
        try:
            token = self._execute(executable, arguments, environment).strip()
        except CommandFailed as error:
            raise NotAuthenticated(f"{self._account}: {error}") from error
        if not token:
            raise NotAuthenticated(f"{self._account}: no token")
        return token

    def _execute(self, executable: Path, arguments: list[str], environment: dict[str, str]) -> str:
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
            if _is_access_refusal(message):
                raise NoAccess(message)
            raise CommandFailed(f"exit {finished.returncode}: {message}")
        return finished.stdout

    def _resolve(self) -> Path | None:
        """The `gh` executable: a path as given, or a bare name looked up by hand then on PATH."""
        if "/" in self._command:
            try:
                candidate = Path(self._command).expanduser()
            except RuntimeError:
                # `~nosuchuser/bin/gh` has no home directory to expand to.
                return None
            return candidate if _is_executable(candidate) else None

        for directory in _INSTALL_DIRECTORIES:
            candidate = directory / self._command
            if _is_executable(candidate):
                return candidate

        found = shutil.which(self._command)
        return Path(found) if found else None


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


_AUTHENTICATION_FAILURES = (
    "gh auth login", "authentication", "not logged", "no oauth token", "bad credentials",
    "401 unauthorized", "http 401",
)
_ACCESS_REFUSALS = ("saml", "resource not accessible")


def _is_authentication_failure(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _AUTHENTICATION_FAILURES)


def _is_access_refusal(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _ACCESS_REFUSALS)
