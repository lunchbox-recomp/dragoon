import CoreGraphics
import Foundation
import ImageIO

/// An opaque image as 8-bit sRGB, four bytes a pixel with the fourth unused, row by row.
struct Bitmap: Equatable {
    let width: Int
    let height: Int
    let bytes: [UInt8]

    static let sRGB = CGColorSpace(name: CGColorSpace.sRGB)!

    init(width: Int, height: Int, bytes: [UInt8]) {
        precondition(bytes.count == width * height * 4)
        self.width = width
        self.height = height
        self.bytes = bytes
    }

    /// `image` drawn into an sRGB bitmap with no alpha, or nil when Core Graphics can't.
    init?(_ image: CGImage) {
        let width = image.width, height = image.height
        var bytes = [UInt8](repeating: 0, count: width * height * 4)
        let drawn = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress, width: width, height: height, bitsPerComponent: 8,
                bytesPerRow: width * 4, space: Bitmap.sRGB,
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)
            else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard drawn else { return nil }
        self.width = width
        self.height = height
        self.bytes = bytes
    }

    /// How many pixels differ from `other`'s by more than `tolerance` in a color channel, or
    /// nil when the two aren't the same size.
    func differingPixels(from other: Bitmap, tolerance: Int) -> Int? {
        guard width == other.width, height == other.height else { return nil }
        // The same Mac renders the same bytes, and comparing them whole is fast in a debug build.
        if bytes == other.bytes { return 0 }
        var count = 0
        for pixel in stride(from: 0, to: bytes.count, by: 4) {
            for channel in pixel..<pixel + 3
            where abs(Int(bytes[channel]) - Int(other.bytes[channel])) > tolerance {
                count += 1
                break
            }
        }
        return count
    }

    /// The PNG at `url`, or nil when there's none or it can't be read.
    static func read(_ url: URL) -> Bitmap? {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
            let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
        else { return nil }
        return Bitmap(image)
    }

    /// Half the width and height, each pixel the mean of the 2x2 block it covers. An odd last
    /// row or column is dropped.
    func halved() -> Bitmap {
        let half = (width: width / 2, height: height / 2)
        var out = [UInt8](repeating: 0, count: half.width * half.height * 4)
        for y in 0..<half.height {
            for x in 0..<half.width {
                for channel in 0..<4 {
                    let at = { (dx: Int, dy: Int) in
                        Int(bytes[((2 * y + dy) * width + 2 * x + dx) * 4 + channel])
                    }
                    let sum = at(0, 0) + at(1, 0) + at(0, 1) + at(1, 1)
                    out[(y * half.width + x) * 4 + channel] = UInt8((sum + 2) / 4)
                }
            }
        }
        return Bitmap(width: half.width, height: half.height, bytes: out)
    }

    /// Each color channel rounded to the nearest multiple of `step`, at most 255. A gradient
    /// SwiftUI dithers is noise in the low bits, which deflate can't shrink.
    func rounded(to step: Int) -> Bitmap {
        let rounded = bytes.map { UInt8(min(255, (Int($0) + step / 2) / step * step)) }
        return Bitmap(width: width, height: height, bytes: rounded)
    }

    func write(to url: URL) throws {
        try PNGEncoder.encode(self).write(to: url)
    }
}
