import DragoonCore
import Foundation
import SwiftUI

@main
enum Launch {
    /// `--check-tools` prints what `Toolchain.detect` found as JSON and exits, before any window
    /// opens. It exits 0 when the tools are ready and 1 when they aren't.
    @MainActor
    static func main() {
        if CommandLine.arguments.dropFirst().contains("--check-tools") {
            Task {
                let status = await Toolchain.detect(
                    runner: SystemProcessRunner(), fs: SystemFileSystem())
                print(status.json())
                exit(status.isReady ? 0 : 1)
            }
            dispatchMain()
        }
        DragoonApp.main()
    }
}

struct DragoonApp: App {
    var body: some Scene {
        Window("Dragoon", id: "main") {
            Color.clear
                .frame(minWidth: 640, minHeight: 420)
        }
    }
}
