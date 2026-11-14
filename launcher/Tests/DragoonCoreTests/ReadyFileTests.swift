@testable import DragoonCore
import Foundation
import Testing

private func marks(_ text: String) -> ReadyMarks {
    ReadyMarks.parse(Data(text.utf8))
}

/// `GCN_READY_FILE`'s lines as the engine writes them, `<word> <ms>` and a newline each
/// (gcn-recomp `runtime/ready_file.h`), and what's made of anything else.
@Suite struct ReadyFileTests {
    @Test func anEmptyFileHasNoMarks() {
        #expect(marks("") == ReadyMarks())
        #expect(!marks("").isComplete)
    }

    @Test func theWindowLineAlone() {
        #expect(marks("window 412\n") == ReadyMarks(window: 412))
    }

    @Test func bothLines() {
        let both = marks("window 412\nframe 1093\n")
        #expect(both == ReadyMarks(window: 412, frame: 1093))
        #expect(both.isComplete)
    }

    /// A line with no newline yet is left for the next read.
    @Test(arguments: ["window 41", "window", "window 412\nframe 10", "window 412\nfr"])
    func aLineWithNoNewlineDoesNotCount(_ text: String) {
        let found = marks(text)
        #expect(found.frame == nil)
        #expect(found.window == (text.hasPrefix("window 412\n") ? 412 : nil))
    }

    @Test(arguments: [
        "window\n", "window \n", "window  412\n", " window 412\n", "window 412 \n", "window -4\n",
        "window +4\n", "window 4.5\n", "window 0x10\n", "Window 412\n", "windows 412\n",
        "window 412\r\n", "window\t412\n", "window 99999999999999999999\n", "\n", "launch 0\n",
    ])
    func aLineThatIsNotAWordASpaceAndMillisecondsIsSkipped(_ text: String) {
        #expect(marks(text) == ReadyMarks())
        #expect(marks(text + "frame 7\n") == ReadyMarks(frame: 7))
    }

    @Test func bytesThatAreNotTextAreSkipped() {
        var bytes = Data([0xFF, 0xFE, 0x00, 0x0A])
        bytes.append(Data("window 5\n".utf8))
        #expect(ReadyMarks.parse(bytes) == ReadyMarks(window: 5))
    }

    /// Each word goes in once, so a second is someone else's and the first stands.
    @Test func theFirstLineForAWordIsKept() {
        #expect(marks("window 5\nwindow 9\nframe 7\nframe 8\n") == ReadyMarks(window: 5, frame: 7))
    }

    @Test func linesComeInAnyOrderAndUnknownWordsAreLeftAlone() {
        #expect(marks("launch 0\nframe 30\nsplash 2\nwindow 12\n") == ReadyMarks(window: 12, frame: 30))
    }

    @Test func zeroMillisecondsCounts() {
        #expect(marks("window 0\nframe 0\n") == ReadyMarks(window: 0, frame: 0))
    }

    @Test func aFileThatIsNotThereReadsAsNothing() throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        #expect(ReadyFile.read(at: scratch.path + "/ready.txt") == nil)
    }

    @Test func aFileOnDiskIsReadAndParsed() throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        let path = scratch.path + "/ready.txt"
        try Data("window 412\nframe 10".utf8).write(to: URL(fileURLWithPath: path))
        #expect(ReadyFile.read(at: path) == ReadyMarks(window: 412))
    }

    /// Only the first `ReadyFile.limit` bytes are read, so a runaway file costs nothing.
    @Test func onlyTheStartOfALongFileIsRead() throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        let path = scratch.path + "/ready.txt"
        let filler = String(repeating: "x", count: ReadyFile.limit) + "\n"
        try Data((filler + "window 1\n").utf8).write(to: URL(fileURLWithPath: path))
        #expect(ReadyFile.read(at: path) == ReadyMarks())
        try Data(("window 1\n" + filler).utf8).write(to: URL(fileURLWithPath: path))
        #expect(ReadyFile.read(at: path) == ReadyMarks(window: 1))
    }

    /// A link at the path isn't followed and a folder isn't read.
    @Test func aLinkOrAFolderReadsAsNothing() throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        let elsewhere = scratch.path + "/elsewhere.txt"
        try Data("window 1\n".utf8).write(to: URL(fileURLWithPath: elsewhere))
        let link = scratch.path + "/ready.txt"
        try FileManager.default.createSymbolicLink(atPath: link, withDestinationPath: elsewhere)
        #expect(ReadyFile.read(at: link) == nil)
        let folder = scratch.path + "/a folder"
        try FileManager.default.createDirectory(atPath: folder, withIntermediateDirectories: true)
        #expect(ReadyFile.read(at: folder) == nil)
    }

    @Test func removeTakesTheFileAndTheEnginesTemporaryOne() throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        let path = scratch.path + "/ready.txt"
        for name in [path, path + ".tmp", scratch.path + "/other.txt"] {
            try Data("window 1\n".utf8).write(to: URL(fileURLWithPath: name))
        }
        ReadyFile.remove(path, fs: SystemFileSystem())
        #expect(!FileManager.default.fileExists(atPath: path))
        #expect(!FileManager.default.fileExists(atPath: path + ".tmp"))
        #expect(FileManager.default.fileExists(atPath: scratch.path + "/other.txt"))
    }
}
