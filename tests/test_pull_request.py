from datetime import datetime, timezone

import pytest

from cockpit_core.pull_request import ParseError, PullRequest, parse

#: One real row, as `gh search prs --json number,title,repository,url,isDraft,updatedAt` writes it.
SAMPLE = """[
  {"isDraft": false, "number": 44,
   "repository": {"name": "material-tailwind", "nameWithOwner": "ezzio-salas/material-tailwind"},
   "title": "[Snyk] Security upgrade next from 10.2.3 to 15.5.10",
   "updatedAt": "2026-02-01T12:05:49Z",
   "url": "https://github.com/ezzio-salas/material-tailwind/pull/44"}
]"""


def test_reads_the_fields_the_card_shows():
    (pull,) = parse(SAMPLE)

    assert pull == PullRequest(
        number=44,
        title="[Snyk] Security upgrade next from 10.2.3 to 15.5.10",
        repo="ezzio-salas/material-tailwind",
        url="https://github.com/ezzio-salas/material-tailwind/pull/44",
        is_draft=False,
        updated_at=datetime(2026, 2, 1, 12, 5, 49, tzinfo=timezone.utc),
    )
    assert pull.reference == "#44"


def test_an_empty_result_is_an_empty_list_not_a_failure():
    # Nobody has asked for a review: a normal state, not an error.
    assert parse("[]") == []


def test_titles_are_trimmed():
    (pull,) = parse(
        '[{"number": 1, "title": "  Fix it  ", "repository": {"nameWithOwner": "a/b"}, "url": "u"}]'
    )
    assert pull.title == "Fix it"


def test_drafts_are_marked():
    (pull,) = parse(
        '[{"number": 1, "title": "t", "isDraft": true, "repository": {"nameWithOwner": "a/b"}, "url": "u"}]'
    )
    assert pull.is_draft


@pytest.mark.parametrize(
    "row",
    [
        '{"title": "t", "repository": {"nameWithOwner": "a/b"}, "url": "u"}',  # no number
        '{"number": 1, "repository": {"nameWithOwner": "a/b"}, "url": "u"}',  # no title
        '{"number": 1, "title": "t", "url": "u"}',  # no repository
        '{"number": 1, "title": "t", "repository": {}, "url": "u"}',  # no nameWithOwner
        '{"number": 1, "title": "t", "repository": {"nameWithOwner": "a/b"}}',  # no url
        '"not an object"',
    ],
)
def test_a_row_the_card_could_not_draw_is_skipped_not_guessed_at(row):
    assert parse(f"[{row}]") == []


def test_one_unusable_row_does_not_cost_the_others():
    pulls = parse(
        '[{"number": 1, "title": "t", "repository": {"nameWithOwner": "a/b"}, "url": "u"},'
        ' {"title": "no number"}]'
    )
    assert [pull.number for pull in pulls] == [1]


def test_a_timestamp_without_a_zone_is_read_as_utc():
    (pull,) = parse(
        '[{"number": 1, "title": "t", "repository": {"nameWithOwner": "a/b"}, "url": "u",'
        ' "updatedAt": "2026-02-01T12:05:49"}]'
    )
    assert pull.updated_at == datetime(2026, 2, 1, 12, 5, 49, tzinfo=timezone.utc)


@pytest.mark.parametrize("value", ['"yesterday"', "null", "17", '""'])
def test_an_unreadable_timestamp_leaves_the_age_blank_rather_than_failing(value):
    (pull,) = parse(
        '[{"number": 1, "title": "t", "repository": {"nameWithOwner": "a/b"}, "url": "u",'
        f' "updatedAt": {value}}}]'
    )
    assert pull.updated_at is None


@pytest.mark.parametrize("text", ["", "not json", "{}", '"a string"', "null"])
def test_anything_that_is_not_a_json_array_is_a_failure(text):
    # The card has to tell these apart from "no pull requests", so they raise.
    with pytest.raises(ParseError):
        parse(text)
