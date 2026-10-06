import json

from cockpit_core.accounts import GitHubAccount, parse_accounts


def status(hosts):
    return json.dumps({"hosts": hosts})


def test_lists_the_github_accounts_in_order_and_marks_the_active_one():
    raw = status({"github.com": [
        {"login": "personal", "active": True, "state": "success", "tokenSource": "keyring"},
        {"login": "work", "active": False, "state": "success", "tokenSource": "keyring"},
    ]})

    assert parse_accounts(raw) == (GitHubAccount("personal", True), GitHubAccount("work", False))


def test_accounts_on_other_hosts_are_not_offered():
    raw = status({
        "github.com": [{"login": "personal", "active": True}],
        "github.example.com": [{"login": "enterprise", "active": True}],
    })

    assert parse_accounts(raw) == (GitHubAccount("personal", True),)


def test_an_entry_without_a_login_is_skipped():
    raw = status({"github.com": [{"active": True}, {"login": ""}, {"login": "work"}]})

    assert parse_accounts(raw) == (GitHubAccount("work", False),)


def test_an_unreadable_answer_gives_no_accounts():
    assert parse_accounts("not json") == ()
    assert parse_accounts("[]") == ()
    assert parse_accounts(status({})) == ()
