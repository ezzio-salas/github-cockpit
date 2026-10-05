import Foundation

/// Runs `gh search prs` for the two lists the card shows, the way the CLI is already signed in.
///
/// Only the most recently updated few are asked for, because the card is a glance, not a queue.
public struct PullRequestFetcher: Sendable {
    public enum FetchError: Error, Equatable {
        case cliNotFound
        case timedOut
        case notAuthenticated(String)
        case launchFailed(String)
        case failed(exitCode: Int32, output: String)
    }

    /// Only what the card draws, so the reply stays small.
    private static let fields = "number,title,repository,url,isDraft,updatedAt"

    private static let installDirectories = [
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin"),
        URL(fileURLWithPath: "/opt/homebrew/bin"),
        URL(fileURLWithPath: "/usr/local/bin"),
    ]

    private let command: String
    private let timeout: TimeInterval
    private let limit: Int

    /// - Parameter command: The CLI to run: a command name such as `gh`, or a path to an executable.
    ///   It is resolved on each fetch, so a CLI installed while the app runs is picked up.
    public init(command: String = "gh", timeout: TimeInterval = 20, limit: Int = 5) {
        self.command = command
        self.timeout = timeout
        self.limit = limit
    }

    /// Raw JSON for the open pull requests the signed-in user opened.
    public func fetchMine() async -> Result<String, FetchError> {
        await search("--author=@me")
    }

    /// Raw JSON for the open pull requests waiting on the signed-in user's review.
    public func fetchReviewRequested() async -> Result<String, FetchError> {
        await search("--review-requested=@me")
    }

    private func search(_ who: String) async -> Result<String, FetchError> {
        let arguments = [
            "search", "prs", who, "--state=open", "--limit=\(limit)", "--json=\(Self.fields)", "--sort=updated",
        ]
        return await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .utility).async {
                guard let cli = Self.resolve(command, searchDirectories: Self.installDirectories) else {
                    continuation.resume(returning: .failure(.cliNotFound))
                    return
                }
                continuation.resume(returning: Self.run(cli, arguments: arguments, timeout: timeout))
            }
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
        let lookup = run(shell, arguments: ["-lc", #"command -v -- "$1""#, "zsh", command], timeout: 5)
        guard case .success(let output) = lookup else { return nil }
        return executable(at: output.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private static func run(_ executable: URL, arguments: [String], timeout: TimeInterval) -> Result<String, FetchError> {
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
            // A pager or a colored answer would both corrupt the JSON.
            process.environment = ProcessInfo.processInfo.environment.merging(
                ["GH_PAGER": "cat", "NO_COLOR": "1", "CLICOLOR": "0"], uniquingKeysWith: { $1 }
            )
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
            return .failure(.failed(exitCode: process.terminationStatus, output: message))
        }
        return .success(output)
    }

    private static func isAuthenticationFailure(_ message: String) -> Bool {
        let lowered = message.lowercased()
        return ["gh auth login", "authentication", "not logged"].contains { lowered.contains($0) }
    }
}
