import Foundation

/// Navigation policy for the IDE wrapper, matching the desktop shell:
/// IDE and identity-provider origins load in-app; the website opens in Safari; everything else is denied.
/// Stripe pages are never shown on iOS: digital subscriptions in iOS apps are sold through the App Store.
public struct NavigationPolicy {
    public enum Verdict: Equatable { case allow, external, deny }

    public let ideHost: String
    public let idpHosts: Set<String>
    static let externalHosts: Set<String> = ["softwareequality.com", "www.softwareequality.com"]
    static let blockedPaymentHosts: Set<String> = ["checkout.stripe.com", "billing.stripe.com"]

    public init(ideURL: URL, idpURLs: [URL]) {
        ideHost = ideURL.host ?? ""
        idpHosts = Set(idpURLs.filter { $0.scheme == "https" }.compactMap(\.host))
    }

    public func decide(_ url: URL) -> Verdict {
        if url.scheme == "about" && url.absoluteString == "about:blank" { return .allow }
        guard url.scheme == "https", url.user == nil, url.password == nil, url.port == nil,
              let host = url.host else { return .deny }
        if Self.blockedPaymentHosts.contains(host) { return .deny }
        if host == ideHost || idpHosts.contains(host) { return .allow }
        if Self.externalHosts.contains(host) { return .external }
        return .deny
    }
}

/// HTTPS-only base URL check for the native API client.
public func validatedBaseURL(_ raw: String) -> URL? {
    guard let url = URL(string: raw.trimmingCharacters(in: CharacterSet(charactersIn: "/"))),
          url.scheme == "https", url.host?.isEmpty == false, url.user == nil else { return nil }
    return url
}
