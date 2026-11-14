import DragoonCore
import Foundation
import Testing

private let discPath = "/Users/Test Player/Games/Kirby Air Ride (USA).gcm"

@Suite struct DumpBannerCommandTests {
    private let out = "/Users/Test Player/Desktop/banner out.png"

    private func world() -> FakeFileSystem {
        let fs = FakeFileSystem()
        fs.addFile(discPath, makeDisc(root: [.file("opening.bnr", makeBNR(pixels: distinctPixels))]).image)
        return fs
    }

    @Test func writesThePNGAndPrintsTheNames() throws {
        let fs = world()
        let result = runDumpBanner(["--dump-banner", discPath, out], fs: fs)
        #expect(result.status == 0)
        let banner = try #require(DiscBanner.read(at: discPath, fs: fs))
        #expect(fs.writes == [.init(path: out, data: banner.png()!)])
        let fields = try #require(
            JSONSerialization.jsonObject(with: Data(result.stdout.utf8)) as? [String: String])
        #expect(fields == [
            "format": "BNR1", "shortName": "Test Ride", "shortMaker": "Test Maker",
            "longName": "Test Ride: The Long Name", "longMaker": "Test Maker Co.",
        ])
        #expect(result.stdout.hasSuffix("\n"))
        #expect(result.stderr.hasPrefix("read and decoded in "))
        #expect(result.stderr.hasSuffix(" ms\n"))
    }

    @Test func aDiscWithNoBannerExits1AndWritesNothing() {
        let fs = FakeFileSystem()
        fs.addFile(discPath, makeDisc(root: []).image)
        let result = runDumpBanner(["--dump-banner", discPath, out], fs: fs)
        #expect(result.status == 1)
        #expect(result.stdout == "")
        #expect(result.stderr == "\(discPath): no opening.bnr on the root that can be read\n")
        #expect(fs.writes.isEmpty)
    }

    @Test func aDiscThatCantBeOpenedExits1AndSaysSo() {
        let fs = FakeFileSystem()
        let result = runDumpBanner(["--dump-banner", discPath, out], fs: fs)
        #expect(result.status == 1)
        #expect(result.stdout == "")
        #expect(result.stderr.hasPrefix("\(discPath): can't be opened ("))
        #expect(result.stderr.hasSuffix(")\n"))
        #expect(fs.writes.isEmpty)
    }

    @Test func aFolderExits1AndSaysItIsntADisc() {
        let fs = FakeFileSystem()
        fs.addDirectory(discPath)
        let result = runDumpBanner(["--dump-banner", discPath, out], fs: fs)
        #expect(result == CommandResult(
            stdout: "", stderr: "\(discPath): is a folder, not a disc image\n", status: 1))
        #expect(fs.writes.isEmpty)
    }

    /// On the real file system a folder says so, and a FIFO nothing writes to is refused at
    /// once, where a plain open(2) would wait for a writer.
    @Test(.timeLimit(.minutes(1)))
    func aRealFolderOrFIFOExits1WithoutWaiting() throws {
        let scratch = try ScratchDirectory("dump banner")
        defer { scratch.remove() }
        let folder = scratch.path + "/a folder.gcm"
        try FileManager.default.createDirectory(atPath: folder, withIntermediateDirectories: false)
        let fifo = scratch.path + "/a fifo.gcm"
        #expect(mkfifo(fifo, 0o600) == 0)
        let png = scratch.path + "/banner.png"

        let fromFolder = runDumpBanner(["--dump-banner", folder, png])
        #expect(fromFolder.status == 1)
        #expect(fromFolder.stderr == "\(folder): is a folder, not a disc image\n")
        let fromFIFO = runDumpBanner(["--dump-banner", fifo, png])
        #expect(fromFIFO.status == 1)
        #expect(fromFIFO.stderr == "\(fifo): isn't a regular file, so it isn't a disc image\n")
        #expect(!FileManager.default.fileExists(atPath: png))
    }

    @Test func aPNGThatCantBeWrittenExits1() {
        let fs = world()
        fs.failWrites(with: POSIXError(.EACCES))
        let result = runDumpBanner(["--dump-banner", discPath, out], fs: fs)
        #expect(result.status == 1)
        #expect(result.stdout == "")
        #expect(result.stderr.hasPrefix("\(out): can't be written ("))
    }

    @Test(arguments: [
        [String](), ["--dump-banner"], ["--dump-banner", "a"], ["--dump-banner", "a", "b", "c"],
        ["--check-disc", "a", "b"], ["a", "--dump-banner", "b"],
    ])
    func badArgumentsPrintUsageAndExit2(_ arguments: [String]) {
        let fs = world()
        let result = runDumpBanner(arguments, fs: fs)
        #expect(result == CommandResult(
            stdout: "", stderr: "usage: Dragoon --dump-banner DISC OUT.png\n", status: 2))
        #expect(fs.writes.isEmpty)
    }
}
