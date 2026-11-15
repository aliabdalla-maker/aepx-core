import AuthenticationServices
import CryptoKit
import Foundation

/// OIDC authorization code + PKCE (S256) with ASWebAuthenticationSession. Tokens stay in memory only.
@MainActor
final class Auth: NSObject, ObservableObject, ASWebAuthenticationPresentationContextProviding {
    @Published private(set) var accessToken: String?
    @Published var error: String?
    static let redirect = "com.equalitysoftware.aepx.companion:/oauth2redirect"

    private struct Discovery: Decodable { let authorization_endpoint: URL; let token_endpoint: URL }
    private struct Tokens: Decodable { let access_token: String }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor { ASPresentationAnchor() }

    func signOut() { accessToken = nil }

    func signIn() async {
        do {
            guard let issuer = URL(string: AppConfig.oidcIssuer), issuer.scheme == "https" else {
                throw URLError(.badURL)
            }
            let (data, _) = try await URLSession.shared.data(from: issuer.appendingPathComponent(".well-known/openid-configuration"))
            let discovery = try JSONDecoder().decode(Discovery.self, from: data)
            let verifier = Self.randomURLSafe(32)
            let challenge = Data(SHA256.hash(data: Data(verifier.utf8))).base64URL
            let state = Self.randomURLSafe(16)
            var auth = URLComponents(url: discovery.authorization_endpoint, resolvingAgainstBaseURL: false)!
            auth.queryItems = [
                .init(name: "response_type", value: "code"), .init(name: "client_id", value: AppConfig.oidcClientID),
                .init(name: "redirect_uri", value: Self.redirect), .init(name: "scope", value: "openid profile"),
                .init(name: "code_challenge", value: challenge), .init(name: "code_challenge_method", value: "S256"),
                .init(name: "state", value: state),
            ]
            let callback = try await withCheckedThrowingContinuation { (cont: CheckedContinuation<URL, Error>) in
                let session = ASWebAuthenticationSession(url: auth.url!, callbackURLScheme: "com.equalitysoftware.aepx.companion") { url, err in
                    if let url { cont.resume(returning: url) } else { cont.resume(throwing: err ?? URLError(.cancelled)) }
                }
                session.presentationContextProvider = self
                session.prefersEphemeralWebBrowserSession = false
                session.start()
            }
            let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems ?? []
            guard items.first(where: { $0.name == "state" })?.value == state,
                  let code = items.first(where: { $0.name == "code" })?.value else { throw URLError(.badServerResponse) }
            var request = URLRequest(url: discovery.token_endpoint)
            request.httpMethod = "POST"
            request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
            var form = URLComponents()
            form.queryItems = [
                .init(name: "grant_type", value: "authorization_code"), .init(name: "code", value: code),
                .init(name: "redirect_uri", value: Self.redirect), .init(name: "client_id", value: AppConfig.oidcClientID),
                .init(name: "code_verifier", value: verifier),
            ]
            request.httpBody = form.percentEncodedQuery?.data(using: .utf8)
            let (tokenData, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.userAuthenticationRequired) }
            accessToken = try JSONDecoder().decode(Tokens.self, from: tokenData).access_token
            error = nil
        } catch {
            if (error as? ASWebAuthenticationSessionError)?.code != .canceledLogin { self.error = "Sign-in failed" }
        }
    }

    private static func randomURLSafe(_ bytes: Int) -> String {
        var data = Data(count: bytes)
        _ = data.withUnsafeMutableBytes { SecRandomCopyBytes(kSecRandomDefault, bytes, $0.baseAddress!) }
        return data.base64URL
    }
}

extension Data {
    var base64URL: String {
        base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}
