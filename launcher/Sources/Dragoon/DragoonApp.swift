import DragoonCore
import DragoonViews
import Foundation
import SwiftUI

@main
enum Launch {
    /// `--check-tools` prints what `Toolchain.detect` found as JSON and exits, before any window
    /// opens. It exits 0 when the tools are ready and 1 when they aren't.
    ///
    /// `--check-disc PATH [--source-info FILE]` does the same for `checkDisc`. It checks the disc
    /// image at PATH against the `source-info.json` in the app's source snapshot, or FILE when
    /// that is given, and the two flags come in either order. It exits 0 for an `ok` disc, 1 for
    /// any other result and 2 for a bad argument or a source-info it can't use.
    ///
    /// `--dump-banner DISC OUT.png` writes the disc's banner as a PNG and exits 0, or exits 1
    /// when DISC is a folder, when the disc can't be opened, when it has no banner and when the
    /// PNG can't be written, and 2 for a bad argument.
    @MainActor
    static func main() {
        let arguments = Array(CommandLine.arguments.dropFirst())
        if arguments.contains("--dump-banner") {
            let result = runDumpBanner(arguments)
            print(result.stdout, terminator: "")
            FileHandle.standardError.write(Data(result.stderr.utf8))
            exit(result.status)
        }
        if arguments.contains("--check-disc") {
            let result = runCheckDisc(
                arguments,
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
    @State private var model = LauncherModel()

    var body: some Scene {
        Window(Strings.appName, id: "main") {
            ModelView(model: model)
                .frame(
                    minWidth: LauncherView.minimumSize.width,
                    minHeight: LauncherView.minimumSize.height)
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(LauncherView.defaultSize)
        .windowResizability(.contentMinSize)
    }
}

/// The window for the model's state, which launches the flow when it first appears.
struct ModelView: View {
    let model: LauncherModel
    @State private var windowIsActive = true

    var body: some View {
        LauncherView(state: model.state, send: { model.send($0) })
            .environment(\.windowIsActive, windowIsActive)
            .background(WindowWatcher(isActive: $windowIsActive))
            .onAppear { model.launch() }
    }
}
