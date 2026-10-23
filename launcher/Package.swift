// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Dragoon",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "Dragoon", targets: ["Dragoon"]),
    ],
    targets: [
        // The SwiftUI app, kept thin. Everything it does that can be tested lives in DragoonCore.
        .executableTarget(name: "Dragoon", dependencies: ["DragoonCore"]),
        .target(name: "DragoonCore"),
        .testTarget(name: "DragoonCoreTests", dependencies: ["DragoonCore"]),
    ]
)
