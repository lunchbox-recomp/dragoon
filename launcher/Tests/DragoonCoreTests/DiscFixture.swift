import Foundation

// Disc images the tests write. Every byte is made up here, and none comes from a game.

/// A CISO block size small enough that a test image spans a few blocks.
let testBlockSize = 0x1000

func be16(_ value: UInt16) -> [UInt8] {
    [UInt8(value >> 8), UInt8(value & 0xFF)]
}

func be32(_ value: UInt32) -> [UInt8] {
    [UInt8(value >> 24), UInt8((value >> 16) & 0xFF), UInt8((value >> 8) & 0xFF), UInt8(value & 0xFF)]
}

func le32(_ value: UInt32) -> [UInt8] {
    Array(be32(value).reversed())
}

/// The blocks of `image` that hold any nonzero byte, by block number.
func storedBlocks(of image: Data, blockSize: Int = testBlockSize) -> [Int: Data] {
    var blocks: [Int: Data] = [:]
    for start in stride(from: 0, to: image.count, by: blockSize) {
        let piece = image.subdata(in: start..<min(start + blockSize, image.count))
        if piece.contains(where: { $0 != 0 }) { blocks[start / blockSize] = piece }
    }
    return blocks
}

/// A CISO holding `blocks`, each padded to `blockSize` and stored in block order. `mapBytes` sets
/// map entries after that, for a byte that means "not stored" by some other name than 0.
func makeCISO(
    blocks: [Int: Data], blockSize: Int = testBlockSize, blockSizeField: UInt32? = nil,
    mapBytes: [Int: UInt8] = [:]
) -> Data {
    var header = Data(count: 0x8000)
    header.replaceSubrange(0..<4, with: Array("CISO".utf8))
    header.replaceSubrange(4..<8, with: le32(blockSizeField ?? UInt32(blockSize)))
    var body = Data()
    for block in blocks.keys.sorted() {
        header[8 + block] = 1
        var bytes = blocks[block]!
        bytes.append(Data(count: blockSize - bytes.count))
        body.append(bytes)
    }
    for (block, byte) in mapBytes { header[8 + block] = byte }
    return header + body
}

func makeCISO(from image: Data, blockSizeField: UInt32? = nil, mapBytes: [Int: UInt8] = [:])
    -> Data
{
    makeCISO(blocks: storedBlocks(of: image), blockSizeField: blockSizeField, mapBytes: mapBytes)
}

// MARK: A file system tree

/// A file or a directory in a disc's file system table.
indirect enum DiscNode {
    case file(String, Data)
    case directory(String, [DiscNode])
}

/// A disc image with a file system table. Built with `makeDisc`, and changed by a test that
/// wants a broken one.
struct DiscFixture {
    var image: Data
    var fstOffset: Int
    var fstSize: Int
    /// Entry count times 12, where the names start.
    var stringTable: Int
    /// Where each node's 12-byte entry is in the image, by its name, with the root's at
    /// `fstOffset`. A name used twice keeps the last.
    var entries: [String: Int]
    /// Where each file's bytes are in the image, by its name.
    var files: [String: Int]

    /// Puts `value` as a big-endian word at `offset` in the image.
    mutating func poke(_ offset: Int, _ value: UInt32) {
        image.replaceSubrange(offset..<offset + 4, with: be32(value))
    }
}

/// A disc whose first 6 bytes are `id` and whose file system table, at `fstOffset`, lists
/// `root`'s nodes, as the GameCube lays them out: entry 0 is the root, each directory's entries
/// follow it, and its word 2 is the index past its last one. The files' bytes come after the
/// table, each at a multiple of 0x800, and `tail` zeros end the image.
func makeDisc(
    id: String = "GKYE01", root: [DiscNode], fstOffset: Int = 0x2000, tail: Int = 0x800
) -> DiscFixture {
    var entries: [(name: String, directory: Bool, nameAt: Int, parent: Int, end: Int, data: Data)]
        = []
    var names = Data([0])  // the root's name, which nothing reads
    func add(_ nodes: [DiscNode], parent: Int) {
        for node in nodes {
            let index = entries.count
            switch node {
            case .file(let name, let data):
                entries.append((name, false, names.count, parent, 0, data))
                names.append(contentsOf: Array(name.utf8) + [0])
            case .directory(let name, let children):
                entries.append((name, true, names.count, parent, 0, Data()))
                names.append(contentsOf: Array(name.utf8) + [0])
                add(children, parent: index)
                entries[index].end = entries.count
            }
        }
    }
    entries.append(("", true, 0, 0, 0, Data()))
    add(root, parent: 0)
    entries[0].end = entries.count

    let stringTable = entries.count * 12
    let fstSize = stringTable + names.count
    var dataAt = (fstOffset + fstSize + 0x7FF) & ~0x7FF
    var fst = Data()
    var files: [String: Int] = [:]
    var entryAt: [String: Int] = [:]
    for (index, entry) in entries.enumerated() {
        entryAt[entry.name] = fstOffset + 12 * index
        if entry.directory {
            fst.append(contentsOf: be32(0x0100_0000 | UInt32(entry.nameAt)))
            fst.append(contentsOf: be32(UInt32(entry.parent)))
            fst.append(contentsOf: be32(UInt32(entry.end)))
        } else {
            fst.append(contentsOf: be32(UInt32(entry.nameAt)))
            fst.append(contentsOf: be32(UInt32(dataAt)))
            fst.append(contentsOf: be32(UInt32(entry.data.count)))
            files[entry.name] = dataAt
            dataAt = (dataAt + entry.data.count + 0x7FF) & ~0x7FF
        }
    }
    fst.append(names)

    var image = Data(count: dataAt + tail)
    image.replaceSubrange(0..<6, with: Array(id.utf8))
    image.replaceSubrange(0x20..<0x28, with: Array("TESTDISC".utf8))
    image.replaceSubrange(0x424..<0x428, with: be32(UInt32(fstOffset)))
    image.replaceSubrange(0x428..<0x42C, with: be32(UInt32(fstSize)))
    image.replaceSubrange(fstOffset..<fstOffset + fstSize, with: fst)
    for entry in entries where !entry.directory {
        let at = files[entry.name]!
        image.replaceSubrange(at..<at + entry.data.count, with: entry.data)
    }
    return DiscFixture(
        image: image, fstOffset: fstOffset, fstSize: fstSize, stringTable: stringTable,
        entries: entryAt, files: files)
}

// MARK: Banners

/// The five strings of one banner info block, as bytes so a test can write any encoding.
struct BannerText {
    var shortName: [UInt8] = Array("Test Ride".utf8)
    var shortMaker: [UInt8] = Array("Test Maker".utf8)
    var longName: [UInt8] = Array("Test Ride: The Long Name".utf8)
    var longMaker: [UInt8] = Array("Test Maker Co.".utf8)
    var description: [UInt8] = Array("Line one\nLine two".utf8)
}

let bannerPixelCount = 96 * 32

/// An `opening.bnr`: `magic`, 0x1C zeros, `pixels` as big-endian words in the order the file
/// keeps them (tile by tile), then one 0x140-byte info block per `texts` entry, each string
/// NUL-padded to its field.
func makeBNR(
    magic: String = "BNR1", pixels: [UInt16] = Array(repeating: 0, count: 96 * 32),
    texts: [BannerText] = [BannerText()]
) -> Data {
    var bytes = Data(Array(magic.utf8))
    bytes.append(Data(count: 0x20 - bytes.count))
    for pixel in pixels { bytes.append(contentsOf: be16(pixel)) }
    func field(_ text: [UInt8], _ length: Int) -> Data {
        var data = Data(text.prefix(length))
        data.append(Data(count: length - data.count))
        return data
    }
    for text in texts {
        bytes.append(field(text.shortName, 0x20))
        bytes.append(field(text.shortMaker, 0x20))
        bytes.append(field(text.longName, 0x40))
        bytes.append(field(text.longMaker, 0x40))
        bytes.append(field(text.description, 0x80))
    }
    return bytes
}

/// Six info blocks with names that tell them apart, for a BNR2.
let sixTexts = (0..<6).map { index in
    BannerText(
        shortName: Array("Name \(index)".utf8), shortMaker: Array("Maker \(index)".utf8),
        longName: Array("Long Name \(index)".utf8), longMaker: Array("Long Maker \(index)".utf8),
        description: Array("Text \(index)".utf8))
}

/// Every pixel opaque and each one different, so where any one lands can be told apart.
let distinctPixels = (0..<96 * 32).map { UInt16(0x8000 | $0) }
