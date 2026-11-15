import AEPXKit
import SwiftUI

@main
struct CompanionApp: App {
    @StateObject private var model = AppModel()
    var body: some Scene {
        WindowGroup { RootView().environmentObject(model).preferredColorScheme(.dark) }
    }
}

@MainActor
final class AppModel: ObservableObject {
    let auth = Auth()
    let ads = Ads()
    @Published var entitlement: Entitlement?
    @Published var message: String?
    lazy var api: APIClient? = APIClient(token: { [weak auth] in auth?.accessToken })
    lazy var store = SubscriptionStore { [weak self] originalID in
        guard let self, let api = self.api else { throw URLError(.notConnectedToInternet) }
        let updated = try await api.verifyAppStore(originalID)
        await MainActor.run { self.apply(updated) }
    }

    init() { ads.start() }

    func apply(_ e: Entitlement) {
        entitlement = e
        ads.setRate(e.adRate)
    }

    func signedIn() async {
        guard let api else { message = "API base URL must use HTTPS"; return }
        do {
            apply(try await api.entitlement())
            await store.load()
            await store.restore()
        } catch {
            message = error.localizedDescription
        }
    }

    func subscribe() async {
        guard let account = entitlement?.accountID else { return }
        await store.purchase(accountID: account)
        if let err = store.lastError { message = err }
    }
}
