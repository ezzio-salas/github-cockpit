import AppKit
import CockpitCore

/// A titled list of pull requests, such as `MINE` or `REVIEW`.
struct PullRequestSection {
    let name: String
    let pullRequests: [PullRequest]
}

/// What the widget shows at one moment.
struct CockpitSnapshot {
    enum Body {
        case sections([PullRequestSection])
        case message(String)
    }

    let body: Body
    /// Short header note such as `SYNC` or `STALE · 2m`; empty when there is nothing to report.
    let status: String
    let isStale: Bool
}

/// The glass card. Dragging it moves the window; clicking a row reports `onOpen`, clicking elsewhere `onClick`.
final class CockpitView: NSView {
    private enum Metrics {
        /// Transparent space around the card where its glow is drawn.
        static let glowMargin: CGFloat = 14
        static let cornerRadius: CGFloat = 16
        /// Wider than Claude Cockpit's 260, because a pull request title needs the room a percentage does not.
        static let cardWidth: CGFloat = 300
        static let padding: CGFloat = 16
        static let dragThreshold: CGFloat = 3
    }

    var onClick: (() -> Void)?
    var onOpen: ((PullRequest) -> Void)?
    var onMoved: (() -> Void)?
    /// Reports the pull request under the pointer whenever it changes; nil once the pointer leaves the rows.
    var onHoverChange: ((PullRequest?) -> Void)?
    /// Items about one pull request, shown above the card's own menu when a row is right-clicked.
    var rowMenuItems: ((PullRequest) -> [NSMenuItem])?

    private let glow = CALayer()
    private let surface = NSView()
    private let titleLabel = NSTextField.label(NSAttributedString())
    private let statusLabel = NSTextField.label(NSAttributedString())
    private let bodyStack = NSStackView.column(spacing: 18)
    private var rows: [PullRequestRowView] = []
    private var hoveredPullRequest: PullRequest?
    private var accent = NSColor(CockpitAppearance.standard.accent)
    private var drag: (mouseStart: NSPoint, windowStart: NSPoint, didMove: Bool)?

    init() {
        super.init(frame: .zero)
        wantsLayer = true
        appearance = NSAppearance(named: .darkAqua)

        glow.shadowOpacity = 0.55
        glow.shadowRadius = 9
        glow.shadowOffset = .zero
        layer?.addSublayer(glow)

        let card = makeCard()
        let content = makeContent()
        card.addSubview(content)
        NSLayoutConstraint.activate([
            content.topAnchor.constraint(equalTo: card.topAnchor, constant: Metrics.padding),
            content.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -Metrics.padding),
            content.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: Metrics.padding),
            content.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -Metrics.padding),
        ])
        addTrackingArea(NSTrackingArea(
            rect: .zero, options: [.mouseMoved, .mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self
        ))
        apply(.standard)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not supported")
    }

    /// Takes effect on the title, border and glow at once, and on the rest of the card at the next `render`.
    func apply(_ appearance: CockpitAppearance) {
        accent = NSColor(appearance.accent)
        titleLabel.attributedStringValue = sectionTitleText(appearance.title)
        surface.layer?.borderColor = NSColor(appearance.border).withAlphaComponent(0.45).cgColor
        glow.shadowColor = NSColor(appearance.glow).cgColor
    }

    func render(_ snapshot: CockpitSnapshot, now: Date) {
        statusLabel.attributedStringValue = Theme.text(
            snapshot.status,
            font: Theme.displayFont(size: 8),
            color: snapshot.isStale ? Theme.amber : accent.withAlphaComponent(0.6),
            kern: 1.5
        )
        // An empty label still has a default line height, which would nudge the header as the status comes and goes.
        statusLabel.isHidden = snapshot.status.isEmpty

        bodyStack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        rows = []
        switch snapshot.body {
        case .sections(let sections):
            sections.forEach { bodyStack.addFullWidth(sectionView($0, now: now)) }
        case .message(let message):
            bodyStack.addFullWidth(NSTextField.label(Theme.text(
                message, font: Theme.displayFont(size: 9), color: Theme.primaryText, kern: 1.5
            )))
        }
        // Pull requests read before a failure stay on screen, dimmed, rather than disappearing.
        bodyStack.alphaValue = snapshot.isStale ? 0.45 : 1

        // The rows were rebuilt, so the one under a pointer that has not moved needs its highlight back.
        layoutSubtreeIfNeeded()
        if let window {
            updateHover(at: convert(window.mouseLocationOutsideOfEventStream, from: nil))
        }
    }

    /// The card's glass, in this view's coordinates.
    var cardFrame: NSRect {
        surface.frame
    }

    /// Where the row for pull request `number` in `repo` is, in this view's coordinates; nil when it is not shown.
    func rowFrame(number: Int, repo: String) -> NSRect? {
        rows.first { $0.pullRequest.number == number && $0.pullRequest.repo == repo }
            .map { $0.convert($0.bounds, to: self) }
    }

    // MARK: - Construction

    /// Blurred backdrop plus a tinted, outlined surface that holds the content.
    private func makeCard() -> NSView {
        let glass = NSVisualEffectView()
        glass.material = .hudWindow
        glass.blendingMode = .behindWindow
        glass.state = .active
        glass.maskImage = Self.roundedMask(radius: Metrics.cornerRadius)

        surface.wantsLayer = true
        surface.layer?.backgroundColor = NSColor(srgbRed: 0.02, green: 0.04, blue: 0.07, alpha: 0.55).cgColor
        surface.layer?.cornerRadius = Metrics.cornerRadius
        surface.layer?.borderWidth = 1

        for view in [glass, surface] {
            view.translatesAutoresizingMaskIntoConstraints = false
            addSubview(view)
            NSLayoutConstraint.activate([
                view.topAnchor.constraint(equalTo: topAnchor, constant: Metrics.glowMargin),
                view.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -Metrics.glowMargin),
                view.leadingAnchor.constraint(equalTo: leadingAnchor, constant: Metrics.glowMargin),
                view.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -Metrics.glowMargin),
            ])
        }
        surface.widthAnchor.constraint(equalToConstant: Metrics.cardWidth).isActive = true
        return surface
    }

    private func makeContent() -> NSView {
        let content = NSStackView.column(spacing: 14)
        content.addFullWidth(NSStackView.splitRow(leading: titleLabel, trailing: statusLabel))
        content.addFullWidth(bodyStack)
        return content
    }

    private func sectionView(_ section: PullRequestSection, now: Date) -> NSView {
        let list = NSStackView.column(spacing: 12)
        for pullRequest in section.pullRequests {
            let row = PullRequestRowView(pullRequest: pullRequest, now: now, accent: accent)
            rows.append(row)
            list.addFullWidth(row)
        }

        let column = NSStackView.column(spacing: 10)
        column.addFullWidth(NSTextField.label(sectionTitleText(section.name)))
        column.addFullWidth(list)
        return column
    }

    private func sectionTitleText(_ name: String) -> NSAttributedString {
        Theme.text(name, font: Theme.displayFont(size: 11, weight: .bold), color: accent, kern: 3)
    }

    private static func roundedMask(radius: CGFloat) -> NSImage {
        let edge = radius * 2 + 1
        let image = NSImage(size: NSSize(width: edge, height: edge), flipped: false) { rect in
            NSColor.black.setFill()
            NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
            return true
        }
        image.capInsets = NSEdgeInsets(top: radius, left: radius, bottom: radius, right: radius)
        image.resizingMode = .stretch
        return image
    }

    // MARK: - Glow

    override func layout() {
        super.layout()
        let cardRect = bounds.insetBy(dx: Metrics.glowMargin, dy: Metrics.glowMargin)
        guard cardRect.width > Metrics.cornerRadius * 2, cardRect.height > Metrics.cornerRadius * 2 else { return }

        let outline = CGPath(
            roundedRect: cardRect,
            cornerWidth: Metrics.cornerRadius,
            cornerHeight: Metrics.cornerRadius,
            transform: nil
        )
        // Keep only the halo outside the card, so the glow never tints the glass.
        let halo = CGMutablePath()
        halo.addRect(bounds)
        halo.addPath(outline)
        let mask = CAShapeLayer()
        mask.path = halo
        mask.fillRule = .evenOdd

        glow.frame = bounds
        glow.shadowPath = outline
        glow.mask = mask
    }

    // MARK: - Mouse

    // Labels never take the mouse; the whole card is one drag and click target, and a click is routed to the
    // row under it by position. That is what keeps moving the card from opening a pull request.
    override func hitTest(_ point: NSPoint) -> NSView? {
        super.hitTest(point) == nil ? nil : self
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        true
    }

    override func mouseDown(with event: NSEvent) {
        guard let window else { return }
        drag = (NSEvent.mouseLocation, window.frame.origin, false)
    }

    override func mouseDragged(with event: NSEvent) {
        guard let window, var drag else { return }
        let mouse = NSEvent.mouseLocation
        let dx = mouse.x - drag.mouseStart.x
        let dy = mouse.y - drag.mouseStart.y
        guard drag.didMove || hypot(dx, dy) >= Metrics.dragThreshold else { return }

        drag.didMove = true
        self.drag = drag
        window.setFrameOrigin(NSPoint(x: drag.windowStart.x + dx, y: drag.windowStart.y + dy))
    }

    override func mouseUp(with event: NSEvent) {
        guard let drag else { return }
        self.drag = nil
        if drag.didMove {
            onMoved?()
        } else if let row = row(at: convert(event.locationInWindow, from: nil)) {
            onOpen?(row.pullRequest)
        } else {
            onClick?()
        }
    }

    override func menu(for event: NSEvent) -> NSMenu? {
        guard let cardMenu = menu,
              let row = row(at: convert(event.locationInWindow, from: nil)),
              let items = rowMenuItems?(row.pullRequest)
        else { return menu }

        let rowMenu = NSMenu()
        items.forEach(rowMenu.addItem)
        rowMenu.addItem(.separator())
        // Copies, because a menu item belongs to one menu at a time.
        cardMenu.items.forEach { rowMenu.addItem($0.copy() as! NSMenuItem) }
        return rowMenu
    }

    override func mouseMoved(with event: NSEvent) {
        updateHover(at: convert(event.locationInWindow, from: nil))
    }

    override func mouseExited(with event: NSEvent) {
        updateHover(at: nil)
    }

    private func updateHover(at point: NSPoint?) {
        let hovered = point.flatMap(row(at:))
        rows.forEach { $0.isHovered = $0 === hovered }
        // Rows are rebuilt on every render, so the pull request, not the row, says whether anything changed.
        guard hovered?.pullRequest != hoveredPullRequest else { return }
        hoveredPullRequest = hovered?.pullRequest
        onHoverChange?(hoveredPullRequest)
    }

    private func row(at point: NSPoint) -> PullRequestRowView? {
        rows.first { $0.convert($0.bounds, to: self).contains(point) }
    }
}
