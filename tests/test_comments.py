import json
from datetime import datetime, timezone

import pytest

from cockpit_core.comments import (
    CommentReading,
    CommentWatch,
    PullRequestComment,
    excerpt,
    parse_comments,
)
from cockpit_core.pull_request import ParseError


def at(minute: int) -> datetime:
    return datetime(2026, 10, 5, 12, minute, tzinfo=timezone.utc)


def node(author="octocat", body="Looks good", minute=0, time_key="createdAt", url="https://c"):
    return {"author": {"login": author} if author else None, "body": body,
            time_key: at(minute).isoformat().replace("+00:00", "Z"), "url": url}


def answer(*pulls, viewer="me"):
    return json.dumps({"data": {"viewer": {"login": viewer}, "nodes": list(pulls)}})


def pull(number=81, comments=(), reviews=()):
    return {"number": number, "repository": {"nameWithOwner": "a/b"},
            "comments": {"nodes": list(comments)}, "reviews": {"nodes": list(reviews)}}


def comment(author="octocat", minute=0, text="hi", number=81):
    return PullRequestComment(number, "a/b", author, text, at(minute), "https://c")


# MARK: - parse_comments


def test_reads_conversation_comments_with_their_pull_request():
    reading = parse_comments(answer(pull(comments=[node(body="Can you rebase?", minute=5)])))

    assert reading == CommentReading(
        viewer="me",
        comments=(PullRequestComment(81, "a/b", "octocat", "Can you rebase?", at(5), "https://c"),),
    )
    assert reading.comments[0].reference == "#81"


def test_review_summaries_and_inline_review_comments_count_too():
    review = node(author="reviewer", body="Two nits", minute=7, time_key="submittedAt")
    review["comments"] = {"nodes": [node(author="reviewer", body="Rename this", minute=6)]}

    reading = parse_comments(answer(pull(reviews=[review])))

    assert [c.text for c in reading.comments] == ["Two nits", "Rename this"]


def test_a_review_with_no_text_is_not_a_comment():
    # Approving without a word leaves an empty body; there is nothing to show.
    reading = parse_comments(answer(pull(reviews=[node(body="", time_key="submittedAt")])))

    assert reading.comments == ()


@pytest.mark.parametrize(
    "broken",
    [
        node(author=None),  # a deleted account
        node(body=None),
        node(body="<!-- only metadata -->"),
        {**node(), "createdAt": "yesterday"},
        {**node(), "url": None},
    ],
)
def test_a_comment_the_bubble_could_not_show_is_skipped(broken):
    reading = parse_comments(answer(pull(comments=[broken, node(body="kept")])))

    assert [c.text for c in reading.comments] == ["kept"]


def test_a_node_that_is_not_a_pull_request_is_skipped():
    reading = parse_comments(answer({}, None, pull(comments=[node()])))

    assert len(reading.comments) == 1


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"errors": [{"message": "x"}]}'])
def test_an_answer_without_data_is_a_failure(text):
    with pytest.raises(ParseError):
        parse_comments(text)


# MARK: - excerpt


@pytest.mark.parametrize(
    "markdown, expected",
    [
        ("Plain text", "Plain text"),
        ("<!-- BUGBOT_REVIEW -->\n✅ Reviewed", "✅ Reviewed"),
        ("See [the docs](https://x.dev) first", "See the docs first"),
        ("![screenshot](https://x.png) Fixed", "Fixed"),
        ("**Bold** and `code` and ~~gone~~", "Bold and code and gone"),
        ("_Comment `@cursor review` to rerun_", "Comment @cursor review to rerun"),
        ("keep snake_case_names", "keep snake_case_names"),
        ("### Heading\n> quoted\n- item\n- [x] done\n1. first", "Heading quoted item done first"),
        ("```python\nprint(1)\n```", "print(1)"),
        ("<sup>Reviewed by <b>Bugbot</b></sup>", "Reviewed by Bugbot"),
        ("  lots\n\n of   space  ", "lots of space"),
    ],
)
def test_excerpt_reduces_markdown_to_plain_text(markdown, expected):
    assert excerpt(markdown) == expected


# MARK: - CommentWatch


def test_the_first_reading_announces_its_newest_comment():
    reading = CommentReading("me", (comment(minute=1, text="old"), comment(minute=9, text="new")))

    assert CommentWatch().announce(reading).text == "new"


def test_a_comment_already_announced_is_not_announced_again():
    watch = CommentWatch()
    reading = CommentReading("me", (comment(minute=1),))
    watch.announce(reading)

    assert watch.announce(reading) is None


def test_a_newer_comment_is_announced():
    watch = CommentWatch()
    watch.announce(CommentReading("me", (comment(minute=1),)))

    reading = CommentReading("me", (comment(minute=1), comment(minute=4, text="new")))

    announced = watch.announce(reading)

    assert announced.text == "new"


def test_an_older_comment_on_a_pull_request_that_just_appeared_is_not_news():
    watch = CommentWatch()
    watch.announce(CommentReading("me", (comment(minute=5),)))

    reading = CommentReading("me", (comment(minute=5), comment(minute=2, number=7)))

    assert watch.announce(reading) is None


def test_your_own_comments_are_never_news():
    others, mine = comment(author="other", minute=1), comment(author="me", minute=9)
    reading = CommentReading("Me", (others, mine))

    assert CommentWatch().announce(reading).author == "other"


def test_nothing_to_announce_when_there_are_no_comments():
    assert CommentWatch().announce(CommentReading("me", ())) is None


# MARK: - CommentReading.latest_on


def test_the_latest_comment_on_a_pull_request_is_its_newest_from_anyone():
    reading = CommentReading("me", (
        comment(minute=1, text="old"),
        comment(author="me", minute=8, text="mine"),
        comment(minute=9, text="other pull", number=7),
    ))

    assert reading.latest_on(81, "a/b").text == "mine"


def test_a_pull_request_without_comments_has_no_latest_comment():
    reading = CommentReading("me", (comment(number=7),))

    assert reading.latest_on(81, "a/b") is None
    assert reading.latest_on(7, "c/d") is None
