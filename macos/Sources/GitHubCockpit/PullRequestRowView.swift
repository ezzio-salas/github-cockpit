import AppKit
import CockpitCore

/// One pull request: its title and number, and the repository and age under them.
final class PullRequestRowView: NSView {
    let pullRequest: PullRequest

    /// The only hover feedback is the title brightening, so the card stays still under the pointer.
    var isHovered = false {
        didSet {
            guard isHovered != oldValue else { return }
            titleLabel.attributedStringValue = titleText()
        }
    }

    private let titleLabel = NSTextField.label(NSAttributedString())

    init(pullRequest: PullRequest, now: Date, accent: NSColor) {
        self.pullRequest = pullRequest
        super.init(frame: .zero)
        titleLabel.attributedStringValue = titleText()
        // The title gives way first; the number and the age always stay readable.
        titleLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        // A draft reads as not-yet-real, so the whole row recedes.
        let number = NSTextField.label(Theme.text(
            pullRequest.reference,
            font: .monospacedSystemFont(ofSize: 11, weight: .medium),
            color: pullRequest.isDraft ? Theme.secondaryText : accent,
            kern: 0.5
        ))
        let repo = NSTextField.label(Self.detailText(pullRequest.repo))
        repo.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let age = NSTextField.label(Self.detailText(RelativeTime.age(of: pullRequest.updatedAt, now: now)))

        let column = NSStackView.column(spacing: 3)
        column.addFullWidth(NSStackView.splitRow(leading: titleLabel, trailing: number))
        column.addFullWidth(NSStackView.splitRow(leading: repo, trailing: age))

        addSubview(column)
        NSLayoutConstraint.activate([
            column.topAnchor.constraint(equalTo: topAnchor),
            column.bottomAnchor.constraint(equalTo: bottomAnchor),
            column.leadingAnchor.constraint(equalTo: leadingAnchor),
            column.trailingAnchor.constraint(equalTo: trailingAnchor),
        ])
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not supported")
    }

    private func titleText() -> NSAttributedString {
        let color: NSColor
        if isHovered {
            color = Theme.hoveredText
        } else {
            color = pullRequest.isDraft ? Theme.secondaryText : Theme.primaryText
        }
        return Theme.text(pullRequest.title, font: .systemFont(ofSize: 11.5), color: color)
    }

    private static func detailText(_ text: String) -> NSAttributedString {
        Theme.text(text, font: .monospacedSystemFont(ofSize: 9.5, weight: .regular), color: Theme.secondaryText, kern: 0.5)
    }
}
