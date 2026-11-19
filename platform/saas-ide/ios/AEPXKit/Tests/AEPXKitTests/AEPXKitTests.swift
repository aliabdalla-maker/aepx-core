import XCTest
@testable import AEPXKit

final class AEPXKitTests: XCTestCase {
    func testAdRateMatchesWebAndAndroid() {
        XCTAssertTrue((0..<20).allSatisfy { AdRate.allowed(rate: 1, opportunity: $0) })
        XCTAssertEqual((0..<20).filter { AdRate.allowed(rate: 0.05, opportunity: $0) }.count, 1)
        XCTAssertEqual((0..<100).filter { AdRate.allowed(rate: 0.05, opportunity: $0) }.count, 5)
        XCTAssertFalse(AdRate.allowed(rate: 0, opportunity: 0))
        XCTAssertFalse(AdRate.allowed(rate: .nan, opportunity: 0))
        XCTAssertFalse(AdRate.allowed(rate: 0.05, opportunity: -1))
    }

    func testGateShowsNothingUntilEntitlementKnown() {
        let gate = AdGate()
        XCTAssertFalse(gate.tryOpportunity())
        gate.rate = 0.05
        XCTAssertEqual((0..<40).filter { _ in gate.tryOpportunity() }.count, 2)
    }

    func testAdUnitsDebugUsesTestIdsReleaseNeedsValidLiveIds() {
        XCTAssertEqual(AdUnits.resolve(debug: true, banner: nil, interstitial: nil).banner, TestAdUnits.banner)
        XCTAssertFalse(AdUnits.resolve(debug: false, banner: "", interstitial: "garbage").any)
        let live = AdUnits.resolve(debug: false, banner: "ca-app-pub-2980680946304710/1234567890", interstitial: nil)
        XCTAssertEqual(live.banner, "ca-app-pub-2980680946304710/1234567890")
        XCTAssertNil(live.interstitial)
    }

    func testFrequencyCap() {
        var t = Date(timeIntervalSince1970: 0)
        let cap = FrequencyCap(minInterval: 180, maxPerSession: 2, now: { t })
        XCTAssertTrue(cap.tryAcquire())
        XCTAssertFalse(cap.tryAcquire())
        t += 181; XCTAssertTrue(cap.tryAcquire())
        t += 999; XCTAssertFalse(cap.tryAcquire())
    }

    func testEntitlementParsingFailsClosed() throws {
        let id = "0B6F3C2E-8D1A-4F1E-9A51-2A7C9E4D5B60"
        let ok = #"{"plan":"trial","ad_rate":1.0,"subscribed":false,"trial_days_left":30,"account_id":"\#(id)","source":null}"#
        let e = try JSONDecoder().decode(Entitlement.self, from: Data(ok.utf8))
        XCTAssertEqual(e.label, "Free trial · 30 days left")
        XCTAssertTrue(e.canBuyInApp)
        for bad in [#"{"plan":"vip","ad_rate":0,"account_id":"\#(id)"}"#,
                    #"{"plan":"pro","ad_rate":1.5,"account_id":"\#(id)"}"#,
                    #"{"plan":"pro","ad_rate":0.05,"account_id":"nope"}"#] {
            XCTAssertThrowsError(try JSONDecoder().decode(Entitlement.self, from: Data(bad.utf8)))
        }
    }

    func testWrapperNavigationPolicy() {
        let p = NavigationPolicy(ideURL: URL(string: "https://ide.softwareequality.com")!,
                                 idpURLs: [URL(string: "https://login.softwareequality.com")!, URL(string: "http://bad.example")!])
        XCTAssertEqual(p.decide(URL(string: "https://ide.softwareequality.com/callback?code=1")!), .allow)
        XCTAssertEqual(p.decide(URL(string: "https://login.softwareequality.com/authorize")!), .allow)
        XCTAssertEqual(p.decide(URL(string: "https://www.softwareequality.com/aepx")!), .external)
        XCTAssertEqual(p.decide(URL(string: "https://checkout.stripe.com/c/pay/x")!), .deny)
        XCTAssertEqual(p.decide(URL(string: "http://ide.softwareequality.com")!), .deny)
        XCTAssertEqual(p.decide(URL(string: "https://bad.example")!), .deny)
        XCTAssertEqual(p.decide(URL(string: "https://ide.softwareequality.com:8443/")!), .deny)
    }

    func testPlanParsing() {
        let steps = PlanStep.parse(#"[{"agent":"architect","action":"design","goal":"Split API"},"raw"]"#)
        XCTAssertEqual(steps, [PlanStep(title: "architect · design", detail: "Split API"), PlanStep(title: "raw", detail: nil)])
        XCTAssertEqual(PlanStep.parse("just text"), [PlanStep(title: "just text", detail: nil)])
        XCTAssertEqual(PlanStep.parse(nil), [])
    }

    func testBaseURL() {
        XCTAssertNotNil(validatedBaseURL("https://ide-api.softwareequality.com/"))
        XCTAssertNil(validatedBaseURL("http://ide-api.softwareequality.com"))
        XCTAssertNil(validatedBaseURL("https://u@x.org"))
    }
}
