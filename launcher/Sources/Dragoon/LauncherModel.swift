import DragoonCore
import Foundation
import Observation

/// Holds the flow's state for the window. Views send events here and never run anything
/// themselves.
@MainActor
@Observable
final class LauncherModel {
    private(set) var state = Flow.State()
    @ObservationIgnored private let effects: EffectRunner
    @ObservationIgnored private let places: Places

    init(places: Places = .system) {
        self.places = places
        effects = EffectRunner(places: places)
        effects.send = { [weak self] event in self?.send(event) }
    }

    /// Sends `launched` with what the app finds on disk. A second call changes nothing.
    func launch() {
        let fs = SystemFileSystem()
        send(.launched(Flow.Launch(
            appPath: places.bundle, onReadOnlyVolume: Volume.isReadOnly(places.bundle),
            settings: LauncherSettings.load(from: places.data, fs: fs),
            source: SourceInfo.read(at: places.sourceInfo, fs: fs),
            installed: InstalledGame.read(dataDirectory: places.data, fs: fs))))
    }

    func send(_ event: Flow.Event) {
        let (next, todo) = Flow.reduce(state, event)
        state = next
        todo.forEach(effects.perform)
    }
}

/// Where the app is and where it keeps the player's things.
struct Places: Sendable {
    var bundle: String
    var data: String

    static let system = Places(
        bundle: Bundle.main.bundlePath, data: Toolchain.defaultDataDirectory)

    var sourceInfo: String { bundle + "/Contents/Resources/source/source-info.json" }
    var saves: String { data + "/saves" }
}
