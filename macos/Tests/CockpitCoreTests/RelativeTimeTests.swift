import XCTest
@testable import CockpitCore

final class RelativeTimeTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_791_201_600)

    func testCompactUsesTheLongestUnitThatIsAtLeastOne() {
        let expected: [(TimeInterval, String)] = [
            (0, "0s"), (59, "59s"), (60, "1m"), (119, "1m"), (3599, "59m"),
            (3600, "1h"), (86_399, "23h"), (86_400, "1d"), (200_000, "2d"),
        ]
        for (seconds, text) in expected {
            XCTAssertEqual(RelativeTime.compact(seconds), text, "\(seconds)s")
        }
    }

    func testCompactNeverShowsANegativeDuration() {
        XCTAssertEqual(RelativeTime.compact(-5), "0s")
    }

    func testAgeReadsAsTimeSinceThePullRequestChanged() {
        let expected: [(TimeInterval, String)] = [
            (0, "JUST NOW"), (59, "JUST NOW"), (5 * 60, "5M AGO"), (3 * 3600, "3H AGO"), (2 * 86_400, "2D AGO"),
        ]
        for (seconds, text) in expected {
            XCTAssertEqual(RelativeTime.age(of: now.addingTimeInterval(-seconds), now: now), text, "\(seconds)s")
        }
    }

    func testAPullRequestWithNoTimestampShowsNoAge() {
        XCTAssertEqual(RelativeTime.age(of: nil, now: now), "")
    }

    func testAClockSlightlyAheadReadsAsJustNowRatherThanANegativeAge() {
        XCTAssertEqual(RelativeTime.age(of: now.addingTimeInterval(120), now: now), "JUST NOW")
    }
}
