// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Dragoon",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "Dragoon", targets: ["Dragoon"]),
    ],
    targets: [
        // The SwiftUI app, kept thin. Everything it does that can be tested lives in DragoonCore,
        // and the window's views and strings in DragoonViews, so tests can render them.
        .executableTarget(name: "Dragoon", dependencies: ["DragoonCore", "DragoonViews"]),
        .target(name: "DragoonViews", dependencies: ["DragoonCore"]),
        .target(name: "DragoonCore"),
        .testTarget(name: "DragoonCoreTests", dependencies: ["DragoonCore"]),
    ]
)
