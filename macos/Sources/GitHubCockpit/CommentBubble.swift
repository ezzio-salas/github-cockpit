import AppKit
import CockpitCore

/// A speech bubble beside the card that shows one comment.
///
/// It springs out of the row the comment belongs to and bobs gently while it is up. Its close button dismisses
/// it, its link button copies the comment's link, and clicking anywhere else opens the comment and dismisses it.
/// Showing another comment replaces it.
final class CommentBubblePanel: NSPanel {
    /// Space between the bubble's tail and the card.
    private static let gap: CGFloat = 4

    var onOpen: ((URL) -> Void)?
    /// Called with the comment's url when its link button is clicked.
    var onCopyLink: ((URL) -> Void)?
    /// Called with the comment on screen whenever the bubble goes away.
    var onDismiss: ((PullRequestComment) -> Void)?
    /// Called when the pointer moves onto the bubble (true) or off it (false).
    var onHoverChange: ((Bool) -> Void)?

    /// The comment on screen; nil when the bubble is hidden or leaving.
    private(set) var comment: PullRequestComment?
    private var bubbleView: CommentBubbleView?

    init() {
        super.init(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        hidesOnDeactivate = false
    }

    /// Shows `comment`, replacing any bubble already up.
    ///
    /// - Parameters:
    ///   - anchor: The screen rectangle the tail points at, normally the comment's row on the card.
    ///   - card: The card's screen rectangle; the bubble sits to its left, or to its right when there is no room.
    func show(
        _ comment: PullRequestComment, pointingAt anchor: NSRect, beside card: NSRect,
        appearance: CockpitAppearance, now: Date
    ) {
        let visible = (screen ?? NSScreen.main)?.visibleFrame ?? .zero
        let view = CommentBubbleView(comment: comment, appearance: appearance, now: now)
        view.onOpen = { [weak self] in
            self?.onOpen?(comment.url)
            self?.dismiss()
        }
        view.onClose = { [weak self] in self?.dismiss() }
        view.onCopyLink = { [weak self] in self?.onCopyLink?(comment.url) }
        view.onHoverChange = { [weak self] in self?.onHoverChange?($0) }
        let size = view.fittingSize
        let margin = CommentBubbleView.Metrics.glowMargin

        var origin = NSPoint(x: card.minX - Self.gap + margin - size.width, y: 0)
        if origin.x < visible.minX {
            view.tailSide = .left
            origin.x = card.maxX + Self.gap - margin
        }
        // The tail sits a little below the bubble's top, level with the anchor, unless the screen edge pushes
        // the bubble away; then the tail slides along the edge to keep pointing at the anchor.
        let top = min(max(anchor.midY + margin + CommentBubbleView.Metrics.tailOffset, visible.minY + size.height), visible.maxY)
        origin.y = top - size.height
        view.tailOffset = top - margin - anchor.midY

        self.comment = comment
        bubbleView = view
        contentView = view
        setFrame(NSRect(origin: origin, size: size), display: true)
        orderFrontRegardless()
        view.layoutSubtreeIfNeeded()
        view.animateIn()
    }

    func dismiss() {
        guard let view = bubbleView, let comment else { return }
        bubbleView = nil
        self.comment = nil
        onDismiss?(comment)
        view.animateOut { [weak self] in
            // A new bubble may have arrived while this one was leaving.
            if self?.bubbleView == nil { self?.orderOut(nil) }
        }
    }
}

/// The bubble: dark glass in the card's colors, a tail pointing at the card, and link and close buttons.
final class CommentBubbleView: NSView {
    enum Metrics {
        /// Transparent space around the bubble where its glow is drawn.
        static let glowMargin: CGFloat = 14
        static let cornerRadius: CGFloat = 14
        static let contentWidth: CGFloat = 236
        static let padding: CGFloat = 12
        /// How far the tail reaches out of the bubble, and half its height where it meets it.
        static let tailLength: CGFloat = 8
        static let tailHalfHeight: CGFloat = 7
        /// The tail's usual distance below the bubble's top.
        static let tailOffset: CGFloat = 24
        static let buttonSize: CGFloat = 14
        /// How long the link button shows a checkmark after copying.
        static let copiedFeedback: TimeInterval = 1.5
        static let bodyLineLimit = 4
    }

    enum TailSide {
        case left, right
    }

    var onOpen: (() -> Void)?
    var onClose: (() -> Void)?
    var onCopyLink: (() -> Void)?
    var onHoverChange: ((Bool) -> Void)?
    var tailSide = TailSide.right {
        didSet { updateContentInsets() }
    }
    /// From the bubble's top edge to the tail's tip.
    var tailOffset = Metrics.tailOffset {
        didSet { needsLayout = true }
    }

    /// Everything that moves: the animations act on this view's layer, never on the window.
    private let bubble = NSView()
    private let glow = CALayer()
    private let glass = NSVisualEffectView()
    private let shape = CAShapeLayer()
    private let closeButton = NSButton()
    private let copyButton = NSButton()
    private let content = NSStackView.column(spacing: 6)
    private var leadingInset: NSLayoutConstraint!
    private var trailingInset: NSLayoutConstraint!
    private let accent: NSColor

    init(comment: PullRequestComment, appearance: CockpitAppearance, now: Date) {
        accent = NSColor(appearance.accent)
        super.init(frame: .zero)
        // Always dark glass, like the card, whatever the system appearance.
        self.appearance = NSAppearance(named: .darkAqua)

        bubble.wantsLayer = true
        bubble.translatesAutoresizingMaskIntoConstraints = false
        addSubview(bubble)
        NSLayoutConstraint.activate([
            bubble.topAnchor.constraint(equalTo: topAnchor),
            bubble.bottomAnchor.constraint(equalTo: bottomAnchor),
            bubble.leadingAnchor.constraint(equalTo: leadingAnchor),
            bubble.trailingAnchor.constraint(equalTo: trailingAnchor),
        ])

        glow.shadowColor = NSColor(appearance.glow).cgColor
        glow.shadowOpacity = 0.55
        glow.shadowRadius = 9
        glow.shadowOffset = .zero
        bubble.layer?.addSublayer(glow)

        glass.material = .hudWindow
        glass.blendingMode = .behindWindow
        glass.state = .active
        glass.autoresizingMask = [.width, .height]
        bubble.addSubview(glass)

        shape.fillColor = NSColor(srgbRed: 0.02, green: 0.04, blue: 0.07, alpha: 0.6).cgColor
        shape.strokeColor = NSColor(appearance.border).withAlphaComponent(0.45).cgColor
        shape.lineWidth = 1
        bubble.layer?.addSublayer(shape)

        fill(with: comment, now: now)
        bubble.addSubview(content)
        let inset = Metrics.glowMargin + Metrics.padding
        leadingInset = content.leadingAnchor.constraint(equalTo: bubble.leadingAnchor)
        trailingInset = content.trailingAnchor.constraint(equalTo: bubble.trailingAnchor)
        NSLayoutConstraint.activate([
            content.topAnchor.constraint(equalTo: bubble.topAnchor, constant: inset),
            content.bottomAnchor.constraint(equalTo: bubble.bottomAnchor, constant: -inset),
            content.widthAnchor.constraint(equalToConstant: Metrics.contentWidth),
            leadingInset,
            trailingInset,
        ])
        updateContentInsets()

        addTrackingArea(NSTrackingArea(
            rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self
        ))
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not supported")
    }

    // MARK: - Content

    private func fill(with comment: PullRequestComment, now: Date) {
        let author = NSTextField.label(Theme.text(
            "@\(comment.author)", font: .monospacedSystemFont(ofSize: 10.5, weight: .medium), color: accent, kern: 0.3
        ))
        author.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let age = NSTextField.label(Self.detailText(RelativeTime.age(of: comment.createdAt, now: now)))
        Self.configure(copyButton, symbol: "link", toolTip: "Copy Link", target: self, action: #selector(copyLink))
        Self.configure(closeButton, symbol: "xmark", toolTip: "Dismiss", target: self, action: #selector(close))
        let trailing = NSStackView(views: [age, copyButton, closeButton])
        trailing.spacing = 6
        trailing.alignment = .centerY

        let body = NSTextField(wrappingLabelWithString: comment.text)
        body.font = .systemFont(ofSize: 12)
        body.textColor = Theme.primaryText
        body.maximumNumberOfLines = Metrics.bodyLineLimit
        body.cell?.truncatesLastVisibleLine = true
        body.preferredMaxLayoutWidth = Metrics.contentWidth

        let source = NSTextField.label(Self.detailText("\(comment.repo) \(comment.reference)"))

        content.addFullWidth(NSStackView.splitRow(leading: author, trailing: trailing))
        content.addFullWidth(body)
        content.addFullWidth(source)
        content.setCustomSpacing(8, after: body)
    }

    private static func configure(_ button: NSButton, symbol: String, toolTip: String, target: AnyObject, action: Selector) {
        button.image = symbolImage(symbol, description: toolTip)
        button.isBordered = false
        button.contentTintColor = Theme.secondaryText
        button.toolTip = toolTip
        button.target = target
        button.action = action
        button.widthAnchor.constraint(equalToConstant: Metrics.buttonSize).isActive = true
        button.heightAnchor.constraint(equalToConstant: Metrics.buttonSize).isActive = true
    }

    private static func symbolImage(_ name: String, description: String) -> NSImage? {
        NSImage(systemSymbolName: name, accessibilityDescription: description)?
            .withSymbolConfiguration(.init(pointSize: 8, weight: .bold))
    }

    private static func detailText(_ text: String) -> NSAttributedString {
        Theme.text(text, font: .monospacedSystemFont(ofSize: 9.5, weight: .regular), color: Theme.secondaryText, kern: 0.5)
    }

    private func updateContentInsets() {
        let inset = Metrics.glowMargin + Metrics.padding
        leadingInset.constant = inset + (tailSide == .left ? Metrics.tailLength : 0)
        trailingInset.constant = -inset - (tailSide == .right ? Metrics.tailLength : 0)
    }

    // MARK: - Shape

    /// The rounded body, without the tail.
    private var bodyRect: NSRect {
        var rect = bounds.insetBy(dx: Metrics.glowMargin, dy: Metrics.glowMargin)
        rect.size.width -= Metrics.tailLength
        if tailSide == .left { rect.origin.x += Metrics.tailLength }
        return rect
    }

    /// The tail's tip, in this view's coordinates; the bubble grows out of and shrinks back into this point.
    private var tailTip: NSPoint {
        let body = bodyRect
        let lowest = body.minY + Metrics.cornerRadius + Metrics.tailHalfHeight
        let highest = body.maxY - Metrics.cornerRadius - Metrics.tailHalfHeight
        let y = min(max(body.maxY - tailOffset, lowest), highest)
        return NSPoint(x: tailSide == .right ? body.maxX + Metrics.tailLength : body.minX - Metrics.tailLength, y: y)
    }

    private func outline() -> CGPath {
        let body = bodyRect
        let tip = tailTip
        let base = tailSide == .right ? body.maxX : body.minX
        let path = CGMutablePath()
        path.addRoundedRect(in: body, cornerWidth: Metrics.cornerRadius, cornerHeight: Metrics.cornerRadius)
        path.move(to: NSPoint(x: base, y: tip.y + Metrics.tailHalfHeight))
        path.addLine(to: tip)
        path.addLine(to: NSPoint(x: base, y: tip.y - Metrics.tailHalfHeight))
        path.closeSubpath()
        // The two pieces overlap only along the body's edge, so one fill reads as one shape.
        return path.union(path)
    }

    override func layout() {
        super.layout()
        guard bodyRect.width > Metrics.cornerRadius * 2, bodyRect.height > Metrics.cornerRadius * 2 else { return }
        let path = outline()

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        shape.path = path

        // Keep only the halo outside the bubble, so the glow never tints the glass.
        let halo = CGMutablePath()
        halo.addRect(bounds)
        halo.addPath(path)
        let mask = CAShapeLayer()
        mask.path = halo
        mask.fillRule = .evenOdd
        glow.frame = bounds
        glow.shadowPath = path
        glow.mask = mask
        CATransaction.commit()

        glass.frame = bounds
        glass.maskImage = NSImage(size: bounds.size, flipped: false) { _ in
            NSColor.black.setFill()
            NSBezierPath(cgPath: path).fill()
            return true
        }
    }

    // MARK: - Animation

    private static var reducesMotion: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    }

    /// Scales about `point` rather than about the layer's origin, which on macOS is its bottom-left corner.
    private static func scale(_ factor: CGFloat, about point: NSPoint) -> CATransform3D {
        var transform = CATransform3DMakeTranslation(point.x, point.y, 0)
        transform = CATransform3DScale(transform, factor, factor, 1)
        return CATransform3DTranslate(transform, -point.x, -point.y, 0)
    }

    func animateIn() {
        guard let layer = bubble.layer else { return }
        let fade = CABasicAnimation(keyPath: "opacity")
        fade.fromValue = 0
        fade.toValue = 1
        fade.duration = 0.18
        layer.add(fade, forKey: "fade")
        guard !Self.reducesMotion else { return }

        let pop = CASpringAnimation(keyPath: "transform")
        pop.fromValue = Self.scale(0.35, about: tailTip)
        pop.toValue = CATransform3DIdentity
        pop.damping = 13
        pop.stiffness = 240
        pop.mass = 0.9
        pop.duration = pop.settlingDuration
        layer.add(pop, forKey: "pop")

        // A slow float once it has landed, so the bubble reads as alive rather than as a window.
        let bob = CABasicAnimation(keyPath: "transform.translation.y")
        bob.fromValue = -1.5
        bob.toValue = 1.5
        bob.isAdditive = true
        bob.autoreverses = true
        bob.repeatCount = .infinity
        bob.duration = 1.6
        bob.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        bob.beginTime = CACurrentMediaTime() + pop.settlingDuration * 0.6
        layer.add(bob, forKey: "bob")
    }

    func animateOut(completion: @escaping () -> Void) {
        guard let layer = bubble.layer else { return completion() }
        layer.removeAnimation(forKey: "bob")

        let fade = CABasicAnimation(keyPath: "opacity")
        fade.fromValue = 1
        fade.toValue = 0
        var animations: [CAAnimation] = [fade]
        if !Self.reducesMotion {
            let shrink = CABasicAnimation(keyPath: "transform")
            shrink.toValue = CATransform3DTranslate(Self.scale(0.85, about: tailTip), 0, 6, 0)
            animations.append(shrink)
        }
        let leave = CAAnimationGroup()
        leave.animations = animations
        leave.duration = 0.22
        leave.timingFunction = CAMediaTimingFunction(name: .easeIn)

        CATransaction.begin()
        CATransaction.setCompletionBlock(completion)
        layer.opacity = 0
        layer.add(leave, forKey: "leave")
        CATransaction.commit()
    }

    // MARK: - Mouse

    @objc private func close() {
        onClose?()
    }

    @objc private func copyLink() {
        onCopyLink?()
        // A checkmark in the accent color confirms the copy where the eye already is.
        copyButton.image = Self.symbolImage("checkmark", description: "Copied")
        copyButton.contentTintColor = accent
        DispatchQueue.main.asyncAfter(deadline: .now() + Metrics.copiedFeedback) { [weak self] in
            self?.copyButton.image = Self.symbolImage("link", description: "Copy Link")
            self?.copyButton.contentTintColor = Theme.secondaryText
        }
    }

    // Apart from the buttons, the text never takes the mouse; the rest of the bubble is one click target.
    override func hitTest(_ point: NSPoint) -> NSView? {
        guard let hit = super.hitTest(point) else { return nil }
        return hit.isDescendant(of: closeButton) || hit.isDescendant(of: copyButton) ? hit : self
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        true
    }

    override func mouseUp(with event: NSEvent) {
        onOpen?()
    }

    override func mouseEntered(with event: NSEvent) {
        onHoverChange?(true)
    }

    override func mouseExited(with event: NSEvent) {
        onHoverChange?(false)
    }
}
