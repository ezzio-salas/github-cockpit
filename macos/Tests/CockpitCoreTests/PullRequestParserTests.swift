import XCTest
@testable import CockpitCore

final class PullRequestParserTests: XCTestCase {
    /// One real row, as `gh search prs --json number,title,repository,url,isDraft,updatedAt` writes it.
    private static let sample = """
    [
      {"isDraft": false, "number": 44,
       "repository": {"name": "material-tailwind", "nameWithOwner": "ezzio-salas/material-tailwind"},
       "title": "[Snyk] Security upgrade next from 10.2.3 to 15.5.10",
       "updatedAt": "2026-02-01T12:05:49Z",
       "url": "https://github.com/ezzio-salas/material-tailwind/pull/44"}
    ]
    """

    /// 2026-02-01T12:05:49Z.
    private static let sampleUpdate = Date(timeIntervalSince1970: 1_769_947_549)

    private func row(_ extra: String) -> String {
        #"[{"number": 1, "title": "t", "repository": {"nameWithOwner": "a/b"}, "url": "https://u"\#(extra)}]"#
    }

    func testReadsTheFieldsTheCardShows() throws {
        let pulls = try PullRequestParser.parse(Self.sample)

        XCTAssertEqual(pulls, [PullRequest(
            number: 44,
            title: "[Snyk] Security upgrade next from 10.2.3 to 15.5.10",
            repo: "ezzio-salas/material-tailwind",
            url: URL(string: "https://github.com/ezzio-salas/material-tailwind/pull/44")!,
            isDraft: false,
            updatedAt: Self.sampleUpdate
        )])
        XCTAssertEqual(pulls.first?.reference, "#44")
    }

    func testAnEmptyResultIsAnEmptyListNotAFailure() throws {
        // Nobody has asked for a review: a normal state, not an error.
        XCTAssertEqual(try PullRequestParser.parse("[]"), [])
    }

    func testTitlesAreTrimmed() throws {
        let pulls = try PullRequestParser.parse(
            #"[{"number": 1, "title": "  Fix it  ", "repository": {"nameWithOwner": "a/b"}, "url": "https://u"}]"#
        )

        XCTAssertEqual(pulls.first?.title, "Fix it")
    }

    func testDraftsAreMarked() throws {
        XCTAssertEqual(try PullRequestParser.parse(row(#", "isDraft": true"#)).first?.isDraft, true)
    }

    func testARowTheCardCouldNotDrawIsSkippedNotGuessedAt() throws {
        let unusable = [
            #"{"title": "t", "repository": {"nameWithOwner": "a/b"}, "url": "u"}"#, // no number
            #"{"number": 1, "repository": {"nameWithOwner": "a/b"}, "url": "u"}"#, // no title
            #"{"number": 1, "title": "   ", "repository": {"nameWithOwner": "a/b"}, "url": "u"}"#, // blank title
            #"{"number": 1, "title": "t", "url": "u"}"#, // no repository
            #"{"number": 1, "title": "t", "repository": {}, "url": "u"}"#, // no nameWithOwner
            #"{"number": 1, "title": "t", "repository": {"nameWithOwner": "a/b"}}"#, // no url
            #"{"number": true, "title": "t", "repository": {"nameWithOwner": "a/b"}, "url": "u"}"#, // not a number
            #"{"number": 1.5, "title": "t", "repository": {"nameWithOwner": "a/b"}, "url": "u"}"#, // not whole
            #""not an object""#,
        ]
        for row in unusable {
            XCTAssertEqual(try PullRequestParser.parse("[\(row)]"), [], row)
        }
    }

    func testOneUnusableRowDoesNotCostTheOthers() throws {
        let pulls = try PullRequestParser.parse(
            #"[{"number": 1, "title": "t", "repository": {"nameWithOwner": "a/b"}, "url": "u"}, {"title": "no number"}]"#
        )

        XCTAssertEqual(pulls.map(\.number), [1])
    }

    func testATimestampWithoutAZoneIsReadAsUTC() throws {
        let pulls = try PullRequestParser.parse(row(#", "updatedAt": "2026-02-01T12:05:49""#))

        XCTAssertEqual(pulls.first?.updatedAt, Self.sampleUpdate)
    }

    func testATimestampWithFractionalSecondsIsRead() throws {
        let pulls = try PullRequestParser.parse(row(#", "updatedAt": "2026-02-01T12:05:49.000Z""#))

        XCTAssertEqual(pulls.first?.updatedAt, Self.sampleUpdate)
    }

    func testAnUnreadableTimestampLeavesTheAgeBlankRatherThanFailing() throws {
        for value in [#""yesterday""#, "null", "17", #""""#] {
            let pulls = try PullRequestParser.parse(row(#", "updatedAt": \#(value)"#))

            XCTAssertEqual(pulls.count, 1, value)
            XCTAssertNil(pulls.first?.updatedAt, value)
        }
    }

    func testAnythingThatIsNotAJSONArrayIsAFailure() {
        // The card has to tell these apart from "no pull requests", so they throw.
        XCTAssertThrowsError(try PullRequestParser.parse("")) {
            XCTAssertEqual($0 as? PullRequestParser.ParseError, .notJSON)
        }
        XCTAssertThrowsError(try PullRequestParser.parse("not json")) {
            XCTAssertEqual($0 as? PullRequestParser.ParseError, .notJSON)
        }
        for text in ["{}", #""a string""#, "null"] {
            XCTAssertThrowsError(try PullRequestParser.parse(text), text) {
                XCTAssertEqual($0 as? PullRequestParser.ParseError, .notAnArray)
            }
        }
    }
}
