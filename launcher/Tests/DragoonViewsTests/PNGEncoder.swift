import Foundation
import zlib

/// Writes a `Bitmap` as an 8-bit RGB PNG. ImageIO's encoder deflates at its fastest level and
/// leaves even a flat 1920x1200 screen at 33 KB. Here every row is Paeth-filtered and the macOS
/// SDK's zlib deflates at level 9, which brings the snapshots to about two thirds of ImageIO's
/// size. Choosing a filter for each row saved 6% more and made recording 4 times slower.
enum PNGEncoder {
    enum Failure: Error {
        case deflate(Int32)
    }

    static func encode(_ bitmap: Bitmap) throws -> Data {
        var png = Data([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        var header = Data()
        header.appendBigEndian(UInt32(bitmap.width))
        header.appendBigEndian(UInt32(bitmap.height))
        // 8 bits a channel, RGB, deflate, adaptive filtering, no interlace.
        header.append(contentsOf: [8, 2, 0, 0, 0])
        png.appendChunk("IHDR", header)
        png.appendChunk("sRGB", Data([0]))
        png.appendChunk("IDAT", try deflate(filtered(bitmap)))
        png.appendChunk("IEND", Data())
        return png
    }

    /// Each row as the Paeth filter's type byte, 4, and its RGB bytes less their predictions.
    static func filtered(_ bitmap: Bitmap) -> [UInt8] {
        let stride = bitmap.width * 3
        var rgb = [UInt8](repeating: 0, count: stride * bitmap.height)
        for pixel in 0..<bitmap.width * bitmap.height {
            for channel in 0..<3 { rgb[pixel * 3 + channel] = bitmap.bytes[pixel * 4 + channel] }
        }
        var out = [UInt8](repeating: 0, count: (stride + 1) * bitmap.height)
        for row in 0..<bitmap.height {
            out[row * (stride + 1)] = 4
            for x in 0..<stride {
                let i = row * stride + x
                let a = x >= 3 ? Int(rgb[i - 3]) : 0
                let b = row > 0 ? Int(rgb[i - stride]) : 0
                let c = x >= 3 && row > 0 ? Int(rgb[i - stride - 3]) : 0
                out[row * (stride + 1) + 1 + x] = rgb[i] &- UInt8(paeth(a, b, c))
            }
        }
        return out
    }

    static func paeth(_ a: Int, _ b: Int, _ c: Int) -> Int {
        let p = a + b - c
        let pa = abs(p - a), pb = abs(p - b), pc = abs(p - c)
        if pa <= pb && pa <= pc { return a }
        return pb <= pc ? b : c
    }

    /// `bytes` as a zlib stream at level 9.
    static func deflate(_ bytes: [UInt8]) throws -> Data {
        var size = compressBound(uLong(bytes.count))
        var out = [UInt8](repeating: 0, count: Int(size))
        let status = compress2(&out, &size, bytes, uLong(bytes.count), 9)
        guard status == Z_OK else { throw Failure.deflate(status) }
        return Data(out[0..<Int(size)])
    }
}

extension Data {
    fileprivate mutating func appendBigEndian(_ value: UInt32) {
        append(contentsOf: [24, 16, 8, 0].map { UInt8(truncatingIfNeeded: value >> $0) })
    }

    fileprivate mutating func appendChunk(_ type: String, _ body: Data) {
        let typed = Data(type.utf8) + body
        appendBigEndian(UInt32(body.count))
        append(typed)
        let crc = typed.withUnsafeBytes { buffer in
            crc32(0, buffer.bindMemory(to: Bytef.self).baseAddress, uInt(buffer.count))
        }
        appendBigEndian(UInt32(crc))
    }
}
