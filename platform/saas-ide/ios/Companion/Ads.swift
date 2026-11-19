import AEPXKit
import GoogleMobileAds
import SwiftUI
import UIKit
import UserMessagingPlatform

/// Consent-first AdMob (Google Mobile Ads 11.x API). The SDK starts only after UMP says ads may be
/// requested AND a unit is configured. No ad is shown until the entitlement sets the plan's ad rate,
/// and approval screens never host ads.
@MainActor
final class Ads: ObservableObject {
    @Published private(set) var ready = false
    @Published private(set) var rate: Double?
    let units = AdUnits.resolve(debug: AppConfig.isDebug, banner: AppConfig.bannerUnit, interstitial: AppConfig.interstitialUnit)
    let gate = AdGate()
    private let interstitialCap = FrequencyCap(minInterval: 180, maxPerSession: 3)
    private var interstitial: GADInterstitialAd?

    var privacyOptionsRequired: Bool {
        UMPConsentInformation.sharedInstance.privacyOptionsRequirementStatus == .required
    }

    func start() {
        guard units.any else { return }
        UMPConsentInformation.sharedInstance.requestConsentInfoUpdate(with: UMPRequestParameters()) { [weak self] _ in
            Task { @MainActor in
                if let root = Self.rootViewController() {
                    try? await UMPConsentForm.loadAndPresentIfRequired(from: root)
                }
                self?.initializeIfAllowed()
            }
        }
        initializeIfAllowed() // consent from a previous session may already allow requests
    }

    func setRate(_ rate: Double) {
        gate.rate = rate
        self.rate = rate
    }

    func showPrivacyOptions() {
        guard let root = Self.rootViewController() else { return }
        UMPConsentForm.presentPrivacyOptionsForm(from: root) { _ in }
    }

    private func initializeIfAllowed() {
        guard !ready, units.any, UMPConsentInformation.sharedInstance.canRequestAds else { return }
        GADMobileAds.sharedInstance().start { [weak self] _ in
            Task { @MainActor in self?.ready = true; self?.preloadInterstitial() }
        }
    }

    private func preloadInterstitial() {
        guard let unit = units.interstitial else { return }
        GADInterstitialAd.load(withAdUnitID: unit, request: GADRequest()) { [weak self] ad, _ in
            Task { @MainActor in self?.interstitial = ad }
        }
    }

    /// Natural break only: leaving a finished run.
    func onLeftCompletedRun() {
        guard let ad = interstitial, gate.tryOpportunity(), interstitialCap.tryAcquire(),
              let root = Self.rootViewController() else { return }
        interstitial = nil
        ad.present(fromRootViewController: root)
        preloadInterstitial()
    }

    static func rootViewController() -> UIViewController? {
        UIApplication.shared.connectedScenes.compactMap { ($0 as? UIWindowScene)?.keyWindow }.first?.rootViewController
    }
}

/// Anchored adaptive banner. One opportunity per appearance, decided once.
struct BannerSlot: View {
    @ObservedObject var ads: Ads
    @State private var allowed: Bool?

    var body: some View {
        Group {
            if ads.ready, let unit = ads.units.banner, allowed == true {
                BannerRepresentable(unit: unit).frame(height: 60)
            }
        }
        .onAppear { if allowed == nil, ads.rate != nil { allowed = ads.gate.tryOpportunity() } }
        .onChange(of: ads.rate) { _ in if allowed == nil { allowed = ads.gate.tryOpportunity() } }
    }
}

private struct BannerRepresentable: UIViewRepresentable {
    let unit: String
    func makeUIView(context: Context) -> GADBannerView {
        let width = UIScreen.main.bounds.width
        let view = GADBannerView(adSize: GADCurrentOrientationAnchoredAdaptiveBannerAdSizeWithWidth(width))
        view.adUnitID = unit
        view.rootViewController = Ads.rootViewController()
        view.load(GADRequest())
        return view
    }
    func updateUIView(_ uiView: GADBannerView, context: Context) {}
}
