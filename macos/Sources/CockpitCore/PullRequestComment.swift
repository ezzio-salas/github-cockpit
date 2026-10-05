import Foundation

/// One comment, already reduced to the plain text the bubble shows.
public struct PullRequestComment: Equatable, Sendable {
    public let number: Int
    public let repo: String
    public let author: String
    public let text: String
    public let createdAt: Date
    public let url: URL

    public init(number: Int, repo: String, author: String, text: String, createdAt: Date, url: URL) {
        self.number = number
        self.repo = repo
        self.author = author
        self.text = text
        self.createdAt = createdAt
        self.url = url
    }

    public var reference: String {
        "#\(number)"
    }
}

/// Who is signed in, and the recent comments on the card's pull requests.
public struct CommentReading: Equatable, Sendable {
    public let viewer: String
    public let comments: [PullRequestComment]

    public init(viewer: String, comments: [PullRequestComment]) {
        self.viewer = viewer
        self.comments = comments
    }
}

/// Reads the answer to `query`, and reduces comment bodies to plain text.
public enum CommentParser {
    /// One GraphQL request for every pull request on the card. Conversation comments, review summaries and
    /// inline review comments all count; only the last few of each are asked for, because only the newest
    /// one is ever shown.
    public static let query = """
    query($ids: [ID!]!) {
      viewer { login }
      nodes(ids: $ids) {
        ... on PullRequest {
          number
          repository { nameWithOwner }
          comments(last: 3) { nodes { author { login } body createdAt url } }
          reviews(last: 3) {
            nodes {
              author { login } body submittedAt url
              comments(last: 1) { nodes { author { login } body createdAt url } }
            }
          }
        }
      }
    }
    """

    /// A comment missing its author, time, url or any readable text is skipped, as a pull request row is.
    /// An answer without `data` throws.
    public static func parse(_ text: String) throws -> CommentReading {
        let decoded: Any
        do {
            decoded = try JSONSerialization.jsonObject(with: Data(text.utf8), options: .fragmentsAllowed)
        } catch {
            throw PullRequestParser.ParseError.notJSON
        }
        guard let data = (decoded as? [String: Any])?["data"] as? [String: Any] else {
            throw PullRequestParser.ParseError.noData
        }

        var comments: [PullRequestComment] = []
        for pull in objects(data["nodes"]) {
            guard let number = PullRequestParser.integer(pull["number"]),
                  let repo = (pull["repository"] as? [String: Any])?["nameWithOwner"] as? String
            else { continue }
            for (node, timeKey) in commentNodes(of: pull) {
                if let comment = comment(node, timeKey: timeKey, number: number, repo: repo) {
                    comments.append(comment)
                }
            }
        }
        let viewer = (data["viewer"] as? [String: Any])?["login"] as? String ?? ""
        return CommentReading(viewer: viewer, comments: comments)
    }

    private static func commentNodes(of pull: [String: Any]) -> [([String: Any], String)] {
        var found = nodes(pull["comments"]).map { ($0, "createdAt") }
        for review in nodes(pull["reviews"]) {
            found.append((review, "submittedAt"))
            found += nodes(review["comments"]).map { ($0, "createdAt") }
        }
        return found
    }

    private static func comment(_ node: [String: Any], timeKey: String, number: Int, repo: String) -> PullRequestComment? {
        guard let author = (node["author"] as? [String: Any])?["login"] as? String,
              let text = (node["body"] as? String).map(excerpt), !text.isEmpty,
              let createdAt = (node[timeKey] as? String).flatMap(PullRequestParser.timestamp),
              let url = (node["url"] as? String).flatMap(URL.init(string:))
        else { return nil }
        return PullRequestComment(number: number, repo: repo, author: author, text: text, createdAt: createdAt, url: url)
    }

    private static func nodes(_ connection: Any?) -> [[String: Any]] {
        objects((connection as? [String: Any])?["nodes"])
    }

    private static func objects(_ value: Any?) -> [[String: Any]] {
        (value as? [Any])?.compactMap { $0 as? [String: Any] } ?? []
    }

    /// Each pattern and what it becomes, applied in order.
    private static let cleanup: [(NSRegularExpression, String)] = [
        (#"(?s)<!--.*?-->"#, " "),
        (#"(?m)^\s*```.*$"#, " "),
        (#"!\[[^\]]*\]\([^)]*\)"#, " "),
        (#"\[([^\]]*)\]\([^)]*\)"#, "$1"),
        (#"<[^>]+>"#, " "),
        (#"(?m)^\s*(?:#{1,6}\s+|>\s?|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+\.\s+)"#, ""),
        (#"\*\*|__|~~|`|(?<!\w)[*_]|[*_](?!\w)"#, ""),
        (#"\s+"#, " "),
    ].map { pattern, template in
        // The patterns are constants, so a failure here is a programming error caught by the tests.
        (try! NSRegularExpression(pattern: pattern), template)
    }

    /// Markdown and HTML reduced to one line of plain text, for a bubble a few lines tall.
    ///
    /// Bots hide metadata in HTML comments and wrap footers in tags, so both go; a link keeps its words and
    /// loses its address; emphasis markers go but a snake_case name keeps its underscores.
    public static func excerpt(_ markdown: String) -> String {
        cleanup.reduce(markdown) { text, rule in
            rule.0.stringByReplacingMatches(
                in: text, range: NSRange(text.startIndex..., in: text), withTemplate: rule.1
            )
        }
        .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

/// Decides which comment, if any, is news worth a bubble.
///
/// The first reading announces its newest comment, so a launch shows where things stand. After that only a
/// comment newer than every one already seen is announced. The signed-in person's own comments are never news
/// to them.
public struct CommentWatch {
    private var latestSeen: Date?

    public init() {}

    public mutating func announce(_ reading: CommentReading) -> PullRequestComment? {
        let viewer = reading.viewer.lowercased()
        guard let newest = reading.comments
            .filter({ $0.author.lowercased() != viewer })
            .max(by: { $0.createdAt < $1.createdAt })
        else { return nil }

        if let latestSeen, newest.createdAt <= latestSeen { return nil }
        latestSeen = newest.createdAt
        return newest
    }
}
