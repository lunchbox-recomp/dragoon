import DragoonCore
import Foundation
import SwiftUI

@main
enum Launch {
    /// `--check-tools` prints what `Toolchain.detect` found as JSON and exits, before any window
    /// opens. It exits 0 when the tools are ready and 1 when they aren't.
    ///
    /// `--check-disc PATH [--source-info FILE]` does the same for `checkDisc`. It checks the disc
    /// image at PATH against the `source-info.json` in the app's source snapshot, or FILE when
    /// that is given. It exits 0 for an `ok` disc, 1 for any other result and 2 for a bad
    /// argument or a source-info it can't use.
    @MainActor
    static func main() {
        let arguments = Array(CommandLine.arguments.dropFirst())
        if let flag = arguments.firstIndex(of: "--check-disc") {
            let result = runCheckDisc(
                Array(arguments[(flag + 1)...]),
                bundledSourceInfo: (Bundle.main.resourcePath ?? "") + "/source/source-info.json")
            print(result.stdout, terminator: "")
            FileHandle.standardError.write(Data(result.stderr.utf8))
            exit(result.status)
        }
        if arguments.contains("--check-tools") {
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
