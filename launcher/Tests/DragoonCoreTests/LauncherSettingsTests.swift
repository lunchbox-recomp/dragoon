import DragoonCore
import Foundation
import Testing

@Suite struct LauncherSettingsTests {
    @Test func settingsThatArentThereAreTheDefaults() {
        #expect(LauncherSettings.load(from: fakeData, fs: FakeFileSystem()) == LauncherSettings())
    }

    @Test func settingsSaveToLauncherJSONInTheDataDirectoryAndLoadBack() throws {
        let scratch = try ScratchDirectory()
        defer { scratch.remove() }
        let settings = LauncherSettings(welcomeSeen: true, disc: Data([0, 1, 2, 255]))
        try settings.save(to: scratch.data, fs: SystemFileSystem())
        #expect(FileManager.default.fileExists(atPath: scratch.data + "/launcher.json"))
        #expect(LauncherSettings.load(from: scratch.data, fs: SystemFileSystem()) == settings)
    }

    @Test func savedSettingsNameBothFields() throws {
        let fs = FakeFileSystem()
        try LauncherSettings(welcomeSeen: true, disc: Data("bm".utf8)).save(to: fakeData, fs: fs)
        let text = String(decoding: try fs.readData(at: fakeData + "/launcher.json"), as: UTF8.self)
        #expect(text.contains("\"welcomeSeen\" : true"))
        #expect(text.contains("\"discBookmark\" : \"Ym0=\""))
    }

    @Test(arguments: ["not json", "[]", "{\"welcomeSeen\": \"yes\"}"])
    func settingsThatCantBeReadAreTheDefaults(text: String) {
        let fs = FakeFileSystem()
        fs.addFile(fakeData + "/launcher.json", Data(text.utf8))
        #expect(LauncherSettings.load(from: fakeData, fs: fs) == LauncherSettings())
    }

    @Test func aFieldThatIsMissingIsItsDefault() {
        let fs = FakeFileSystem()
        fs.addFile(fakeData + "/launcher.json", Data("{\"welcomeSeen\": true}".utf8))
        #expect(LauncherSettings.load(from: fakeData, fs: fs) == LauncherSettings(welcomeSeen: true))
    }
}
