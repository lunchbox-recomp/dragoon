import DragoonCore
import Foundation
import Testing

/// One file in `SettingsFixtures/`: `<name>.in` is settings.txt before the save, missing for a
/// file that isn't there, and `<name>.out` what the engine's `settings_save` wrote over it with
/// these values. A harness built against gcn-recomp's `runtime/settings.cpp` and
/// `runtime/platform.cpp` wrote both, and `cases.txt` lists the values it saved.
struct SettingsFixture: CustomTestStringConvertible, Sendable {
    let name: String
    let picture: PictureSettings
    let before: Data?
    let after: Data

    var testDescription: String { name }

    static let directory = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().appendingPathComponent("SettingsFixtures")

    static let all: [SettingsFixture] = {
        let list = (try? String(contentsOf: directory.appendingPathComponent("cases.txt"), encoding: .utf8)) ?? ""
        return list.split(separator: "\n").compactMap { line in
            let words = line.split(separator: " ").map(String.init)
            guard words.count == 5, let scale = Int(words[3]),
                let after = try? Data(contentsOf: directory.appendingPathComponent(words[0] + ".out"))
            else { return nil }
            return SettingsFixture(
                name: words[0],
                picture: PictureSettings(
                    aspect: words[1], fullscreen: words[2] == "1", scale: scale, fastDisc: words[4] == "fast"),
                before: try? Data(contentsOf: directory.appendingPathComponent(words[0] + ".in")),
                after: after)
        }
    }()
}

@Suite struct PictureSettingsTests {
    private let path = fakeData + "/settings.txt"

    @Test func everyFixtureIsListedAndRead() {
        #expect(SettingsFixture.all.count == 18)
        #expect(SettingsFixture.all.filter { $0.before == nil }.map(\.name) == ["missing"])
    }

    @Test(arguments: SettingsFixture.all)
    func aSaveWritesTheBytesTheEngineWrites(_ fixture: SettingsFixture) throws {
        let scratch = try ScratchDirectory("settings")
        defer { scratch.remove() }
        let file = scratch.data + "/settings.txt"
        try FileManager.default.createDirectory(atPath: scratch.data, withIntermediateDirectories: true)
        if let before = fixture.before { try before.write(to: URL(fileURLWithPath: file)) }
        try fixture.picture.save(to: scratch.data, fs: SystemFileSystem())
        #expect(try Data(contentsOf: URL(fileURLWithPath: file)) == fixture.after)
        #expect(!FileManager.default.fileExists(atPath: file + ".tmp"))
    }

    @Test(arguments: SettingsFixture.all)
    func whatASaveWroteLoadsBackAsWhatWasSet(_ fixture: SettingsFixture) {
        #expect(PictureSettings(parsing: fixture.after) == fixture.picture)
    }

    @Test func aSaveWritesTheTemporaryFileThenRenamesItOverSettings() throws {
        let fs = FakeFileSystem()
        fs.addFile(path, Data("aspect 4:3\n".utf8))
        try PictureSettings(aspect: "16:9").save(to: fakeData, fs: fs)
        #expect(fs.writes.map(\.path) == [path + ".tmp"])
        #expect(fs.renames == [.init(from: path + ".tmp", to: path)])
        #expect(!fs.fileExists(at: path + ".tmp"))
        #expect(try fs.readData(at: path) == Data("aspect 16:9\nfullscreen 0\nscale 2\ndisc fast\n".utf8))
    }

    @Test(arguments: [
        PictureSettings(aspect: "16:9\n"), PictureSettings(aspect: "0:9"), PictureSettings(aspect: "16:10000"),
        PictureSettings(aspect: "Window"), PictureSettings(aspect: ""), PictureSettings(aspect: "16:9:1"),
        PictureSettings(scale: 0), PictureSettings(scale: -1), PictureSettings(scale: 1_000_000_000),
    ])
    func aValueTheEngineWouldSkipIsRefusedAndNothingIsWritten(_ picture: PictureSettings) {
        let fs = FakeFileSystem()
        fs.addFile(path, Data("aspect 4:3\n".utf8))
        #expect(throws: PictureSettings.SaveFailure.refused) { try picture.save(to: fakeData, fs: fs) }
        #expect(fs.writes.isEmpty)
        #expect(fs.renames.isEmpty)
    }

    @Test func aFileThatIsThereAndCantBeReadIsLeftAlone() {
        let fs = FakeFileSystem()
        fs.addDirectory(path)
        let failure = #expect(throws: PictureSettings.SaveFailure.self) {
            try PictureSettings(aspect: "16:9").save(to: fakeData, fs: fs)
        }
        guard case .unreadable? = failure else {
            Issue.record("\(String(describing: failure)) isn't unreadable")
            return
        }
        #expect(fs.writes.isEmpty)
        #expect(fs.isDirectory(at: path))
    }

    @Test func aWriteThatFailsLeavesTheOldFile() throws {
        let fs = FakeFileSystem()
        fs.addFile(path, Data("aspect 4:3\n".utf8))
        fs.failWrites(with: POSIXError(.ENOSPC))
        #expect(throws: PictureSettings.SaveFailure.notWritten(POSIXError(.ENOSPC).localizedDescription)) {
            try PictureSettings(aspect: "16:9").save(to: fakeData, fs: fs)
        }
        #expect(try fs.readData(at: path) == Data("aspect 4:3\n".utf8))
    }

    @Test func aRenameThatFailsLeavesTheOldFileAndRemovesTheTemporaryOne() throws {
        let fs = FakeFileSystem()
        fs.addFile(path, Data("aspect 4:3\n".utf8))
        fs.failRenames(with: POSIXError(.EACCES))
        #expect(throws: PictureSettings.SaveFailure.notWritten(POSIXError(.EACCES).localizedDescription)) {
            try PictureSettings(aspect: "16:9").save(to: fakeData, fs: fs)
        }
        #expect(try fs.readData(at: path) == Data("aspect 4:3\n".utf8))
        #expect(!fs.fileExists(at: path + ".tmp"))
    }

    @Test func aFileThatIsntThereLoadsAsTheEngineDefaults() {
        #expect(PictureSettings.load(from: fakeData, fs: FakeFileSystem()) == PictureSettings())
        #expect(PictureSettings() == PictureSettings(aspect: "4:3", fullscreen: false, scale: 2, fastDisc: true))
    }

    @Test func theLastLineTheEngineTakesWinsAndOthersAreSkipped() {
        let text = """
            aspect 16:9
            aspect 21:9
            aspect 5
            scale 3
            scale 1000000000
            fullscreen 1
            fullscreen yes
            disc console
            disc slow
            # aspect 16:10
            aspectx 4:3
            """
        #expect(PictureSettings(parsing: Data(text.utf8))
            == PictureSettings(aspect: "21:9", fullscreen: true, scale: 3, fastDisc: false))
    }

    @Test(arguments: [
        ("4:3", 4.0 / 3), ("16:9", 16.0 / 9), ("0016:0009", 16.0 / 9), ("9999:1", 9999), ("window", 0),
    ] as [(String, Double)])
    func anAspectTheEngineTakesHasItsRatio(_ aspect: String, _ ratio: Double) {
        #expect(PictureSettings.ratio(of: aspect) == ratio)
    }

    @Test(arguments: ["", "4", "4:", ":3", "4:3:", "10000:1", "4:0", "-4:3", "+4:3", "4 :3", "４:3", "windows"])
    func anAspectTheEngineRefusesHasNone(_ aspect: String) {
        #expect(PictureSettings.ratio(of: aspect) == nil)
    }

    @Test func theAspectsAreTheDisplayPagesInItsOrder() {
        #expect(PictureSettings.aspects == ["4:3", "16:9", "16:10", "21:9", "window"])
    }
}
