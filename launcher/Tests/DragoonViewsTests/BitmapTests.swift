import Foundation
import Testing

/// A 3x2 bitmap with every color channel different, so a filter or a channel that's dropped
/// shows.
private let pattern = Bitmap(width: 3, height: 2, bytes: [
    0, 255, 3, 255, 40, 225, 10, 255, 80, 195, 17, 255,
    120, 165, 24, 255, 160, 135, 31, 255, 200, 105, 38, 255,
])

/// `bitmap` with one channel of one pixel moved by `by`.
private func nudged(_ bitmap: Bitmap, pixel: Int, channel: Int, by: Int) -> Bitmap {
    var bytes = bitmap.bytes
    bytes[pixel * 4 + channel] = UInt8(Int(bytes[pixel * 4 + channel]) + by)
    return Bitmap(width: bitmap.width, height: bitmap.height, bytes: bytes)
}

struct BitmapTests {
    @Test func aPNGReadsBackAsTheSamePixels() throws {
        let file = FileManager.default.temporaryDirectory
            .appendingPathComponent("Dragoon bitmap test \(UUID().uuidString).png")
        defer { try? FileManager.default.removeItem(at: file) }
        try pattern.write(to: file)
        #expect(Bitmap.read(file) == pattern)
    }

    @Test func aMissingPNGReadsAsNothing() {
        #expect(Bitmap.read(URL(fileURLWithPath: "/nonexistent/Dragoon snapshot.png")) == nil)
    }

    @Test func onlyAChannelPastTheToleranceCounts() {
        let tolerance = Snapshot.channelTolerance
        #expect(pattern.differingPixels(from: pattern, tolerance: tolerance) == 0)
        for channel in 0..<3 {
            let within = nudged(pattern, pixel: 4, channel: channel, by: tolerance)
            let past = nudged(pattern, pixel: 4, channel: channel, by: tolerance + 1)
            #expect(pattern.differingPixels(from: within, tolerance: tolerance) == 0)
            #expect(pattern.differingPixels(from: past, tolerance: tolerance) == 1)
        }
    }

    @Test func aPixelCountsOnceHoweverManyChannelsDiffer() {
        let twice = nudged(nudged(pattern, pixel: 1, channel: 0, by: 50), pixel: 1, channel: 2, by: 50)
        let two = nudged(twice, pixel: 5, channel: 1, by: -50)
        #expect(pattern.differingPixels(from: two, tolerance: Snapshot.channelTolerance) == 2)
    }

    @Test func theUnusedByteNeverCounts() {
        let padded = nudged(pattern, pixel: 0, channel: 3, by: -200)
        #expect(pattern.differingPixels(from: padded, tolerance: Snapshot.channelTolerance) == 0)
    }

    @Test func halvingAveragesEachBlockAndDropsAnOddEdge() {
        // 3x2: the first two columns make one pixel, and the third is dropped.
        let half = pattern.halved()
        #expect(half.width == 1 && half.height == 1)
        // (0 + 40 + 120 + 160) / 4, (255 + 225 + 165 + 135) / 4, (3 + 10 + 24 + 31) / 4 = 17.
        #expect(Array(half.bytes.prefix(3)) == [80, 195, 17])
        let rounding = Bitmap(width: 2, height: 2, bytes: [1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        #expect(rounding.halved().bytes[0] == 1)
    }

    @Test func roundingKeepsEachChannelWithinHalfAStep() {
        let ramp = Bitmap(width: 64, height: 1, bytes: (0..<256).map { UInt8($0) })
        let rounded = ramp.rounded(to: Snapshot.recordStep)
        for (before, after) in zip(ramp.bytes, rounded.bytes) {
            #expect(Int(after) % Snapshot.recordStep == 0 || after == 255)
            #expect(abs(Int(after) - Int(before)) <= Snapshot.recordStep / 2)
        }
        #expect(ramp.differingPixels(from: rounded, tolerance: Snapshot.recordStep / 2) == 0)
    }

    @Test func anotherSizeIsNoComparison() {
        let wide = Bitmap(width: 6, height: 1, bytes: pattern.bytes)
        #expect(pattern.differingPixels(from: wide, tolerance: Snapshot.channelTolerance) == nil)
    }
}
