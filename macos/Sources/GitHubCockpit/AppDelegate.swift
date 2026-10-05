import AppKit
import CockpitCore
import os

/// Polls GitHub for open pull requests and keeps the panel showing the latest good reading.
final class AppDelegate: NSObject, NSApplicationDelegate {
    private static let refreshInterval: TimeInterval = 60
    /// Ages and the stale marker move on without a fetch.
    private static let redrawInterval: TimeInterval = 30
    private static let pullRequestsPage = URL(string: "https://github.com/pulls")!
    /// How long a confirmation such as `LINK COPIED` stays in the header.
    private static let noticeDuration: TimeInterval = 2

    private let log = Logger(subsystem: "local.github-cockpit", category: "pull-requests")
    /// `defaults write local.github-cockpit cliCommand <name or path>` points the widget at another CLI.
    private let fetcher = PullRequestFetcher(command: UserDefaults.standard.string(forKey: "cliCommand") ?? "gh")
    private let appearanceStore = AppearanceStore()
    private lazy var customization = CustomizationWindowController(store: appearanceStore) { [weak self] in
        self?.panel.apply($0)
        self?.render()
    }
    /// How long the pointer rests on a row before its comment shows, and how long the comment outlasts the
    /// pointer leaving, so sweeping across the card or crossing to the bubble does not flicker.
    private static let hoverDelay: TimeInterval = 0.35
    private static let unhoverDelay: TimeInterval = 0.3

    private lazy var bubble: CommentBubblePanel = {
        let bubble = CommentBubblePanel()
        bubble.onOpen = { NSWorkspace.shared.open($0) }
        bubble.onDismiss = { [weak self] dismissed in
            if dismissed == self?.announced { self?.announced = nil }
            self?.previewed = nil
        }
        bubble.onHoverChange = { [weak self] in
            self?.isPointerOnBubble = $0
            self?.scheduleHoverUpdate()
        }
        return bubble
    }()
    private lazy var panel = CockpitPanel(
        menu: makeMenu(),
        onClick: { [weak self] in self?.refresh() },
        onOpen: { NSWorkspace.shared.open($0.url) }
    )

    private var lastReading: (sections: [PullRequestSection], takenAt: Date)?
    /// Why the most recent fetch failed; nil after a success.
    private var failure: String?
    private var isFetching = false
    /// A short confirmation shown in the header in place of the status until it expires.
    private var notice: (text: String, until: Date)?
    private var commentWatch = CommentWatch()
    /// The latest comments read, which hovering a row looks up.
    private var comments: CommentReading?
    /// A new comment shown until it is dismissed; a hover preview covers it for a while, then gives way to it.
    private var announced: PullRequestComment?
    /// The comment shown because the pointer rests on its row.
    private var previewed: PullRequestComment?
    private var hoveredPullRequest: PullRequest?
    private var isPointerOnBubble = false
    private var hoverUpdate: DispatchWorkItem?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.mainMenu = Self.makeMainMenu()
        panel.apply(appearanceStore.appearance)
        // A bubble left behind by a moved card would point at nothing.
        panel.onMoved = { [weak self] in self?.bubble.dismiss() }
        panel.rowMenuItems = { [weak self] in self?.rowMenuItems(for: $0) ?? [] }
        panel.onHoverChange = { [weak self] in
            self?.hoveredPullRequest = $0
            self?.scheduleHoverUpdate()
        }
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
            await announceNewComment()
        }
    }

    /// Reads the latest comments on the pull requests the card shows and bubbles up the newest one that is
    /// news. A failure here is only logged: the card never depends on it.
    @MainActor private func announceNewComment() async {
        guard failure == nil, let lastReading else { return }
        let nodeIDs = lastReading.sections.flatMap(\.pullRequests).compactMap(\.nodeID)
        guard !nodeIDs.isEmpty else { return }

        let reading: CommentReading
        do {
            reading = try await CommentParser.parse(fetcher.fetchComments(nodeIDs: nodeIDs).get())
        } catch {
            log.error("Comment fetch failed: \(String(describing: error), privacy: .public)")
            return
        }
        comments = reading
        guard let comment = commentWatch.announce(reading) else { return }
        announced = comment
        // A hover preview keeps the bubble until the pointer moves on; the announcement follows it.
        if previewed == nil {
            showBubble(comment)
        }
    }

    // MARK: - Hover

    private func scheduleHoverUpdate() {
        hoverUpdate?.cancel()
        let update = DispatchWorkItem { [weak self] in self?.updateHoverBubble() }
        hoverUpdate = update
        let delay = hoveredPullRequest == nil ? Self.unhoverDelay : Self.hoverDelay
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: update)
    }

    /// Shows the latest comment on the row under the pointer. Once the pointer is on neither a row with comments
    /// nor the bubble, puts back what was there before.
    private func updateHoverBubble() {
        let hovered = hoveredPullRequest.flatMap { comments?.latestComment(number: $0.number, repo: $0.repo) }
        if let hovered {
            guard hovered != bubble.comment else { return }
            previewed = hovered
            showBubble(hovered)
        } else if !isPointerOnBubble, previewed != nil {
            previewed = nil
            if let announced {
                showBubble(announced)
            } else {
                bubble.dismiss()
            }
        }
    }

    private func showBubble(_ comment: PullRequestComment) {
        bubble.show(
            comment,
            pointingAt: panel.screenFrame(for: comment),
            beside: panel.cardScreenFrame,
            appearance: appearanceStore.appearance,
            now: Date()
        )
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
        if let notice, notice.until > now {
            status = notice.text
        } else if isFetching {
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

    // MARK: - Row menu

    private func rowMenuItems(for pullRequest: PullRequest) -> [NSMenuItem] {
        let open = NSMenuItem(title: "Open Pull Request", action: #selector(openPullRequest(_:)), keyEquivalent: "")
        let copy = NSMenuItem(title: "Copy Link", action: #selector(copyLink(_:)), keyEquivalent: "")
        for item in [open, copy] {
            item.target = self
            item.representedObject = pullRequest.url
        }
        return [open, copy]
    }

    @objc private func openPullRequest(_ sender: NSMenuItem) {
        guard let url = sender.representedObject as? URL else { return }
        NSWorkspace.shared.open(url)
    }

    @objc private func copyLink(_ sender: NSMenuItem) {
        guard let url = sender.representedObject as? URL else { return }
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(url.absoluteString, forType: .string)
        showNotice("LINK COPIED")
    }

    private func showNotice(_ text: String) {
        notice = (text, Date().addingTimeInterval(Self.noticeDuration))
        render()
        // `render` drops an expired notice itself, so a newer one shown meanwhile survives this.
        DispatchQueue.main.asyncAfter(deadline: .now() + Self.noticeDuration) { [weak self] in self?.render() }
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
