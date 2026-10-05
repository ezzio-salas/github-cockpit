import AppKit
import CockpitCore
import os

/// Polls GitHub for open pull requests and keeps the panel showing the latest good reading.
final class AppDelegate: NSObject, NSApplicationDelegate {
    private static let refreshInterval: TimeInterval = 60
    /// Ages and the stale marker move on without a fetch.
    private static let redrawInterval: TimeInterval = 30
    private static let pullRequestsPage = URL(string: "https://github.com/pulls")!

    private let log = Logger(subsystem: "local.github-cockpit", category: "pull-requests")
    /// `defaults write local.github-cockpit cliCommand <name or path>` points the widget at another CLI.
    private let fetcher = PullRequestFetcher(command: UserDefaults.standard.string(forKey: "cliCommand") ?? "gh")
    private let appearanceStore = AppearanceStore()
    private lazy var customization = CustomizationWindowController(store: appearanceStore) { [weak self] in
        self?.panel.apply($0)
        self?.render()
    }
    private lazy var panel = CockpitPanel(
        menu: makeMenu(),
        onClick: { [weak self] in self?.refresh() },
        onOpen: { NSWorkspace.shared.open($0.url) }
    )

    private var lastReading: (sections: [PullRequestSection], takenAt: Date)?
    /// Why the most recent fetch failed; nil after a success.
    private var failure: String?
    private var isFetching = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.mainMenu = Self.makeMainMenu()
        panel.apply(appearanceStore.appearance)
        refresh()
        Timer.scheduledTimer(
            timeInterval: Self.refreshInterval, target: self, selector: #selector(refresh), userInfo: nil, repeats: true
        )
        Timer.scheduledTimer(
            timeInterval: Self.redrawInterval, target: self, selector: #selector(render), userInfo: nil, repeats: true
        )
        offerCustomizationOnFirstLaunch()
    }

    /// The first launch offers personalization once; afterwards it is reached from the card's menu.
    private func offerCustomizationOnFirstLaunch() {
        guard !appearanceStore.hasOfferedCustomization else { return }
        appearanceStore.hasOfferedCustomization = true
        customization.present()
    }

    @objc private func showCustomization() {
        customization.present()
    }

    @objc private func openPullRequestsPage() {
        NSWorkspace.shared.open(Self.pullRequestsPage)
    }

    /// Starts a fetch unless one is already running, so polls never pile up.
    @objc private func refresh() {
        guard !isFetching else { return }
        isFetching = true
        render()

        Task { @MainActor in
            async let mine = fetcher.fetchMine()
            async let review = fetcher.fetchReviewRequested()
            let mineResult = await mine
            let reviewResult = await review
            isFetching = false
            record(Self.sections(mine: mineResult, review: reviewResult))
            render()
        }
    }

    private static func sections(
        mine: Result<String, PullRequestFetcher.FetchError>,
        review: Result<String, PullRequestFetcher.FetchError>
    ) -> Result<[PullRequestSection], Error> {
        Result {
            [
                PullRequestSection(name: "MINE", pullRequests: try PullRequestParser.parse(mine.get())),
                PullRequestSection(name: "REVIEW", pullRequests: try PullRequestParser.parse(review.get())),
            ]
        }
    }

    private func record(_ result: Result<[PullRequestSection], Error>) {
        switch result {
        case .success(let sections):
            lastReading = (sections, Date())
            failure = nil
        case .failure(let error):
            failure = Self.message(for: error)
            log.error("Pull request fetch failed: \(String(describing: error), privacy: .public)")
        }
    }

    @objc private func render() {
        let now = Date()
        let isStale = lastReading != nil && failure != nil
        let status: String
        if isFetching {
            status = "SYNC"
        } else if isStale, let lastReading {
            status = "STALE · \(RelativeTime.compact(now.timeIntervalSince(lastReading.takenAt)))"
        } else {
            status = ""
        }
        panel.render(CockpitSnapshot(body: body(), status: status, isStale: isStale), now: now)
    }

    /// The sections to draw, or the one message that stands in for them.
    private func body() -> CockpitSnapshot.Body {
        guard let lastReading else { return .message(failure ?? "READING PULL REQUESTS") }
        // An empty section is hidden; only when both are empty is there something to say.
        let sections = lastReading.sections.filter { !$0.pullRequests.isEmpty }
        return sections.isEmpty ? .message("NO OPEN PULL REQUESTS") : .sections(sections)
    }

    private func makeMenu() -> NSMenu {
        let menu = NSMenu()
        menu.addItem(withTitle: "Refresh", action: #selector(refresh), keyEquivalent: "").target = self
        menu.addItem(withTitle: "Open GitHub Pull Requests", action: #selector(openPullRequestsPage), keyEquivalent: "")
            .target = self
        menu.addItem(withTitle: "Customize…", action: #selector(showCustomization), keyEquivalent: "").target = self
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit GitHub Cockpit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "")
        return menu
    }

    /// The app shows no menu bar, but text fields rely on these items for their keyboard shortcuts.
    private static func makeMainMenu() -> NSMenu {
        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        let editItem = NSMenuItem()
        editItem.submenu = edit
        let mainMenu = NSMenu()
        mainMenu.addItem(editItem)
        return mainMenu
    }

    private static func message(for error: Error) -> String {
        switch error {
        case PullRequestFetcher.FetchError.cliNotFound: return "GH CLI NOT FOUND"
        case PullRequestFetcher.FetchError.timedOut: return "TIMED OUT"
        case PullRequestFetcher.FetchError.notAuthenticated: return "NOT SIGNED IN"
        case is PullRequestParser.ParseError: return "UNRECOGNIZED OUTPUT"
        default: return "COULD NOT READ PRS"
        }
    }
}
