import AEPXKit
import SwiftUI

struct RootView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        Inner(auth: model.auth)
    }

    private struct Inner: View {
        @EnvironmentObject var model: AppModel
        @ObservedObject var auth: Auth
        var body: some View {
            NavigationStack {
                Group {
                    if auth.accessToken == nil {
                        SignInView()
                    } else {
                        ProjectsView()
                    }
                }
                .toolbar {
                    if auth.accessToken != nil {
                        Button("Sign out") { auth.signOut(); model.entitlement = nil }
                    }
                }
            }
            .safeAreaInset(edge: .top) {
                if let msg = model.message ?? auth.error {
                    Text(msg).font(.footnote).foregroundStyle(.red).padding(.horizontal)
                }
            }
            .task(id: auth.accessToken) { if auth.accessToken != nil { await model.signedIn() } }
        }
    }
}

struct SignInView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Governed agentic development").font(.title2.bold())
            Text("Review plans and approve agent tool calls from your phone. Every decision is audited.")
            Button("Sign in with your organisation") { Task { await model.auth.signIn() } }
                .buttonStyle(.borderedProminent)
        }
        .padding(24)
        .navigationTitle("AEP-X")
    }
}

struct PlanCard: View {
    @EnvironmentObject var model: AppModel
    @ObservedObject var store: SubscriptionStore
    let plan: Entitlement
    var body: some View {
        HStack {
            Text(plan.label)
            Spacer()
            if plan.canBuyInApp {
                Button(store.product.map { "Go Pro \($0.displayPrice)/mo" } ?? "Go Pro \(plan.price)") {
                    Task { await model.subscribe() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.product == nil)
            }
        }
    }
}

struct ProjectsView: View {
    @EnvironmentObject var model: AppModel
    @State private var projects: [Project] = []
    var body: some View {
        VStack(spacing: 0) {
            List {
                if let plan = model.entitlement { Section { PlanCard(store: model.store, plan: plan) } }
                Section("Projects") {
                    ForEach(projects) { p in NavigationLink(p.name, value: p) }
                }
                Section {
                    Button("Restore purchases") { Task { await model.store.restore() } }
                    if model.ads.privacyOptionsRequired { Button("Privacy options") { model.ads.showPrivacyOptions() } }
                }
            }
            BannerSlot(ads: model.ads)
        }
        .navigationTitle("AEP-X")
        .navigationDestination(for: Project.self) { RunsView(project: $0) }
        .task { await load() }
        .refreshable { await load() }
    }
    private func load() async {
        do { projects = try await model.api?.projects() ?? [] } catch { model.message = error.localizedDescription }
    }
}

struct RunsView: View {
    @EnvironmentObject var model: AppModel
    let project: Project
    @State private var runs: [RunSummary] = []
    var body: some View {
        VStack(spacing: 0) {
            List(runs) { r in
                NavigationLink(value: r) {
                    VStack(alignment: .leading) {
                        Text(r.status.replacingOccurrences(of: "_", with: " ")).foregroundStyle(.tint)
                        Text(r.task ?? "").lineLimit(2)
                    }
                }
            }
            BannerSlot(ads: model.ads)
        }
        .navigationTitle(project.name)
        .navigationDestination(for: RunSummary.self) { RunView(runID: $0.id) }
        .task { await load() }
        .refreshable { await load() }
    }
    private func load() async {
        do { runs = try await model.api?.runs(project.id) ?? [] } catch { model.message = error.localizedDescription }
    }
}

/// Approval surface: intentionally ad-free. Each decision needs an explicit confirmation.
struct RunView: View {
    @EnvironmentObject var model: AppModel
    let runID: String
    @State private var run: RunDetail?
    @State private var approvals: [ToolApproval] = []
    @State private var pending: (text: String, action: () async throws -> Void)?

    var body: some View {
        List {
            if let run {
                Section("Status") { Text(run.status.replacingOccurrences(of: "_", with: " ")) }
                Section("Plan") {
                    ForEach(Array(run.plan.enumerated()), id: \.offset) { _, step in
                        VStack(alignment: .leading) {
                            Text(step.title).bold()
                            if let d = step.detail { Text(d).font(.callout) }
                        }
                    }
                }
                if run.status == "awaiting_approval" {
                    Section {
                        Button("Approve plan") { confirm("Approve this plan?") { try await model.api?.decide(run: runID, approved: true) } }
                        Button("Reject plan", role: .destructive) { confirm("Reject this plan?") { try await model.api?.decide(run: runID, approved: false) } }
                    }
                }
                Section("Tool calls") {
                    ForEach(approvals) { a in
                        VStack(alignment: .leading, spacing: 4) {
                            Text("\(a.server) · \(a.tool)").bold()
                            Text("args sha256 \(a.argsSHA256.prefix(16))…").font(.caption.monospaced())
                            if a.state == "pending" {
                                HStack {
                                    Button("Allow") { confirm("Allow \(a.tool)?") { try await model.api?.decide(tool: a.id, approved: true) } }
                                    Button("Deny", role: .destructive) { confirm("Deny \(a.tool)?") { try await model.api?.decide(tool: a.id, approved: false) } }
                                }.buttonStyle(.bordered)
                            } else {
                                Text(a.state).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                if let result = run.result, !result.isEmpty { Section("Result") { Text(result) } }
            }
        }
        .navigationTitle("Run")
        .task { await load() }
        .refreshable { await load() }
        .onDisappear { if run?.isTerminal == true { model.ads.onLeftCompletedRun() } }
        .alert(pending?.text ?? "", isPresented: Binding(get: { pending != nil }, set: { if !$0 { pending = nil } })) {
            Button("Confirm") {
                let action = pending?.action
                Task { do { try await action?(); await load() } catch { model.message = error.localizedDescription } }
            }
            Button("Cancel", role: .cancel) {}
        }
    }

    private func confirm(_ text: String, _ action: @escaping () async throws -> Void) { pending = (text, action) }

    private func load() async {
        guard let api = model.api else { return }
        do {
            run = try await api.run(runID)
            approvals = try await api.approvals(runID)
        } catch { model.message = error.localizedDescription }
    }
}
