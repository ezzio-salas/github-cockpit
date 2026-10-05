import Foundation

/// Short durations, for the stale marker and the age of a pull request.
public enum RelativeTime {
    private static let minute: TimeInterval = 60
    private static let hour = 60 * minute
    private static let day = 24 * hour

    /// `30s`, `5m`, `3h`, `2d` — the longest unit that is at least 1, for the header marker.
    public static func compact(_ interval: TimeInterval) -> String {
        let seconds = max(interval, 0)
        if seconds < minute { return "\(Int(seconds))s" }
        if seconds < hour { return "\(Int(seconds / minute))m" }
        if seconds < day { return "\(Int(seconds / hour))h" }
        return "\(Int(seconds / day))d"
    }

    /// `JUST NOW`, `5M AGO`, `2D AGO`; empty when there is no timestamp.
    ///
    /// A moment in the future reads as `JUST NOW` rather than a negative age, because a clock a little out of
    /// step should not look like a bug.
    public static func age(of moment: Date?, now: Date) -> String {
        guard let moment else { return "" }
        let seconds = now.timeIntervalSince(moment)
        return seconds < minute ? "JUST NOW" : "\(compact(seconds).uppercased()) AGO"
    }
}
