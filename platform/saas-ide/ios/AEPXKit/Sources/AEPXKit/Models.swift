import Foundation

public struct Project: Decodable, Identifiable, Hashable { public let id: String; public let name: String }

public struct RunSummary: Decodable, Identifiable, Hashable {
    public let id: String
    public let status: String
    public let task: String?
}

public struct PlanStep: Hashable { public let title: String; public let detail: String? }

public struct RunDetail: Decodable {
    public let id: String
    public let status: String
    public let result: String?
    public let plan: [PlanStep]

    enum CodingKeys: String, CodingKey { case id, status, result, plan }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        status = try c.decode(String.self, forKey: .status)
        result = try c.decodeIfPresent(String.self, forKey: .result)
        // plan is JSON text from supervisor.plan_steps(): [{agent, action, goal}] (or plain text).
        let raw = try? c.decodeIfPresent(String.self, forKey: .plan)
        plan = PlanStep.parse(raw ?? nil)
    }

    public static let terminal: Set<String> = ["succeeded", "failed", "cancelled", "rejected"]
    public var isTerminal: Bool { Self.terminal.contains(status) }
}

extension PlanStep {
    public static func parse(_ raw: String?) -> [PlanStep] {
        guard let raw, !raw.trimmingCharacters(in: .whitespaces).isEmpty else { return [] }
        guard let data = raw.data(using: .utf8),
              let array = try? JSONSerialization.jsonObject(with: data) as? [Any] else {
            return [PlanStep(title: raw.trimmingCharacters(in: .whitespacesAndNewlines), detail: nil)]
        }
        return array.prefix(50).map { item in
            guard let o = item as? [String: Any] else { return PlanStep(title: "\(item)", detail: nil) }
            let title = [o["agent"], o["action"]].compactMap { $0 as? String }.filter { !$0.isEmpty }.joined(separator: " · ")
            let detail = (o["goal"] ?? o["detail"] ?? o["description"]) as? String
            return PlanStep(title: title.isEmpty ? (o["title"] as? String ?? "Step") : title, detail: detail)
        }
    }
}

public struct ToolApproval: Decodable, Identifiable, Hashable {
    public let id: String
    public let server: String
    public let tool: String
    public let argsSHA256: String
    public let state: String
    enum CodingKeys: String, CodingKey { case id, server, tool, state, argsSHA256 = "args_sha256" }
}
