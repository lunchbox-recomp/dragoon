import DragoonCore
import Foundation
import Testing

private let commitA = String(repeating: "a", count: 40)
private let commitB = String(repeating: "b", count: 40)
private let sourceInfo = "/Applications/Dragoon.app/Contents/Resources/source/source-info.json"

@Suite struct VersionsTests {
    @Test func theSourceInfoGivesItsCommitsAndItsDisc() {
        let fs = FakeFileSystem()
        let dol = String(repeating: "c", count: 40)
        fs.addFile(sourceInfo, Data("""
            {"dragoon": "\(commitA)", "gcn-recomp": "\(commitB)", "disc_id": "GKYE01", "dol_sha1": "\(dol)"}
            """.utf8))
        #expect(SourceInfo.read(at: sourceInfo, fs: fs) == SourceInfo(
            commits: Commits(dragoon: commitA, gcnRecomp: commitB),
            disc: ExpectedDisc(id: "GKYE01", dolSHA1: dol)))
    }

    @Test(arguments: [
        "", "{}", "{\"dragoon\": \"\(commitA)\", \"gcn-recomp\": \"\(commitB)\"}",
        "{\"dragoon\": \"ABC\", \"gcn-recomp\": \"\(commitB)\", \"disc_id\": \"GKYE01\", \"dol_sha1\": \"\(commitA)\"}",
    ])
    func aSourceInfoThatCantBeUsedIsNil(text: String) {
        let fs = FakeFileSystem()
        fs.addFile(sourceInfo, Data(text.utf8))
        #expect(SourceInfo.read(at: sourceInfo, fs: fs) == nil)
        #expect(SourceInfo.read(at: "/nowhere.json", fs: fs) == nil)
    }

    @Test func theInstalledGameHasTheStampTheRecipeWrote() {
        let fs = FakeFileSystem()
        fs.addDirectory(fakeData + "/game/20270115-080000-aaaaaaaaaaaa/Dragoon.app/Contents")
        fs.addFile(fakeData + "/game/20270115-080000-aaaaaaaaaaaa/stamp.json", Data("""
            {"built": "2027-01-15T08:00:00Z", "dragoon": "\(commitA)", "gcn-recomp": "\(commitB)",
             "sdk": "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk"}
            """.utf8))
        fs.addSymlink(fakeData + "/game/current", to: "20270115-080000-aaaaaaaaaaaa")
        #expect(InstalledGame.read(dataDirectory: fakeData, fs: fs)
            == InstalledGame(stamp: Commits(dragoon: commitA, gcnRecomp: commitB)))
    }

    @Test func aGameWithAStampThatCantBeReadIsStillInstalled() {
        let fs = FakeFileSystem()
        fs.addDirectory(fakeData + "/game/b1/Dragoon.app")
        fs.addFile(fakeData + "/game/b1/stamp.json", Data("{".utf8))
        fs.addSymlink(fakeData + "/game/current", to: "b1")
        #expect(InstalledGame.read(dataDirectory: fakeData, fs: fs) == InstalledGame(stamp: nil))
    }

    @Test func noCurrentGameIsNoGame() {
        let fs = FakeFileSystem()
        fs.addDirectory(fakeData + "/game/b1/Dragoon.app")
        #expect(InstalledGame.read(dataDirectory: fakeData, fs: fs) == nil)
        fs.addSymlink(fakeData + "/game/current", to: "gone")
        #expect(InstalledGame.read(dataDirectory: fakeData, fs: fs) == nil)
    }
}
