import Foundation

/// Plan-based ad thinning, identical to web `impressionAllowed` and Android `AdRate`:
/// trial and free plans show every opportunity (rate 1.0); Pro shows 1 in 20 (rate 0.05).
public enum AdRate {
    public static func allowed(rate: Double, opportunity: Int) -> Bool {
        guard rate.isFinite, rate > 0 else { return false }
        if rate >= 1 { return true }
        let every = max(1, Int((1 / rate).rounded()))
        return opportunity >= 0 && opportunity % every == 0
    }
}

/// Counts ad opportunities. `rate` is nil until the server entitlement is known; until then no ad is shown.
public final class AdGate {
    private let lock = NSLock()
    private var opportunities = 0
    private var _rate: Double?

    public init() {}

    public var rate: Double? {
        get { lock.lock(); defer { lock.unlock() }; return _rate }
        set { lock.lock(); _rate = newValue; lock.unlock() }
    }

    public func tryOpportunity() -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard let r = _rate else { return false }
        defer { opportunities += 1 }
        return AdRate.allowed(rate: r, opportunity: opportunities)
    }
}

/// Google's published iOS sample units (https://developers.google.com/admob/ios/test-ads).
public enum TestAdUnits {
    public static let appID = "ca-app-pub-3940256099942544~1458002511"
    public static let banner = "ca-app-pub-3940256099942544/2435281174"
    public static let interstitial = "ca-app-pub-3940256099942544/4411468910"
}

/// Resolves which unit to request: test units in debug, configured live units in release, else nothing.
public struct AdUnits: Equatable {
    public let banner: String?
    public let interstitial: String?

    private static let unitPattern = try! NSRegularExpression(pattern: "^ca-app-pub-\\d{16}/\\d{10}$")

    static func valid(_ s: String?) -> String? {
        guard let s, !s.isEmpty,
              unitPattern.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)) != nil else { return nil }
        return s
    }

    public static func resolve(debug: Bool, banner: String?, interstitial: String?) -> AdUnits {
        if debug { return AdUnits(banner: TestAdUnits.banner, interstitial: TestAdUnits.interstitial) }
        return AdUnits(banner: valid(banner), interstitial: valid(interstitial))
    }

    public var any: Bool { banner != nil || interstitial != nil }
}

/// Full-screen ad cap: a minimum gap and a per-session maximum.
public final class FrequencyCap {
    private let minInterval: TimeInterval
    private let maxPerSession: Int
    private let now: () -> Date
    private var shown = 0
    private var last: Date?

    public init(minInterval: TimeInterval, maxPerSession: Int, now: @escaping () -> Date = Date.init) {
        self.minInterval = minInterval; self.maxPerSession = maxPerSession; self.now = now
    }

    public func tryAcquire() -> Bool {
        let t = now()
        if shown >= maxPerSession { return false }
        if let last, t.timeIntervalSince(last) < minInterval { return false }
        shown += 1; last = t
        return true
    }
}
