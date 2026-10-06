import Foundation

/// Runs `gh search prs` for the two lists the card shows, the way the CLI is already signed in.
///
/// Only the most recently updated few are asked for, because the card is a glance, not a queue.
///
/// With an `account`, each call runs as that account without switching the one `gh` has active, which terminals
/// keep using: its token is read from the keyring for that call and handed only to that one process, never stored
/// or logged.
public struct PullRequestFetcher: Sendable {
    public enum FetchError: Error, Equatable {
        case cliNotFound
        case timedOut
        case notAuthenticated(String)
        /// Signed in, but an organization refuses the account, such as for SAML SSO.
        case noAccess(String)
        case launchFailed(String)
        case failed(exitCode: Int32, output: String)
    }

    /// Only what the card draws, so the reply stays small.
    private static let fields = "id,number,title,repository,url,isDraft,updatedAt"

    private static let installDirectories = [
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin"),
        URL(fileURLWithPath: "/opt/homebrew/bin"),
        URL(fileURLWithPath: "/usr/local/bin"),
    ]

    /// Each would override the account `gh` was asked for, or the one it has active, unseen.
    private static let tokenVariables: Set = ["GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"]

    private static var environment: [String: String] {
        ProcessInfo.processInfo.environment
            .filter { !tokenVariables.contains($0.key) }
            // A pager or a colored answer would both corrupt the JSON.
            .merging(["GH_PAGER": "cat", "NO_COLOR": "1", "CLICOLOR": "0"], uniquingKeysWith: { $1 })
    }

    private let command: String
    /// The account every call runs as, or nil for the one `gh` has active.
    public let account: String?
    private let timeout: TimeInterval
    private let limit: Int

    /// - Parameter command: The CLI to run: a command name such as `gh`, or a path to an executable.
    ///   It is resolved on each fetch, so a CLI installed while the app runs is picked up.
    public init(command: String = "gh", account: String? = nil, timeout: TimeInterval = 20, limit: Int = 5) {
        self.command = command
        self.account = account
        self.timeout = timeout
        self.limit = limit
    }

    /// Raw JSON for the github.com accounts `gh` is signed in to; no token is asked for.
    public func fetchAccounts() async -> Result<String, FetchError> {
        await run(["auth", "status", "--json", "hosts", "--hostname", AccountParser.host], asAccount: false)
    }

    /// Raw JSON for the open pull requests the signed-in user opened.
    public func fetchMine() async -> Result<String, FetchError> {
        await search("--author=@me")
    }

    /// Raw JSON for the open pull requests waiting on the signed-in user's review.
    public func fetchReviewRequested() async -> Result<String, FetchError> {
        await search("--review-requested=@me")
    }

    /// Raw GraphQL JSON for the latest comments on the given pull requests.
    public func fetchComments(nodeIDs: [String]) async -> Result<String, FetchError> {
        await run(["api", "graphql", "-f", "query=\(CommentParser.query)"] + nodeIDs.flatMap { ["-f", "ids[]=\($0)"] })
    }

    private func search(_ who: String) async -> Result<String, FetchError> {
        await run([
            "search", "prs", who, "--state=open", "--limit=\(limit)", "--json=\(Self.fields)", "--sort=updated",
        ])
    }

    private func run(_ arguments: [String], asAccount: Bool = true) async -> Result<String, FetchError> {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .utility).async {
                guard let cli = Self.resolve(command, searchDirectories: Self.installDirectories) else {
                    continuation.resume(returning: .failure(.cliNotFound))
                    return
                }
                var environment = Self.environment
                if asAccount, let account {
                    switch token(for: account, cli: cli, environment: environment) {
                    case .success(let token): environment["GH_TOKEN"] = token
                    case .failure(let error):
                        continuation.resume(returning: .failure(error))
                        return
                    }
                }
                continuation.resume(
                    returning: Self.run(cli, arguments: arguments, environment: environment, timeout: timeout)
                )
            }
        }
    }

    /// The keyring's token for `account`; any failure to read it means the card cannot read as that account.
    private func token(for account: String, cli: URL, environment: [String: String]) -> Result<String, FetchError> {
        let arguments = ["auth", "token", "--hostname", AccountParser.host, "--user", account]
        switch Self.run(cli, arguments: arguments, environment: environment, timeout: timeout) {
        case .success(let output):
            let token = output.trimmingCharacters(in: .whitespacesAndNewlines)
            return token.isEmpty ? .failure(.notAuthenticated("\(account): no token")) : .success(token)
        case .failure(.failed(_, let output)):
            return .failure(.notAuthenticated("\(account): \(output)"))
        case .failure(let error):
            return .failure(error)
        }
    }

    /// Finds the executable for `command`. A command containing `/` is taken as a path. A bare name is looked up
    /// in `searchDirectories` and then by a login shell, because apps launched from Finder do not inherit the
    /// shell `PATH`.
    static func resolve(_ command: String, searchDirectories: [URL]) -> URL? {
        func executable(at path: String) -> URL? {
            FileManager.default.isExecutableFile(atPath: path) ? URL(fileURLWithPath: path) : nil
        }

        if command.contains("/") {
            return executable(at: (command as NSString).expandingTildeInPath)
        }
        for directory in searchDirectories {
            if let installed = executable(at: directory.appendingPathComponent(command).path) {
                return installed
            }
        }

        let shell = URL(fileURLWithPath: "/bin/zsh")
        // The name travels as an argument, never as shell source.
        let lookup = run(
            shell, arguments: ["-lc", #"command -v -- "$1""#, "zsh", command], environment: environment, timeout: 5
        )
        guard case .success(let output) = lookup else { return nil }
        return executable(at: output.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private static func run(
        _ executable: URL, arguments: [String], environment: [String: String], timeout: TimeInterval
    ) -> Result<String, FetchError> {
        // Output goes to files rather than pipes, so waiting depends only on the process itself and never on a
        // descendant that still holds a pipe open. stderr is kept apart so it can never corrupt the JSON.
        let temporary = FileManager.default.temporaryDirectory
        let outputURL = temporary.appendingPathComponent("github-cockpit-\(UUID().uuidString).out")
        let errorURL = temporary.appendingPathComponent("github-cockpit-\(UUID().uuidString).err")
        defer {
            try? FileManager.default.removeItem(at: outputURL)
            try? FileManager.default.removeItem(at: errorURL)
        }

        let process = Process()
        let exited = DispatchSemaphore(value: 0)
        do {
            try Data().write(to: outputURL)
            try Data().write(to: errorURL)
            let output = try FileHandle(forWritingTo: outputURL)
            let errors = try FileHandle(forWritingTo: errorURL)
            defer {
                try? output.close()
                try? errors.close()
            }

            process.executableURL = executable
            process.arguments = arguments
            process.environment = environment
            process.currentDirectoryURL = temporary
            // A CLI that decides to prompt fails fast instead of hanging.
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = output
            process.standardError = errors
            process.terminationHandler = { _ in exited.signal() }
            try process.run()
        } catch {
            return .failure(.launchFailed(error.localizedDescription))
        }

        guard exited.wait(timeout: .now() + timeout) == .success else {
            // SIGKILL rather than SIGTERM: a CLI stuck in a system call never gets to act on a polite request.
            kill(process.processIdentifier, SIGKILL)
            process.waitUntilExit()
            return .failure(.timedOut)
        }

        let output = (try? String(contentsOf: outputURL, encoding: .utf8)) ?? ""
        guard process.terminationStatus == 0 else {
            let errors = (try? String(contentsOf: errorURL, encoding: .utf8)) ?? ""
            let message = (errors.isEmpty ? output : errors).trimmingCharacters(in: .whitespacesAndNewlines)
            if isAuthenticationFailure(message) {
                return .failure(.notAuthenticated(message))
            }
            if isAccessRefusal(message) {
                return .failure(.noAccess(message))
            }
            return .failure(.failed(exitCode: process.terminationStatus, output: message))
        }
        return .success(output)
    }

    private static let authenticationFailures = [
        "gh auth login", "authentication", "not logged", "no oauth token", "bad credentials", "401 unauthorized",
        "http 401",
    ]
    private static let accessRefusals = ["saml", "resource not accessible"]

    private static func isAuthenticationFailure(_ message: String) -> Bool {
        let lowered = message.lowercased()
        return authenticationFailures.contains { lowered.contains($0) }
    }

    private static func isAccessRefusal(_ message: String) -> Bool {
        let lowered = message.lowercased()
        return accessRefusals.contains { lowered.contains($0) }
    }
}
