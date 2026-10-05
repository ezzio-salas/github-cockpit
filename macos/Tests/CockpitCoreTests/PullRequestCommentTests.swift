import XCTest
@testable import CockpitCore

private let noon = Date(timeIntervalSince1970: 1_791_201_600)

private func at(minute: Int) -> Date {
    noon.addingTimeInterval(TimeInterval(minute * 60))
}

private func node(
    author: String? = "octocat", body: String? = "Looks good", minute: Int = 0, timeKey: String = "createdAt"
) -> [String: Any] {
    var node: [String: Any] = [timeKey: ISO8601DateFormatter().string(from: at(minute: minute)), "url": "https://c"]
    node["author"] = author.map { ["login": $0] } ?? NSNull()
    node["body"] = body ?? NSNull()
    return node
}

private func pull(comments: [[String: Any]] = [], reviews: [[String: Any]] = []) -> [String: Any] {
    ["number": 81, "repository": ["nameWithOwner": "a/b"], "comments": ["nodes": comments], "reviews": ["nodes": reviews]]
}

private func answer(_ nodes: [Any], viewer: String = "me") throws -> String {
    let object: [String: Any] = ["data": ["viewer": ["login": viewer], "nodes": nodes]]
    return String(decoding: try JSONSerialization.data(withJSONObject: object), as: UTF8.self)
}

private func comment(author: String = "octocat", minute: Int = 0, text: String = "hi", number: Int = 81) -> PullRequestComment {
    PullRequestComment(
        number: number, repo: "a/b", author: author, text: text, createdAt: at(minute: minute), url: URL(string: "https://c")!
    )
}

final class CommentParserTests: XCTestCase {
    func testReadsConversationCommentsWithTheirPullRequest() throws {
        let reading = try CommentParser.parse(answer([pull(comments: [node(body: "Can you rebase?", minute: 5)])]))

        XCTAssertEqual(reading, CommentReading(viewer: "me", comments: [comment(minute: 5, text: "Can you rebase?")]))
        XCTAssertEqual(reading.comments.first?.reference, "#81")
    }

    func testReviewSummariesAndInlineReviewCommentsCountToo() throws {
        var review = node(author: "reviewer", body: "Two nits", minute: 7, timeKey: "submittedAt")
        review["comments"] = ["nodes": [node(author: "reviewer", body: "Rename this", minute: 6)]]

        let reading = try CommentParser.parse(answer([pull(reviews: [review])]))

        XCTAssertEqual(reading.comments.map(\.text), ["Two nits", "Rename this"])
    }

    func testAReviewWithNoTextIsNotAComment() throws {
        // Approving without a word leaves an empty body; there is nothing to show.
        let reading = try CommentParser.parse(answer([pull(reviews: [node(body: "", timeKey: "submittedAt")])]))

        XCTAssertEqual(reading.comments, [])
    }

    func testACommentTheBubbleCouldNotShowIsSkipped() throws {
        var badTime = node()
        badTime["createdAt"] = "yesterday"
        var noURL = node()
        noURL["url"] = NSNull()
        let broken = [node(author: nil), node(body: nil), node(body: "<!-- only metadata -->"), badTime, noURL]

        for row in broken {
            let reading = try CommentParser.parse(answer([pull(comments: [row, node(body: "kept")])]))

            XCTAssertEqual(reading.comments.map(\.text), ["kept"], "\(row)")
        }
    }

    func testANodeThatIsNotAPullRequestIsSkipped() throws {
        let reading = try CommentParser.parse(answer([[String: Any](), NSNull(), pull(comments: [node()])]))

        XCTAssertEqual(reading.comments.count, 1)
    }

    func testAnAnswerWithoutDataIsAFailure() {
        for text in ["", "not json", "[]", #"{"errors": [{"message": "x"}]}"#] {
            XCTAssertThrowsError(try CommentParser.parse(text), text)
        }
    }

    func testExcerptReducesMarkdownToPlainText() {
        let expected = [
            ("Plain text", "Plain text"),
            ("<!-- BUGBOT_REVIEW\nid: 1 -->\n✅ Reviewed", "✅ Reviewed"),
            ("See [the docs](https://x.dev) first", "See the docs first"),
            ("![screenshot](https://x.png) Fixed", "Fixed"),
            ("**Bold** and `code` and ~~gone~~", "Bold and code and gone"),
            ("_Comment `@cursor review` to rerun_", "Comment @cursor review to rerun"),
            ("keep snake_case_names", "keep snake_case_names"),
            ("### Heading\n> quoted\n- item\n- [x] done\n1. first", "Heading quoted item done first"),
            ("```python\nprint(1)\n```", "print(1)"),
            ("<sup>Reviewed by <b>Bugbot</b></sup>", "Reviewed by Bugbot"),
            ("  lots\n\n of   space  ", "lots of space"),
        ]
        for (markdown, text) in expected {
            XCTAssertEqual(CommentParser.excerpt(markdown), text, markdown)
        }
    }
}

final class CommentWatchTests: XCTestCase {
    func testTheFirstReadingAnnouncesItsNewestComment() {
        var watch = CommentWatch()
        let reading = CommentReading(viewer: "me", comments: [comment(minute: 1, text: "old"), comment(minute: 9, text: "new")])

        XCTAssertEqual(watch.announce(reading)?.text, "new")
    }

    func testACommentAlreadyAnnouncedIsNotAnnouncedAgain() {
        var watch = CommentWatch()
        let reading = CommentReading(viewer: "me", comments: [comment(minute: 1)])
        _ = watch.announce(reading)

        XCTAssertNil(watch.announce(reading))
    }

    func testANewerCommentIsAnnounced() {
        var watch = CommentWatch()
        _ = watch.announce(CommentReading(viewer: "me", comments: [comment(minute: 1)]))

        let announced = watch.announce(CommentReading(
            viewer: "me", comments: [comment(minute: 1), comment(minute: 4, text: "new")]
        ))

        XCTAssertEqual(announced?.text, "new")
    }

    func testAnOlderCommentOnAPullRequestThatJustAppearedIsNotNews() {
        var watch = CommentWatch()
        _ = watch.announce(CommentReading(viewer: "me", comments: [comment(minute: 5)]))

        XCTAssertNil(watch.announce(CommentReading(
            viewer: "me", comments: [comment(minute: 5), comment(minute: 2, number: 7)]
        )))
    }

    func testYourOwnCommentsAreNeverNews() {
        var watch = CommentWatch()
        let reading = CommentReading(viewer: "Me", comments: [comment(author: "other", minute: 1), comment(author: "me", minute: 9)])

        XCTAssertEqual(watch.announce(reading)?.author, "other")
    }

    func testNothingToAnnounceWhenThereAreNoComments() {
        var watch = CommentWatch()

        XCTAssertNil(watch.announce(CommentReading(viewer: "me", comments: [])))
    }
}
