import Foundation

/// Server entitlement (GET /api/v1/entitlement). The backend is the only source of truth.
public struct Entitlement: Decodable, Equatable {
    public let plan: String
    public let adRate: Double
    public let subscribed: Bool
    public let trialDaysLeft: Int
    public let price: String
    public let accountID: UUID
    public let source: String?

    enum CodingKeys: String, CodingKey {
        case plan, subscribed, price, source
        case adRate = "ad_rate", trialDaysLeft = "trial_days_left", accountID = "account_id"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        plan = try c.decode(String.self, forKey: .plan)
        guard ["trial", "pro", "free"].contains(plan) else {
            throw DecodingError.dataCorruptedError(forKey: .plan, in: c, debugDescription: "Unknown plan")
        }
        adRate = try c.decode(Double.self, forKey: .adRate)
        guard (0...1).contains(adRate) else {
            throw DecodingError.dataCorruptedError(forKey: .adRate, in: c, debugDescription: "ad_rate out of range")
        }
        subscribed = try c.decodeIfPresent(Bool.self, forKey: .subscribed) ?? false
        trialDaysLeft = try c.decodeIfPresent(Int.self, forKey: .trialDaysLeft) ?? 0
        price = try c.decodeIfPresent(String.self, forKey: .price) ?? "£4.99/month"
        accountID = try c.decode(UUID.self, forKey: .accountID)
        source = try c.decodeIfPresent(String.self, forKey: .source)
    }

    /// StoreKit is offered only to people without an active subscription from any store.
    public var canBuyInApp: Bool { !subscribed }

    public var label: String {
        switch plan {
        case "trial": return "Free trial · \(trialDaysLeft) days left"
        case "pro": return "Pro · 95% fewer ads"
        default: return "Free plan · ads supported"
        }
    }
}
