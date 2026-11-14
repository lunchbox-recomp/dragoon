import Foundation
import ImageIO

/// A GameCube disc's banner: the `opening.bnr` file on the root of its file system, holding a
/// 96 x 32 picture and the game's name and maker.
///
/// The layout follows Dolphin (GPL-2.0-or-later, read at 44e0c56, none of its code used):
/// the file system table in `DiscIO/DiscUtils.cpp` and `FileSystemGCWii.cpp`, the banner in
/// `VolumeGC.h` and `VolumeGC.cpp`, and the pixels in `Common/ColorUtil.cpp`. Dolphin lays the
/// pixels onto black, and this keeps their alpha.
public struct DiscBanner: Equatable, Sendable {
    public static let width = 96
    public static let height = 32

    /// BNR1 has one info block, as US and Japanese discs do. BNR2 has six, one per language, as
    /// PAL discs do.
    public enum Format: String, Sendable {
        case bnr1 = "BNR1"
        case bnr2 = "BNR2"
    }

    /// One info block's strings, each cut at its first NUL.
    public struct Text: Equatable, Sendable {
        public var shortName: String
        public var shortMaker: String
        public var longName: String
        public var longMaker: String
        /// Two lines split by a newline.
        public var description: String

        public init(
            shortName: String, shortMaker: String, longName: String, longMaker: String,
            description: String
        ) {
            self.shortName = shortName
            self.shortMaker = shortMaker
            self.longName = longName
            self.longMaker = longMaker
            self.description = description
        }
    }

    public let format: Format
    /// `width` x `height` pixels row by row from the top left, four bytes each, red, green, blue
    /// and alpha, with the color not multiplied by the alpha.
    public let rgba: [UInt8]
    /// One for a BNR1 and six for a BNR2, in the file's order.
    public let texts: [Text]
    /// The file as the disc holds it.
    public let bytes: Data

    /// Decodes an `opening.bnr`. `discID` is the ID of the disc it came from, whose fourth
    /// character picks the strings' encoding: Shift-JIS for a Japanese disc (`J`) and
    /// Windows-1252 for the rest. Nil unless the magic and the size are BNR1's or BNR2's.
    public init?(bytes: Data, discID: String) {
        self.init(bytes: bytes, japanese: discID.utf8.dropFirst(3).first == UInt8(ascii: "J"))
    }

    /// The banner of the disc image at `path`, plain or CISO, or nil when it has none that can
    /// be read. It reads the disc's header, its file system table and the banner, and nothing
    /// else.
    public static func read(at path: String, fs: any FileSystem) -> DiscBanner? {
        guard let file = try? fs.openReader(at: path) else { return nil }
        return read(from: file)
    }

    /// The banner of the disc image `file` holds, as `read(at:)` gives it.
    static func read(from file: any FileReader) -> DiscBanner? {
        try? find(in: file)
    }

    /// The pixels as an image with straight alpha, in sRGB.
    public func cgImage() -> CGImage? {
        guard let space = CGColorSpace(name: CGColorSpace.sRGB),
            let provider = CGDataProvider(data: Data(rgba) as CFData)
        else { return nil }
        return CGImage(
            width: Self.width, height: Self.height, bitsPerComponent: 8, bitsPerPixel: 32,
            bytesPerRow: Self.width * 4, space: space,
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.last.rawValue),
            provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)
    }

    /// The pixels as a PNG with straight alpha, tagged sRGB.
    public func png() -> Data? {
        guard let image = cgImage() else { return nil }
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            data, "public.png" as CFString, 1, nil)
        else { return nil }
        CGImageDestinationAddImage(destination, image, nil)
        return CGImageDestinationFinalize(destination) ? data as Data : nil
    }
}

// MARK: - Finding the file

private enum DiscLayout {
    static let headerLength = 0x440
    static let idLength = 6
    /// The file system table's offset and size, big-endian words. GameCube shifts neither.
    static let fstOffsetWord = 0x424
    static let fstSizeWord = 0x428
    static let smallestFST = 12
    static let largestFST = 1 << 20
    /// An entry is three big-endian words. Word 0's high byte says it's a directory and its
    /// low 24 bits are where its name is in the string table. For a file, word 1 is its offset
    /// on the disc and word 2 its size. For a directory, word 2 is the index past its last
    /// entry. Entry 0 is the root, whose word 2 is the entry count, and the string table
    /// follows the last entry.
    static let entryLength = 12
    static let bannerName = Array("opening.bnr".utf8) + [0]
}

extension DiscBanner {
    private static func find(in file: any FileReader) throws -> DiscBanner? {
        let plain = PlainImage(file: file)
        var header = try plain.read(at: 0, count: DiscLayout.headerLength)
        let image: any DiscBytes
        switch DiscFormat(magic: header) {
        case .needsConversion: return nil
        case .plain: image = plain
        case .ciso:
            image = try CISOImage(file: file)
            header = try image.read(at: 0, count: DiscLayout.headerLength)
        }
        let fstOffset = UInt64(bigEndianWord(header, at: DiscLayout.fstOffsetWord))
        let fstSize = Int(bigEndianWord(header, at: DiscLayout.fstSizeWord))
        guard (DiscLayout.smallestFST...DiscLayout.largestFST).contains(fstSize) else {
            return nil
        }
        let fst = [UInt8](try image.read(at: fstOffset, count: fstSize))
        guard let file = rootFile(named: DiscLayout.bannerName, in: fst),
            file.size == BannerLayout.bnr1Length || file.size == BannerLayout.bnr2Length
        else { return nil }
        let bytes = try image.read(at: UInt64(file.offset), count: file.size)
        let id = String(decoding: header.prefix(DiscLayout.idLength), as: UTF8.self)
        return DiscBanner(bytes: bytes, discID: id)
    }

    /// The offset and size of the file the root itself holds whose name is `name` (which ends
    /// in its NUL), stepping over every directory whole. Nil when there's none, or when the
    /// entry count, a name or a directory's end can't be right.
    private static func rootFile(named name: [UInt8], in fst: [UInt8])
        -> (offset: UInt32, size: Int)?
    {
        func word(_ entry: Int, _ index: Int) -> UInt32 {
            let at = entry * DiscLayout.entryLength + 4 * index
            return (at..<at + 4).reduce(0) { $0 << 8 | UInt32(fst[$1]) }
        }
        let count = Int(word(0, 2))
        let stringTable = count * DiscLayout.entryLength
        // Every name then ends inside the table.
        guard stringTable < fst.count, fst.last == 0 else { return nil }
        var entry = 1
        while entry < count {
            let first = word(entry, 0)
            if first >> 24 != 0 {
                let end = Int(word(entry, 2))
                guard end > entry else { return nil }
                entry = end
                continue
            }
            let nameAt = stringTable + Int(first & 0xFF_FFFF)
            guard nameAt < fst.count else { return nil }
            if fst[nameAt...].starts(with: name) {
                return (word(entry, 1), Int(word(entry, 2)))
            }
            entry += 1
        }
        return nil
    }
}

// MARK: - Decoding the file

private enum BannerLayout {
    static let bnr1Length = 0x1960
    static let bnr2Length = 0x1FA0
    /// Magic, then 0x1C zeros.
    static let imageAt = 0x20
    /// Big-endian RGB5A3 words in 4x4 tiles, left to right and then down, each tile's 16
    /// pixels row by row.
    static let tile = 4
    static let infoAt = 0x1820
    static let infoLength = 0x140
    /// Each string's offset and length in an info block.
    static let fields = [(0x00, 0x20), (0x20, 0x20), (0x40, 0x40), (0x80, 0x40), (0xC0, 0x80)]
}

extension DiscBanner {
    private init?(bytes: Data, japanese: Bool) {
        let raw = [UInt8](bytes)
        switch (String(decoding: raw.prefix(4), as: UTF8.self), raw.count) {
        case ("BNR1", BannerLayout.bnr1Length): format = .bnr1
        case ("BNR2", BannerLayout.bnr2Length): format = .bnr2
        default: return nil
        }
        rgba = Self.decodePixels(raw)
        texts = stride(from: BannerLayout.infoAt, to: raw.count, by: BannerLayout.infoLength).map {
            block in
            let strings = BannerLayout.fields.map { offset, length in
                Self.decodeString(raw[block + offset..<block + offset + length], japanese: japanese)
            }
            return Text(
                shortName: strings[0], shortMaker: strings[1], longName: strings[2],
                longMaker: strings[3], description: strings[4])
        }
        self.bytes = bytes
    }

    private static func decodePixels(_ raw: [UInt8]) -> [UInt8] {
        let tile = BannerLayout.tile
        let across = width / tile
        var rgba = [UInt8](repeating: 0, count: width * height * 4)
        for index in 0..<width * height {
            let at = BannerLayout.imageAt + 2 * index
            let (red, green, blue, alpha) = rgb5a3(UInt16(raw[at]) << 8 | UInt16(raw[at + 1]))
            let inTile = index % (tile * tile)
            let tileNumber = index / (tile * tile)
            let x = tileNumber % across * tile + inTile % tile
            let y = tileNumber / across * tile + inTile / tile
            let out = (y * width + x) * 4
            rgba[out] = red
            rgba[out + 1] = green
            rgba[out + 2] = blue
            rgba[out + 3] = alpha
        }
        return rgba
    }

    /// With bit 15 set, RGB555 and opaque. Without it, 3 bits of alpha and RGB444. Each channel
    /// widens to 8 bits by repeating its high bits in the low ones.
    private static func rgb5a3(_ value: UInt16) -> (UInt8, UInt8, UInt8, UInt8) {
        func five(_ bits: UInt16) -> UInt8 {
            let bits = UInt8(bits & 0x1F)
            return bits << 3 | bits >> 2
        }
        func four(_ bits: UInt16) -> UInt8 { UInt8(bits & 0xF) * 17 }
        func three(_ bits: UInt16) -> UInt8 {
            let bits = UInt8(bits & 0x7)
            return bits << 5 | bits << 2 | bits >> 1
        }
        if value & 0x8000 != 0 {
            return (five(value >> 10), five(value >> 5), five(value), 255)
        }
        return (four(value >> 8), four(value >> 4), four(value), three(value >> 12))
    }

    private static func decodeString(_ field: ArraySlice<UInt8>, japanese: Bool) -> String {
        let text = Data(field.prefix { $0 != 0 })
        if japanese { return String(data: text, encoding: .shiftJIS) ?? "" }
        // Latin-1 decodes any byte, for the five Windows-1252 leaves undefined.
        return String(data: text, encoding: .windowsCP1252)
            ?? String(data: text, encoding: .isoLatin1) ?? ""
    }
}
