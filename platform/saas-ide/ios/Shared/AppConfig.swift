import Foundation

/// Build-time configuration from Config/*.xcconfig via Info.plist. Never contains secrets.
enum AppConfig {
    private static func value(_ key: String) -> String {
        (Bundle.main.object(forInfoDictionaryKey: key) as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
    }
    static var apiBaseURL: String { value("AEPXAPIBaseURL") }
    static var ideURL: URL { URL(string: value("AEPXIDEURL")) ?? URL(string: "https://ide.softwareequality.com")! }
    static var tenant: String { value("AEPXTenant") }
    static var oidcIssuer: String { value("AEPXOIDCIssuer") }
    static var oidcClientID: String { value("AEPXOIDCClientID") }
    static var idpURLs: [URL] { value("AEPXIdPOrigins").split(separator: " ").compactMap { URL(string: String($0)) } }
    static var productID: String { value("AEPXAppStoreProductID") }
    static var bannerUnit: String { value("AEPXAdMobBannerUnit") }
    static var interstitialUnit: String { value("AEPXAdMobInterstitialUnit") }
    static var isDebug: Bool {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }
}
