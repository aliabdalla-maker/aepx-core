// swift-tools-version:5.9
import PackageDescription

// Platform-free core (Foundation only) shared by the iOS companion and the IDE wrapper, so the
// money- and security-relevant rules are unit-tested with `swift test`.
let package = Package(
    name: "AEPXKit",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [.library(name: "AEPXKit", targets: ["AEPXKit"])],
    targets: [
        .target(name: "AEPXKit"),
        .testTarget(name: "AEPXKitTests", dependencies: ["AEPXKit"]),
    ]
)
