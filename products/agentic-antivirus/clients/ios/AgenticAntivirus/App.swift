import SwiftUI
import WebKit
import GoogleMobileAds
import UserMessagingPlatform

/// iPhone/iPad client: the accessible web console plus native AdMob (consent first) and StoreKit 2.
/// Subscriptions require an Apple Developer account; until the control plane's App Store verification is
/// configured, purchases are not offered (register item B-03).
@main
struct AgenticAntivirusApp: App {
    var body: some Scene { WindowGroup { ConsoleView() } }
}

enum AdPolicy {
    /// Same pacing as server/web/Android: show when floor(n*rate) increases (1.0 trial, 0.05 paid).
    final class Pacer {
        let rate: Double; private var n = 0
        init(rate: Double) { self.rate = min(1, max(0, rate)) }
        func next() -> Bool { let b = Int(Double(n) * rate); n += 1; return Int(Double(n) * rate) > b }
    }
    /// Banner placement by console route; nil = never (approvals, incident detail, quarantine, login, billing, audit).
    static func placement(for path: String) -> String? {
        switch path.split(separator: "?").first.map(String.init)?.trimmingCharacters(in: CharacterSet(charactersIn: "/")) ?? "" {
        case "": return "dashboard_banner"
        case "devices": return "device_list_banner"
        case "incidents": return "incident_list_banner"
        case "settings": return "settings_banner"
        case "help": return "help_banner"
        default: return nil
        }
    }
    static let testBanner = "ca-app-pub-3940256099942544/2435281174"
}

final class ConsoleModel: NSObject, ObservableObject, WKNavigationDelegate {
    @Published var placement: String?
    @Published var canRequestAds = false
    let web: WKWebView
    var pacer = AdPolicy.Pacer(rate: 1.0)
    let consoleURL = URL(string: Bundle.main.object(forInfoDictionaryKey: "AAVConsoleURL") as! String)!

    override init() {
        let cfg = WKWebViewConfiguration()
        cfg.applicationNameForUserAgent = "AgenticAntivirusApp/" + (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0")
        web = WKWebView(frame: .zero, configuration: cfg)
        super.init()
        web.navigationDelegate = self
        web.load(URLRequest(url: consoleURL))
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, url.host != consoleURL.host { UIApplication.shared.open(url); decisionHandler(.cancel); return }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        let base = consoleURL.path
        let path = String((webView.url?.path ?? "/").dropFirst(max(0, base.count - 1)))
        let p = AdPolicy.placement(for: path)
        placement = (p != nil && canRequestAds && pacer.next()) ? p : nil
        webView.evaluateJavaScript("[sessionStorage.getItem('aav.token'), sessionStorage.getItem('aav.tenant')]") { [weak self] r, _ in
            guard let self, let arr = r as? [Any], let token = arr.first as? String, let tenant = arr.last as? String else { return }
            self.refreshEntitlement(token: token, tenant: tenant)
        }
    }

    func refreshEntitlement(token: String, tenant: String) {
        var req = URLRequest(url: consoleURL.appendingPathComponent("api/v1/licence"))
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue(tenant, forHTTPHeaderField: "X-Tenant-Id")
        URLSession.shared.dataTask(with: req) { data, _, _ in
            guard let data, let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let rate = obj["ad_rate"] as? Double else { return }
            DispatchQueue.main.async { if rate != self.pacer.rate { self.pacer = AdPolicy.Pacer(rate: rate) } }
        }.resume()
    }

    func startConsent() {
        let params = RequestParameters()
        ConsentInformation.shared.requestConsentInfoUpdate(with: params) { [weak self] _ in
            guard let root = UIApplication.shared.connectedScenes.compactMap({ ($0 as? UIWindowScene)?.keyWindow }).first?.rootViewController else { return }
            ConsentForm.loadAndPresentIfRequired(from: root) { _ in
                if ConsentInformation.shared.canRequestAds {
                    MobileAds.shared.start(completionHandler: nil)
                    DispatchQueue.main.async { self?.canRequestAds = true }
                }
            }
        }
    }
}

struct WebContainer: UIViewRepresentable {
    let web: WKWebView
    func makeUIView(context: Context) -> WKWebView { web }
    func updateUIView(_ v: WKWebView, context: Context) {}
}

struct Banner: UIViewRepresentable {
    let unit: String
    func makeUIView(context: Context) -> BannerView {
        let b = BannerView(adSize: AdSizeBanner)
        b.adUnitID = unit
        b.rootViewController = UIApplication.shared.connectedScenes.compactMap { ($0 as? UIWindowScene)?.keyWindow }.first?.rootViewController
        b.accessibilityLabel = "Advertisement"
        b.load(Request())
        return b
    }
    func updateUIView(_ v: BannerView, context: Context) {}
}

struct ConsoleView: View {
    @StateObject private var model = ConsoleModel()
    /// Live unit IDs come from ads-config.json once their format is known in the AdMob console;
    /// until then no live unit is requested. Debug builds use Google's sample banner.
    private var bannerUnit: String? {
        #if DEBUG
        return AdPolicy.testBanner
        #else
        return nil
        #endif
    }
    var body: some View {
        VStack(spacing: 0) {
            WebContainer(web: model.web)
            if model.placement != nil, let unit = bannerUnit { Banner(unit: unit).frame(height: 50) }
        }
        .ignoresSafeArea(edges: .bottom)
        .onAppear { model.startConsent() }
    }
}
