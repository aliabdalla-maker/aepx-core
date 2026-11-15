import Foundation
import StoreKit

/// StoreKit 2 purchase of the £4.99/month auto-renewing subscription.
///
/// The app grants nothing locally. Each verified transaction's originalID is handed to [verify], which
/// sends it to POST /api/v1/billing/app-store/verify; the server re-checks it with the App Store Server API
/// and matches appAccountToken to the signed-in account. Only then is the transaction finished.
@MainActor
final class SubscriptionStore: ObservableObject {
    @Published private(set) var product: Product?
    @Published var lastError: String?
    private var updates: Task<Void, Never>?
    private let verify: (UInt64) async throws -> Void

    init(verify: @escaping (UInt64) async throws -> Void) {
        self.verify = verify
        updates = Task { [weak self] in
            for await result in Transaction.updates { await self?.handle(result) }
        }
    }

    deinit { updates?.cancel() }

    func load() async {
        guard !AppConfig.productID.isEmpty else { return }
        product = try? await Product.products(for: [AppConfig.productID]).first
    }

    /// appAccountToken binds the purchase to the backend account (server rejects any mismatch).
    func purchase(accountID: UUID) async {
        guard let product else { lastError = "Subscription is not available yet"; return }
        do {
            switch try await product.purchase(options: [.appAccountToken(accountID)]) {
            case .success(let result): await handle(result)
            case .pending: lastError = "Purchase pending approval"
            case .userCancelled: break
            @unknown default: break
            }
        } catch {
            lastError = error.localizedDescription
        }
    }

    /// Re-sends current subscriptions (reinstall, new device, "Restore purchases").
    func restore() async {
        for await result in Transaction.currentEntitlements { await handle(result) }
    }

    private func handle(_ result: VerificationResult<Transaction>) async {
        guard case .verified(let transaction) = result, transaction.productID == AppConfig.productID else { return }
        do {
            try await verify(transaction.originalID)
            await transaction.finish()
        } catch {
            // Unfinished transactions are redelivered by StoreKit, so verification is retried later.
            lastError = "Purchase received; verification pending"
        }
    }
}
