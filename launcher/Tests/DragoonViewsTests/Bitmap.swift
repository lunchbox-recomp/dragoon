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

    func write(to url: URL) throws {
        try PNGEncoder.encode(self).write(to: url)
    }
}
