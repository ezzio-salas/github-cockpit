import Foundation

/// A single open pull request, as the widget shows it.
public struct PullRequest: Equatable, Sendable {
    public let number: Int
    public let title: String
    /// `owner/name`, shown on the line under the title.
    public let repo: String
    public let url: URL
    public let isDraft: Bool
    /// When it last changed, or nil when `gh` did not report it.
    public let updatedAt: Date?
    /// GitHub's GraphQL id, which the latest comments are asked for by; nil when not reported.
    public let nodeID: String?

    public init(
        number: Int, title: String, repo: String, url: URL, isDraft: Bool, updatedAt: Date?, nodeID: String? = nil
    ) {
        self.number = number
        self.title = title
        self.repo = repo
        self.url = url
        self.isDraft = isDraft
        self.updatedAt = updatedAt
        self.nodeID = nodeID
    }

    /// `#412`, the short form shown beside the title.
    public var reference: String {
        "#\(number)"
    }
}

/// Turns `gh search prs --json ...` answers into pull requests.
public enum PullRequestParser {
    /// `gh` answered, but not with a list of pull requests.
    public enum ParseError: Error, Equatable {
        case notJSON
        case notAnArray
        /// A GraphQL answer that carries no `data`, such as one reporting only errors.
        case noData
    }

    /// Rows missing a number, title, repo or url are skipped rather than guessed at, so a change in `gh`'s
    /// output costs at most a row. A reply that is not a JSON array throws, because the card has to tell
    /// "nothing to show" apart from "could not read".
    public static func parse(_ text: String) throws -> [PullRequest] {
        let decoded: Any
        do {
            decoded = try JSONSerialization.jsonObject(with: Data(text.utf8), options: .fragmentsAllowed)
        } catch {
            throw ParseError.notJSON
        }
        guard let rows = decoded as? [Any] else { throw ParseError.notAnArray }
        return rows.compactMap { ($0 as? [String: Any]).flatMap(pullRequest) }
    }

    private static func pullRequest(_ row: [String: Any]) -> PullRequest? {
        guard let number = integer(row["number"]),
              let title = (row["title"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !title.isEmpty,
              let repo = (row["repository"] as? [String: Any])?["nameWithOwner"] as? String,
              !repo.isEmpty,
              let url = (row["url"] as? String).flatMap(URL.init(string:))
        else { return nil }

        return PullRequest(
            number: number,
            title: title,
            repo: repo,
            url: url,
            isDraft: row["isDraft"] as? Bool ?? false,
            updatedAt: (row["updatedAt"] as? String).flatMap(timestamp),
            nodeID: (row["id"] as? String).flatMap { $0.isEmpty ? nil : $0 }
        )
    }

    /// A whole JSON number. Foundation hands booleans and fractions back as numbers too, so both are refused here.
    static func integer(_ value: Any?) -> Int? {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID(),
              !CFNumberIsFloatType(number)
        else { return nil }
        return number.intValue
    }

    private static let zoned: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static let zonedWithFraction: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    /// Read as UTC, the zone GitHub reports in.
    private static let unzoned: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate, .withFullTime, .withColonSeparatorInTime]
        formatter.formatOptions.remove(.withTimeZone)
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    /// Reads GitHub's `2026-02-01T12:05:49Z`; anything else becomes nil, which leaves the age blank.
    static func timestamp(_ text: String) -> Date? {
        zoned.date(from: text) ?? zonedWithFraction.date(from: text) ?? unzoned.date(from: text)
    }
}
