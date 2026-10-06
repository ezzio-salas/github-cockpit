import XCTest
@testable import CockpitCore

final class PullRequestFetcherTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try FileManager.default.removeItem(at: directory)
    }

    /// Writes an executable shell script standing in for the `gh` CLI, so no test reaches the network.
    private func fakeCLI(_ body: String, named name: String = "gh") throws -> URL {
        let url = directory.appendingPathComponent(name)
        try "#!/bin/sh\n\(body)\n".write(to: url, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
        return url
    }

    func testReturnsWhatTheCLIWrote() async throws {
        let cli = try fakeCLI("echo '[]'")

        let result = await PullRequestFetcher(command: cli.path).fetchMine()

        XCTAssertEqual(result, .success("[]\n"))
    }

    func testAsksForThePullRequestsTheUserOpened() async throws {
        let cli = try fakeCLI(#"printf '[%s]' "$@""#)

        let result = await PullRequestFetcher(command: cli.path, limit: 3).fetchMine()

        XCTAssertEqual(result, .success(
            "[search][prs][--author=@me][--state=open][--limit=3]"
                + "[--json=id,number,title,repository,url,isDraft,updatedAt][--sort=updated]"
        ))
    }

    func testAsksForTheLatestCommentsOnTheGivenPullRequests() async throws {
        let cli = try fakeCLI(#"shift 4; printf '[%s]' "$@""#)

        let result = await PullRequestFetcher(command: cli.path).fetchComments(nodeIDs: ["PR_a", "PR_b"])

        XCTAssertEqual(result, .success("[-f][ids[]=PR_a][-f][ids[]=PR_b]"))
    }

    func testTheCommentQueryIsSentAsAGraphQLRequest() async throws {
        let cli = try fakeCLI(#"printf '%s %s %s %s' "$1" "$2" "$3" "$(printf '%s' "$4" | head -c 6)""#)

        let result = await PullRequestFetcher(command: cli.path).fetchComments(nodeIDs: ["PR_a"])

        XCTAssertEqual(result, .success("api graphql -f query="))
    }

    func testAsksForThePullRequestsWaitingOnTheUsersReview() async throws {
        let cli = try fakeCLI(#"printf '%s' "$3""#)

        let result = await PullRequestFetcher(command: cli.path).fetchReviewRequested()

        XCTAssertEqual(result, .success("--review-requested=@me"))
    }

    func testThePagerAndColorAreDisabledSoTheyCannotCorruptTheJSON() async throws {
        let cli = try fakeCLI(#"printf '%s %s %s' "$GH_PAGER" "$NO_COLOR" "$CLICOLOR""#)

        let result = await PullRequestFetcher(command: cli.path).fetchMine()

        XCTAssertEqual(result, .success("cat 1 0"))
    }

    func testErrorOutputNeverReachesTheJSON() async throws {
        let cli = try fakeCLI("echo 'warning: something' >&2\necho '[]'")

        let result = await PullRequestFetcher(command: cli.path).fetchMine()

        XCTAssertEqual(result, .success("[]\n"))
    }

    func testBeingSignedOutIsToldApartFromOtherFailures() async throws {
        let cli = try fakeCLI("echo 'To get started with GitHub CLI, please run:  gh auth login' >&2\nexit 4")

        let result = await PullRequestFetcher(command: cli.path).fetchMine()

        XCTAssertEqual(result, .failure(.notAuthenticated("To get started with GitHub CLI, please run:  gh auth login")))
    }

    func testAnyOtherNonZeroExitIsAPlainFailure() async throws {
        let cli = try fakeCLI("echo 'could not connect' >&2\nexit 1")

        let result = await PullRequestFetcher(command: cli.path).fetchMine()

        XCTAssertEqual(result, .failure(.failed(exitCode: 1, output: "could not connect")))
    }

    /// Answers `gh auth token` with a token naming the account, and anything else with the GH_TOKEN it was given,
    /// so a test sees which account a call ran as.
    private static let tokenByAccount = #"""
    if [ "$1 $2" = "auth token" ]; then
      [ "$6" = "signed-out" ] && { echo "no oauth token found for github.com account $6" >&2; exit 1; }
      echo "token-for-$6:$3=$4"
      exit 0
    fi
    printf '%s' "${GH_TOKEN-unset}"
    """#

    func testAChosenAccountRunsWithThatAccountsTokenFromTheKeyring() async throws {
        let fetcher = PullRequestFetcher(command: try fakeCLI(Self.tokenByAccount).path, account: "work")

        let mine = await fetcher.fetchMine()
        let comments = await fetcher.fetchComments(nodeIDs: ["PR_a"])

        XCTAssertEqual(mine, .success("token-for-work:--hostname=github.com"))
        XCTAssertEqual(comments, .success("token-for-work:--hostname=github.com"))
    }

    func testAChosenAccountThatIsSignedOutIsReportedAsNotSignedIn() async throws {
        let fetcher = PullRequestFetcher(command: try fakeCLI(Self.tokenByAccount).path, account: "signed-out")

        let result = await fetcher.fetchMine()

        XCTAssertEqual(result, .failure(.notAuthenticated("no oauth token found for github.com account signed-out")))
    }

    func testWithoutAChosenAccountTheCLIPicksItsOwn() async throws {
        let result = await PullRequestFetcher(command: try fakeCLI(Self.tokenByAccount).path).fetchMine()

        XCTAssertEqual(result, .success("unset"))
    }

    func testATokenInheritedFromTheEnvironmentNeverReachesTheCLI() async throws {
        // Either would silently override the account the menu shows as chosen. The test runner's own environment
        // is what the fetcher inherits, so it is set there for the length of the test.
        let names = ["GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"]
        names.forEach { setenv($0, "inherited", 1) }
        defer { names.forEach { unsetenv($0) } }
        let cli = try fakeCLI(#"env | grep -E '^(GH|GITHUB)_(ENTERPRISE_)?TOKEN=' || printf none"#)

        let result = await PullRequestFetcher(command: cli.path).fetchMine()

        XCTAssertEqual(result, .success("none"))
    }

    func testAsksForTheSignedInAccountsWithoutTheirTokens() async throws {
        let cli = try fakeCLI(#"printf '[%s]' "$@" "${GH_TOKEN-unset}""#)

        let result = await PullRequestFetcher(command: cli.path, account: "work").fetchAccounts()

        XCTAssertEqual(result, .success("[auth][status][--json][hosts][--hostname][github.com][unset]"))
    }

    func testBadCredentialsAreReportedAsNotSignedIn() async throws {
        let cli = try fakeCLI("echo 'non-200 OK status code: 401 Unauthorized body: Bad credentials' >&2\nexit 1")

        let result = await PullRequestFetcher(command: cli.path).fetchMine()

        XCTAssertEqual(result, .failure(.notAuthenticated("non-200 OK status code: 401 Unauthorized body: Bad credentials")))
    }

    func testAnOrganizationRefusingTheAccountIsReportedAsNoAccess() async throws {
        let cli = try fakeCLI("echo 'Resource protected by organization SAML enforcement.' >&2\nexit 1")

        let result = await PullRequestFetcher(command: cli.path).fetchMine()

        XCTAssertEqual(result, .failure(.noAccess("Resource protected by organization SAML enforcement.")))
    }

    func testACLIThatNeverAnswersIsGivenUpOnInTime() async throws {
        let cli = try fakeCLI("trap '' TERM\nsleep 5")
        let started = Date()

        let result = await PullRequestFetcher(command: cli.path, timeout: 0.3).fetchMine()

        XCTAssertEqual(result, .failure(.timedOut))
        XCTAssertLessThan(Date().timeIntervalSince(started), 2)
    }

    func testTheCLINeverReadsTheWidgetsStdin() async throws {
        let cli = try fakeCLI("cat")

        let result = await PullRequestFetcher(command: cli.path, timeout: 2).fetchMine()

        XCTAssertEqual(result, .success(""))
    }

    func testAMissingExecutableIsReportedAsNotFound() async {
        let missing = directory.appendingPathComponent("no-such-gh")

        let result = await PullRequestFetcher(command: missing.path).fetchMine()

        XCTAssertEqual(result, .failure(.cliNotFound))
    }

    func testCommandNameIsFoundInTheSearchDirectories() throws {
        let cli = try fakeCLI("true", named: "gh-work")
        let elsewhere = directory.appendingPathComponent("empty")

        let resolved = PullRequestFetcher.resolve("gh-work", searchDirectories: [elsewhere, directory])

        XCTAssertEqual(resolved?.path, cli.path)
    }

    func testCommandNameThatExistsNowhereIsNotResolved() {
        XCTAssertNil(PullRequestFetcher.resolve("no-such-gh-\(UUID().uuidString)", searchDirectories: [directory]))
    }

    func testCommandGivenAsAPathIsUsedAsIsAndNeverSearchedFor() throws {
        let cli = try fakeCLI("true", named: "gh-work")

        XCTAssertEqual(PullRequestFetcher.resolve(cli.path, searchDirectories: [])?.path, cli.path)
        XCTAssertNil(PullRequestFetcher.resolve("./gh-work", searchDirectories: [directory]))
    }

    func testFileThatIsNotExecutableIsNotResolved() throws {
        let file = directory.appendingPathComponent("gh-work")
        try "not a program".write(to: file, atomically: true, encoding: .utf8)

        XCTAssertNil(PullRequestFetcher.resolve(file.path, searchDirectories: []))
    }
}
