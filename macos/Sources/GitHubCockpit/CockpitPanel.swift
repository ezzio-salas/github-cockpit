import AppKit
import CockpitCore

/// A frameless panel that floats above every window on every Space and never takes focus.
final class CockpitPanel: NSPanel {
    private static let topLeftKey = "panelTopLeft"
    private static let screenMargin: CGFloat = 12
    /// The card's title row, which a bubble points at when its pull request has no row.
    private static let headerHeight: CGFloat = 40

    private let cockpitView = CockpitView()

    /// Called after the card has been dragged to a new place.
    var onMoved: (() -> Void)?
    /// Called with the pull request under the pointer whenever it changes.
    var onHoverChange: ((PullRequest?) -> Void)? {
        get { cockpitView.onHoverChange }
        set { cockpitView.onHoverChange = newValue }
    }

    init(menu: NSMenu, onClick: @escaping () -> Void, onOpen: @escaping (PullRequest) -> Void) {
        super.init(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        isOpaque = false
        backgroundColor = .clear
        // The card draws its own glow; a system shadow would outline the transparent margin.
        hasShadow = false
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        hidesOnDeactivate = false

        cockpitView.menu = menu
        cockpitView.onClick = onClick
        cockpitView.onOpen = onOpen
        cockpitView.onMoved = { [weak self] in
            self?.saveTopLeft()
            self?.onMoved?()
        }
        contentView = cockpitView
    }

    func apply(_ appearance: CockpitAppearance) {
        cockpitView.apply(appearance)
    }

    /// Shows the snapshot and resizes to fit it, keeping the top-left corner where it is.
    func render(_ snapshot: CockpitSnapshot, now: Date) {
        cockpitView.render(snapshot, now: now)

        let size = cockpitView.fittingSize
        let topLeft = isVisible ? NSPoint(x: frame.minX, y: frame.maxY) : initialTopLeft(for: size)
        setFrame(NSRect(x: topLeft.x, y: topLeft.y - size.height, width: size.width, height: size.height), display: true)
        if !isVisible {
            orderFrontRegardless()
        }
    }

    /// The card's glass on screen.
    var cardScreenFrame: NSRect {
        convertToScreen(cockpitView.convert(cockpitView.cardFrame, to: nil))
    }

    /// The screen rectangle a bubble about `comment` points at: its row, or the card's header when the row is
    /// not shown.
    func screenFrame(for comment: PullRequestComment) -> NSRect {
        guard let row = cockpitView.rowFrame(number: comment.number, repo: comment.repo) else {
            let card = cardScreenFrame
            return NSRect(x: card.minX, y: card.maxY - Self.headerHeight, width: card.width, height: Self.headerHeight)
        }
        return convertToScreen(cockpitView.convert(row, to: nil))
    }

    private func saveTopLeft() {
        UserDefaults.standard.set(NSStringFromPoint(NSPoint(x: frame.minX, y: frame.maxY)), forKey: Self.topLeftKey)
    }

    /// The saved position if it is still on a connected screen, otherwise the top-right of the main screen.
    private func initialTopLeft(for size: NSSize) -> NSPoint {
        if let saved = UserDefaults.standard.string(forKey: Self.topLeftKey).map(NSPointFromString) {
            let center = NSPoint(x: saved.x + size.width / 2, y: saved.y - size.height / 2)
            if NSScreen.screens.contains(where: { $0.visibleFrame.contains(center) }) {
                return saved
            }
        }
        let visible = NSScreen.main?.visibleFrame ?? .zero
        return NSPoint(x: visible.maxX - size.width - Self.screenMargin, y: visible.maxY - Self.screenMargin)
    }
}
