import DragoonCore
import Foundation

/// A made-up banner for the snapshots, never a real disc's: an orange capsule with teal
/// stripes and a white rim on a clear background, under a soft shadow.
enum TestBanner {
    static let banner = DiscBanner(bytes: bnr(), discID: "TSTE01")!

    /// Whether (x, y) is inside a capsule `inset` pixels in from the banner's edges.
    private static func inCapsule(_ x: Int, _ y: Int, inset: Int) -> Bool {
        let top = 3 + inset, bottom = 28 - inset, left = 3 + inset, right = 92 - inset
        guard (top...bottom).contains(y), (left...right).contains(x) else { return false }
        let radius = Double(bottom - top) / 2
        let middle = Double(top + bottom) / 2
        let centerX = Double(min(max(x, left + Int(radius)), right - Int(radius)))
        return hypot(Double(x) - centerX, Double(y) - middle) <= radius
    }

    /// One pixel as an RGB5A3 word.
    private static func pixel(_ x: Int, _ y: Int) -> UInt16 {
        func opaque(_ red: UInt16, _ green: UInt16, _ blue: UInt16) -> UInt16 {
            0x8000 | (red >> 3) << 10 | (green >> 3) << 5 | blue >> 3
        }
        if inCapsule(x, y, inset: 2) {
            return (x + y) / 6 % 2 == 0 ? opaque(255, 140, 40) : opaque(40, 190, 200)
        }
        if inCapsule(x, y, inset: 0) { return opaque(255, 255, 255) }
        // A shadow 2 pixels down, alpha 3 of 7, in black.
        if inCapsule(x, y - 2, inset: 0) { return 0x3000 }
        return 0
    }

    /// The BNR1 file: magic, 0x1C zeros, the pixels in 4x4 tiles and one empty info block.
    private static func bnr() -> Data {
        var bytes = Data("BNR1".utf8) + Data(count: 0x1C)
        for tileY in 0..<DiscBanner.height / 4 {
            for tileX in 0..<DiscBanner.width / 4 {
                for row in 0..<4 {
                    for column in 0..<4 {
                        let word = pixel(tileX * 4 + column, tileY * 4 + row)
                        bytes.append(contentsOf: [UInt8(word >> 8), UInt8(word & 0xFF)])
                    }
                }
            }
        }
        return bytes + Data(count: 0x140)
    }
}
