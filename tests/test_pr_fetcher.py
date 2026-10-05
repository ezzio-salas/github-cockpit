"""The fetcher is exercised against stand-in `gh` scripts, so no test reaches the network."""

import os
import stat

import pytest

from cockpit_core.pr_fetcher import (
    CliNotFound,
    CommandFailed,
    NotAuthenticated,
    PullRequestFetcher,
    TimedOut,
)


def fake_gh(directory, body, name="gh"):
    """Writes an executable stand-in for `gh` and returns its path."""
    script = directory / name
    script.write_text("#!/bin/bash\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_returns_what_the_cli_wrote(tmp_path):
    gh = fake_gh(tmp_path, 'echo "[]"')
    assert PullRequestFetcher(command=str(gh)).fetch_mine().strip() == "[]"


def test_asks_for_the_pull_requests_the_user_opened(tmp_path):
    gh = fake_gh(tmp_path, 'printf "%s\\n" "$@"')
    arguments = PullRequestFetcher(command=str(gh), limit=5).fetch_mine().split("\n")

    assert arguments[:3] == ["search", "prs", "--author=@me"]
    assert "--state=open" in arguments
    assert "--limit=5" in arguments
    assert "--sort=updated" in arguments
    assert "--json=number,title,repository,url,isDraft,updatedAt" in arguments


def test_asks_for_the_pull_requests_waiting_on_the_users_review(tmp_path):
    gh = fake_gh(tmp_path, 'printf "%s\\n" "$@"')
    arguments = PullRequestFetcher(command=str(gh)).fetch_review_requested().split("\n")

    assert arguments[:3] == ["search", "prs", "--review-requested=@me"]


def test_the_pager_is_disabled_so_it_cannot_corrupt_the_json(tmp_path):
    gh = fake_gh(tmp_path, 'echo "$GH_PAGER"')
    assert PullRequestFetcher(command=str(gh)).fetch_mine().strip() == "cat"


def test_a_missing_executable_is_reported_as_such(tmp_path):
    with pytest.raises(CliNotFound):
        PullRequestFetcher(command=str(tmp_path / "absent")).fetch_mine()


def test_a_file_that_is_not_executable_does_not_count(tmp_path):
    (tmp_path / "gh").write_text("#!/bin/bash\necho []")
    with pytest.raises(CliNotFound):
        PullRequestFetcher(command=str(tmp_path / "gh")).fetch_mine()


def test_being_signed_out_is_told_apart_from_other_failures(tmp_path):
    gh = fake_gh(tmp_path, 'echo "To get started with GitHub CLI, please run: gh auth login" >&2\nexit 4')
    with pytest.raises(NotAuthenticated):
        PullRequestFetcher(command=str(gh)).fetch_mine()


def test_any_other_non_zero_exit_is_a_plain_failure(tmp_path):
    gh = fake_gh(tmp_path, 'echo "HTTP 503" >&2\nexit 1')
    with pytest.raises(CommandFailed) as failure:
        PullRequestFetcher(command=str(gh)).fetch_mine()
    assert "503" in str(failure.value)


def test_a_cli_that_never_answers_is_given_up_on(tmp_path):
    gh = fake_gh(tmp_path, "sleep 30")
    with pytest.raises(TimedOut):
        PullRequestFetcher(command=str(gh), timeout=0.5).fetch_mine()


def test_a_bare_name_is_looked_up_rather_than_run_from_the_working_directory(tmp_path, monkeypatch):
    fake_gh(tmp_path, 'echo "[]"', name="gh-stub")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert PullRequestFetcher(command="gh-stub").fetch_mine().strip() == "[]"


def test_a_bare_name_that_is_nowhere_is_reported_as_a_missing_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr("cockpit_core.pr_fetcher._INSTALL_DIRECTORIES", ())
    with pytest.raises(CliNotFound):
        PullRequestFetcher(command="gh-definitely-absent").fetch_mine()


def test_the_cli_is_resolved_on_each_fetch_so_a_later_install_is_picked_up(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr("cockpit_core.pr_fetcher._INSTALL_DIRECTORIES", ())
    fetcher = PullRequestFetcher(command="gh-installed-late")

    with pytest.raises(CliNotFound):
        fetcher.fetch_mine()

    fake_gh(tmp_path, 'echo "[]"', name="gh-installed-late")
    assert fetcher.fetch_mine().strip() == "[]"


def test_the_cli_never_reads_the_widgets_stdin(tmp_path):
    # A `gh` waiting on input would otherwise hang the fetch until the timeout.
    gh = fake_gh(tmp_path, "cat; echo done")
    assert PullRequestFetcher(command=str(gh), timeout=5).fetch_mine().strip() == "done"
