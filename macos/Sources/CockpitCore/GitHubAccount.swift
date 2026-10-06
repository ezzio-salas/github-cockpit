import Foundation

/// One account the GitHub CLI is signed in to.
public struct GitHubAccount: Equatable, Sendable {
    public let login: String
    /// Whether `gh` itself uses this account when none is named.
    public let isActive: Bool

    public init(login: String, isActive: Bool) {
        self.login = login
        self.isActive = isActive
    }
}

/// Turns `gh auth status --json hosts` answers into accounts.
public enum AccountParser {
    /// The only host the card reads; an enterprise host's accounts are not offered.
    public static let host = "github.com"

    /// The github.com accounts in `gh`'s order. An unreadable answer gives none rather than throwing: the list only
    /// feeds a menu, and the card works without it.
    public static func parse(_ raw: String) -> [GitHubAccount] {
        guard let object = try? JSONSerialization.jsonObject(with: Data(raw.utf8)),
              let hosts = (object as? [String: Any])?["hosts"] as? [String: Any],
              let entries = hosts[host] as? [[String: Any]]
        else { return [] }
        return entries.compactMap { entry in
            guard let login = entry["login"] as? String, !login.isEmpty else { return nil }
            return GitHubAccount(login: login, isActive: entry["active"] as? Bool == true)
        }
    }
}
