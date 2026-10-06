import XCTest
@testable import CockpitCore

final class AccountParserTests: XCTestCase {
    func testListsTheGitHubAccountsInOrderAndMarksTheActiveOne() {
        let raw = #"""
        {"hosts":{"github.com":[
          {"login":"personal","active":true,"state":"success","tokenSource":"keyring"},
          {"login":"work","active":false,"state":"success","tokenSource":"keyring"}
        ]}}
        """#

        XCTAssertEqual(AccountParser.parse(raw), [
            GitHubAccount(login: "personal", isActive: true),
            GitHubAccount(login: "work", isActive: false),
        ])
    }

    func testAccountsOnOtherHostsAreNotOffered() {
        let raw = #"""
        {"hosts":{"github.com":[{"login":"personal","active":true}],
                  "github.example.com":[{"login":"enterprise","active":true}]}}
        """#

        XCTAssertEqual(AccountParser.parse(raw), [GitHubAccount(login: "personal", isActive: true)])
    }

    func testAnEntryWithoutALoginIsSkipped() {
        let raw = #"{"hosts":{"github.com":[{"active":true},{"login":""},{"login":"work"}]}}"#

        XCTAssertEqual(AccountParser.parse(raw), [GitHubAccount(login: "work", isActive: false)])
    }

    func testAnUnreadableAnswerGivesNoAccounts() {
        XCTAssertEqual(AccountParser.parse("not json"), [])
        XCTAssertEqual(AccountParser.parse("[]"), [])
        XCTAssertEqual(AccountParser.parse(#"{"hosts":{}}"#), [])
    }
}
