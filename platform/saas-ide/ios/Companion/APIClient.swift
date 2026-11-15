import AEPXKit
import Foundation

struct APIError: LocalizedError { let status: Int; let detail: String; var errorDescription: String? { detail } }

/// Thin client for the IDE backend. HTTPS only; no redirects followed for authenticated calls.
final class APIClient: NSObject, URLSessionTaskDelegate {
    private let base: URL
    private let token: @MainActor () -> String?
    private lazy var session = URLSession(configuration: .ephemeral, delegate: self, delegateQueue: nil)

    init?(token: @escaping @MainActor () -> String?) {
        guard let base = validatedBaseURL(AppConfig.apiBaseURL) else { return nil }
        self.base = base; self.token = token
    }

    func urlSession(_ s: URLSession, task: URLSessionTask, willPerformHTTPRedirection r: HTTPURLResponse,
                    newRequest: URLRequest) async -> URLRequest? { nil }

    private func call<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil) async throws -> T {
        guard let bearer = await token() else { throw APIError(status: 401, detail: "Sign in first") }
        var request = URLRequest(url: URL(string: base.absoluteString + path)!)
        request.httpMethod = method
        request.timeoutInterval = 30
        request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        request.setValue(AppConfig.tenant, forHTTPHeaderField: "X-Tenant-ID")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await session.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw APIError(status: status, detail: detail ?? "API error \(status)")
        }
        if T.self == Empty.self { return Empty() as! T }
        return try JSONDecoder().decode(T.self, from: data)
    }

    private struct Empty: Decodable {}
    private func seg(_ s: String) -> String { s.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(.init(charactersIn: "/"))) ?? s }

    func entitlement() async throws -> Entitlement { try await call("/api/v1/entitlement") }
    func verifyAppStore(_ originalID: UInt64) async throws -> Entitlement {
        try await call("/api/v1/billing/app-store/verify", method: "POST", body: ["original_transaction_id": String(originalID),
                                                                       "bundle_id": Bundle.main.bundleIdentifier ?? ""])
    }
    func projects() async throws -> [Project] { try await call("/api/v1/projects") }
    func runs(_ project: String) async throws -> [RunSummary] { try await call("/api/v1/projects/\(seg(project))/agent-runs") }
    func run(_ id: String) async throws -> RunDetail { try await call("/api/v1/agent-runs/\(seg(id))") }
    func approvals(_ id: String) async throws -> [ToolApproval] { try await call("/api/v1/agent-runs/\(seg(id))/tool-approvals") }
    func decide(run id: String, approved: Bool) async throws {
        let _: Empty = try await call("/api/v1/agent-runs/\(seg(id))/decision?approved=\(approved)", method: "POST")
    }
    func decide(tool id: String, approved: Bool) async throws {
        let _: Empty = try await call("/api/v1/tool-approvals/\(seg(id))/decision?approved=\(approved)", method: "POST")
    }
}
