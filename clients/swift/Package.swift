// swift-tools-version: 5.7
import PackageDescription

let package = Package(
    name: "OrbitClient",
    platforms: [.macOS(.v12), .iOS(.v15)],
    products: [
        .library(name: "OrbitClient", targets: ["OrbitClient"]),
        .executable(name: "OrbitExample", targets: ["OrbitExample"]) 
    ],
    targets: [
        .target(name: "OrbitClient"),
        .executableTarget(name: "OrbitExample", dependencies: ["OrbitClient"], path: "Examples/SwiftExample"),
        .testTarget(name: "OrbitClientTests", dependencies: ["OrbitClient"]) 
    ]
)
