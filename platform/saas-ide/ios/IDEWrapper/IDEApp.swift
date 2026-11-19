import AEPXKit
import GoogleMobileAds
import StoreKit
import SwiftUI
import WebKit

/// "AEP-X IDE" for iPhone/iPad: the full web IDE in a locked-down WKWebView.
/// - Only the IDE and identity-provider origins load in-app; the website opens in Safari; all else is blocked.
/// - Stripe is never shown: purchases go through StoreKit via the `aepxStore` message bridge (see web
///   lib/nativeStore.ts). The page verifies the transaction with its own session; no token crosses the bridge.
/// - The web view is registered with the Google Mobile Ads WebView API so the IDE's web ads are app-compliant.
@main
struct IDEApp: App {
    var body: some Scene {
        WindowGroup { IDEWebView().ignoresSafeArea(edges: .bottom).preferredColorScheme(.dark) }
    }
}

struct IDEWebView: UIViewRepresentable {
    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.preferences.javaScriptCanOpenWindowsAutomatically = false
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.applicationNameForUserAgent = "AEPX-iOS/1"
        // Bridge available only to the IDE's main frame (checked again on every message).
        config.userContentController.add(context.coordinator, contentWorld: .page, name: "aepxStore")
        let view = WKWebView(frame: .zero, configuration: config)
        view.navigationDelegate = context.coordinator
        view.uiDelegate = context.coordinator
        view.allowsBackForwardNavigationGestures = true
        context.coordinator.webView = view
        GADMobileAds.sharedInstance().register(view)
        view.load(URLRequest(url: AppConfig.ideURL))
        return view
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    @MainActor
    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        weak var webView: WKWebView?
        let policy = NavigationPolicy(ideURL: AppConfig.ideURL, idpURLs: AppConfig.idpURLs)
        private var waiting: [String: CheckedContinuation<Bool, Never>] = [:]
        private lazy var store = SubscriptionStore { [weak self] originalID in
            guard let self, await self.verifyInPage(originalID) else { throw URLError(.userAuthenticationRequired) }
        }

        override init() {
            super.init()
            Task { await store.load() }
        }

        // MARK: navigation

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction) async -> WKNavigationActionPolicy {
            guard let url = action.request.url else { return .cancel }
            switch policy.decide(url) {
            case .allow: return .allow
            case .external: await UIApplication.shared.open(url); return .cancel
            case .deny: return .cancel
            }
        }

        func webView(_ webView: WKWebView, createWebViewWith c: WKWebViewConfiguration,
                     for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = action.request.url, policy.decide(url) == .external { UIApplication.shared.open(url) }
            return nil // never open extra web views
        }

        // MARK: StoreKit bridge

        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.frameInfo.isMainFrame, message.frameInfo.securityOrigin.host == policy.ideHost,
                  message.frameInfo.securityOrigin.protocol == "https",
                  let body = message.body as? [String: Any], let type = body["type"] as? String else { return }
            switch type {
            case "subscribe":
                guard let raw = body["accountId"] as? String, let account = UUID(uuidString: raw) else { return }
                Task { await store.purchase(accountID: account) }
            case "verified":
                guard let id = body["originalTransactionId"] as? String else { return }
                waiting.removeValue(forKey: id)?.resume(returning: body["ok"] as? Bool == true)
            case "manage":
                if let scene = webView?.window?.windowScene { Task { try? await AppStore.showManageSubscriptions(in: scene) } }
            default: break
            }
        }

        /// Hands the originalID to the page, which verifies with the backend and replies "verified".
        private func verifyInPage(_ originalID: UInt64) async -> Bool {
            let id = String(originalID)
            let bundle = (Bundle.main.bundleIdentifier ?? "").filter { $0.isLetter || $0.isNumber || $0 == "." || $0 == "-" }
            let js = "window.dispatchEvent(new CustomEvent('aepx-appstore-transaction',{detail:{originalTransactionId:'\(id)',bundleId:'\(bundle)'}}))"
            return await withCheckedContinuation { cont in
                waiting[id]?.resume(returning: false)
                waiting[id] = cont
                webView?.evaluateJavaScript(js)
                Task { [weak self] in
                    try? await Task.sleep(nanoseconds: 90 * 1_000_000_000)
                    self?.waiting.removeValue(forKey: id)?.resume(returning: false)
                }
            }
        }
    }
}
