import DragoonCore
import Foundation
import Testing

@Suite struct LogTailTests {
    @Test func theLastLinesAreShownOldestFirstWithoutBlankOnes() {
        let fs = FakeFileSystem()
        let lines = (1...30).map { "line \($0)" }
        fs.addFile(flowLog, Data((lines.joined(separator: "\n") + "\n\n   \n").utf8))
        #expect(LogTail.lineCount == 20)
        #expect(LogTail.lastLines(of: flowLog, fs: fs) == Array(lines.suffix(20)))
        #expect(LogTail.lastLines(of: flowLog, count: 2, fs: fs) == ["line 29", "line 30"])
    }

    @Test func aLogThatCantBeReadHasNoLines() {
        #expect(LogTail.lastLines(of: flowLog, fs: FakeFileSystem()) == [])
    }
}
