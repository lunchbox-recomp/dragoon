import CryptoKit
import DragoonCore
import Foundation
import Testing

private let kirbyID = "GKYE01"
private let home = "/Users/Test Player"
private let discPath = home + "/Games/Kirby Air Ride (USA).gcm"
private let bundledInfo = home + "/Applications/Dragoon.app/Contents/Resources/source/source-info.json"
/// A CISO block size small enough that a test image spans a few blocks.
private let testBlockSize = 0x1000
/// How many blocks a CISO header's map covers, which is 0x8000 less its eight leading bytes.
private let mapBlocks = 0x8000 - 8

// MARK: Images the tests write

private func be32(_ value: UInt32) -> [UInt8] {
    [UInt8(value >> 24), UInt8((value >> 16) & 0xFF), UInt8((value >> 8) & 0xFF), UInt8(value & 0xFF)]
}

private func le32(_ value: UInt32) -> [UInt8] {
    Array(be32(value).reversed())
}

private func sha1(_ data: Data) -> String {
    Insecure.SHA1.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

/// One entry of a DOL's section table: where the section starts in the DOL and how long it is.
private struct Section {
    var index: Int
    var offset: UInt32
    var size: UInt32
}

private let standardSections = [
    Section(index: 0, offset: 0x100, size: 0x300), Section(index: 7, offset: 0x400, size: 0x200),
]

/// A DOL of made-up bytes whose header lists `sections`, with offsets at 0x00 and sizes at 0x90.
/// Its length is the end of the section that reaches furthest, unless `length` says otherwise.
/// Bytes in `zeroed` are zero, for an image that has a whole block of zeros in its DOL.
private func makeDOL(
    _ sections: [Section] = standardSections, length: Int? = nil, seed: Int = 1,
    zeroed: Range<Int>? = nil
) -> Data {
    let ends = sections.filter { $0.size != 0 }.map { Int($0.offset) + Int($0.size) }
    let count = max(length ?? ends.max() ?? 0, 0x100)
    var bytes = (0..<count).map { UInt8(truncatingIfNeeded: ($0 &* 31 &+ seed) ^ ($0 >> 8)) }
    for index in zeroed ?? 0..<0 { bytes[index] = 0 }
    for index in 0..<0x48 { bytes[index] = 0 }
    for index in 0x90..<0xD8 { bytes[index] = 0 }
    for section in sections {
        let offsetAt = 4 * section.index
        let sizeAt = 0x90 + 4 * section.index
        bytes.replaceSubrange(offsetAt..<offsetAt + 4, with: be32(section.offset))
        bytes.replaceSubrange(sizeAt..<sizeAt + 4, with: be32(section.size))
    }
    return Data(bytes)
}

/// A disc image: the ID, then the DOL's offset as a big-endian word at 0x420, the DOL there, and
/// zeros for `tail` bytes after it.
private func makeISO(
    id: [UInt8] = Array(kirbyID.utf8), dol: Data, dolOffset: Int = 0x3000, tail: Int = 0x1000
) -> Data {
    var image = Data(count: dolOffset + dol.count + tail)
    image.replaceSubrange(0..<id.count, with: id)
    image.replaceSubrange(0x20..<0x28, with: Array("TESTDISC".utf8))
    image.replaceSubrange(0x420..<0x424, with: be32(UInt32(dolOffset)))
    image.replaceSubrange(dolOffset..<dolOffset + dol.count, with: dol)
    return image
}

/// The blocks of `image` that hold any nonzero byte, by block number.
private func storedBlocks(of image: Data, blockSize: Int = testBlockSize) -> [Int: Data] {
    var blocks: [Int: Data] = [:]
    for start in stride(from: 0, to: image.count, by: blockSize) {
        let piece = image.subdata(in: start..<min(start + blockSize, image.count))
        if piece.contains(where: { $0 != 0 }) { blocks[start / blockSize] = piece }
    }
    return blocks
}

/// A CISO holding `blocks`, each padded to `blockSize` and stored in block order. `mapBytes` sets
/// map entries after that, for a byte that means "not stored" by some other name than 0.
private func makeCISO(
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

private func makeCISO(from image: Data, blockSizeField: UInt32? = nil, mapBytes: [Int: UInt8] = [:])
    -> Data
{
    makeCISO(blocks: storedBlocks(of: image), blockSizeField: blockSizeField, mapBytes: mapBytes)
}

/// The bytes a disc in `format` starts with, as Dolphin reads them, and then junk.
private func compressedImage(_ format: UnsupportedDiscFormat, junk: Int = 0x500) -> Data {
    let magic: [UInt8]
    switch format {
    case .rvz: magic = Array("RVZ".utf8) + [0x01]
    case .wia: magic = Array("WIA".utf8) + [0x01]
    case .gcz: magic = [0x01, 0xC0, 0x0B, 0xB1]
    case .wbfs: magic = Array("WBFS".utf8)
    }
    return Data(magic + (0..<junk).map { UInt8(truncatingIfNeeded: $0 &+ 7) })
}

// MARK: Running the check

/// A DOL laid out so that, at 0x3000 in an image of 4 KiB blocks, one whole block of it is zeros.
private let zeroBlockDOL = makeDOL(
    [Section(index: 0, offset: 0x100, size: 0x2F00)], zeroed: 0x1000..<0x2000)
private let standardDOL = makeDOL()
private let standardISO = makeISO(dol: standardDOL)
private let standardDOLEnd = 0x3000 + standardDOL.count

private func check(_ image: Data, expecting dol: Data, id: String = kirbyID) -> DiscCheck {
    let fs = FakeFileSystem()
    fs.addFile(discPath, image)
    return checkDisc(at: discPath, expectedID: id, expectedDOLSHA1: sha1(dol), fs: fs)
}

private func isUnreadable(_ check: DiscCheck) -> Bool {
    if case .unreadable = check { return true }
    return false
}

private func isWrongGame(_ check: DiscCheck) -> Bool {
    if case .wrongGame = check { return true }
    return false
}

// MARK: Tests

@Suite struct DiscImageTests {
    @Test func anISOWithTheExpectedIDAndDOLIsOK() {
        #expect(check(standardISO, expecting: standardDOL) == .ok)
    }

    @Test func aCISOOfTheSameImageIsOK() {
        #expect(check(makeCISO(from: standardISO), expecting: standardDOL) == .ok)
    }

    @Test func aCISOBlockThatIsNotStoredReadsAsZeros() {
        let iso = makeISO(dol: zeroBlockDOL)
        #expect(storedBlocks(of: iso)[4] == nil)
        let ciso = makeCISO(from: iso)
        #expect(check(iso, expecting: zeroBlockDOL) == .ok)
        #expect(check(ciso, expecting: zeroBlockDOL) == .ok)
        // The same CISO against a DOL that has bytes where the zeros are
        let filled = makeDOL([Section(index: 0, offset: 0x100, size: 0x2F00)])
        #expect(check(ciso, expecting: filled) == .wrongRevision(foundSHA1: sha1(zeroBlockDOL)))
    }

    @Test(arguments: [UInt8(2), 0x80, 0xFF])
    func aCISOMapByteOtherThanOneMeansNotStored(_ byte: UInt8) {
        let iso = makeISO(dol: zeroBlockDOL)
        // Block 4 is all zeros and so has no data in the CISO. Its map entry says "not stored"
        // some way other than 0, and the blocks after it must still be found where they are.
        let ciso = makeCISO(from: iso, mapBytes: [4: byte])
        #expect(check(ciso, expecting: zeroBlockDOL) == .ok)
    }

    @Test func aCISOFindsABlockByItsPlaceAmongTheStoredOnesNotByItsNumber() {
        // Blocks 1 and 2 of the image are zeros, so block 3 is the second stored block.
        let iso = makeISO(dol: standardDOL)
        let stored = storedBlocks(of: iso)
        #expect(stored[1] == nil && stored[2] == nil && stored[3] != nil)
        #expect(check(makeCISO(from: iso), expecting: standardDOL) == .ok)
    }

    @Test func aCISOReadThatStartsInsideABlockCrossesAnUnstoredBlockAtTheRightPlace() {
        // The DOL starts 0x80 into block 3 and ends 0x580 into block 4, so every read of it starts
        // mid-block, as it does in a real CISO whose blocks are 2 MiB. Block 4 is all zeros and
        // so isn't stored.
        let dol = makeDOL([Section(index: 0, offset: 0x100, size: 0x1400)], zeroed: 0xF80..<0x1500)
        #expect(dol.count == 0x1500)
        let iso = makeISO(dol: dol, dolOffset: 0x3080, tail: 0x6000 - 0x3080 - 0x1500)
        #expect(iso.count == 0x6000)
        let stored = storedBlocks(of: iso)
        #expect(stored[3] != nil && stored[4] == nil)
        #expect(check(iso, expecting: dol) == .ok)
        #expect(check(makeCISO(from: iso), expecting: dol) == .ok)
    }

    @Test func aCISOOfAnotherGameIsWrongGame() {
        let ciso = makeCISO(from: makeISO(id: Array("GMSE01".utf8), dol: standardDOL))
        #expect(check(ciso, expecting: standardDOL) == .wrongGame(foundID: "GMSE01"))
    }

    @Test func aCISOWithABlockSizeOfZeroIsUnreadable() {
        let result = check(makeCISO(from: standardISO, blockSizeField: 0), expecting: standardDOL)
        #expect(isUnreadable(result), "\(result)")
    }

    @Test(arguments: [0x8000 - 1, 0x1000, 0x8, 0x4])
    func aCISOWithAShortHeaderIsUnreadable(_ cut: Int) {
        let result = check(Data(makeCISO(from: standardISO).prefix(cut)), expecting: standardDOL)
        #expect(isUnreadable(result), "\(result)")
    }

    @Test func aCISOWhoseLastStoredBlockIsCutShortIsUnreadable() {
        let ciso = makeCISO(from: makeISO(dol: zeroBlockDOL))
        #expect(check(ciso, expecting: zeroBlockDOL) == .ok)
        let result = check(Data(ciso.dropLast(0x10)), expecting: zeroBlockDOL)
        #expect(isUnreadable(result), "\(result)")
    }

    @Test func aCISOReadPastTheEndOfItsMapIsUnreadable() {
        // The DOL's first block is the last one the map covers. Its sections run on past the map,
        // where the image has no blocks to read as zeros.
        let mapEnd = mapBlocks * testBlockSize
        let dol = makeDOL([Section(index: 0, offset: 0x100, size: 0x2000)])
        var discHeader = Data(count: 0x440)
        discHeader.replaceSubrange(0..<6, with: Array(kirbyID.utf8))
        discHeader.replaceSubrange(0x420..<0x424, with: be32(UInt32(mapEnd - testBlockSize)))
        let ciso = makeCISO(blocks: [0: discHeader, mapBlocks - 1: dol.prefix(testBlockSize)])
        let result = check(ciso, expecting: dol)
        #expect(isUnreadable(result), "\(result)")
    }

    @Test func anImageOfAnotherGameIsWrongGameWithTheIDItHas() {
        let image = makeISO(id: Array("GMSE01".utf8), dol: standardDOL)
        #expect(check(image, expecting: standardDOL) == .wrongGame(foundID: "GMSE01"))
    }

    @Test func anIDThatIsntPrintableASCIIIsShownWithQuestionMarks() {
        let image = makeISO(id: [0x47, 0x00, 0xFF, 0x4D, 0x53, 0x7F], dol: standardDOL)
        #expect(check(image, expecting: standardDOL) == .wrongGame(foundID: "G??MS?"))
    }

    @Test func aDifferentRevisionOfTheSameGameIsWrongRevisionWithItsSHA1() {
        var other = standardDOL
        other[other.count - 1] ^= 0x01
        #expect(check(makeISO(dol: other), expecting: standardDOL)
                == .wrongRevision(foundSHA1: sha1(other)))
        let longer = makeDOL(standardSections + [Section(index: 8, offset: 0x600, size: 0x10)])
        #expect(check(makeISO(dol: longer), expecting: standardDOL)
                == .wrongRevision(foundSHA1: sha1(longer)))
    }

    @Test func theDOLStartsAtTheBigEndianWordAt0x420() {
        var iso = makeISO(dol: standardDOL, dolOffset: 0x3000, tail: 0x8000)
        // Other valid DOLs sit where the words either side of 0x420 point.
        let before = makeDOL(seed: 2)
        let after = makeDOL(seed: 3)
        iso.replaceSubrange(0x5000..<0x5000 + before.count, with: before)
        iso.replaceSubrange(0x7000..<0x7000 + after.count, with: after)
        iso.replaceSubrange(0x41C..<0x420, with: be32(0x5000))
        iso.replaceSubrange(0x424..<0x428, with: be32(0x7000))
        #expect(check(iso, expecting: standardDOL) == .ok)
        #expect(check(iso, expecting: before) == .wrongRevision(foundSHA1: sha1(standardDOL)))
    }

    @Test func aDOLOffsetBeyondTheEndOfTheImageIsUnreadable() {
        let image = makeISO(dol: standardDOL)
        var moved = image
        moved.replaceSubrange(0x420..<0x424, with: be32(UInt32(image.count)))
        let result = check(moved, expecting: standardDOL)
        #expect(isUnreadable(result), "\(result)")
    }

    // MARK: The length of the DOL

    @Test func theLengthIsTheLargestOffsetPlusSizeNotTheLastSectionOrTheSizesAdded() {
        let dol = makeDOL([
            Section(index: 0, offset: 0x100, size: 0x100),
            Section(index: 4, offset: 0x200, size: 0x700),
            Section(index: 9, offset: 0x180, size: 0x80),
        ])
        #expect(dol.count == 0x900)
        #expect(check(makeISO(dol: dol), expecting: dol) == .ok)
    }

    @Test func theEighteenthSectionCounts() {
        let dol = makeDOL([
            Section(index: 0, offset: 0x100, size: 0x100),
            Section(index: 17, offset: 0x200, size: 0x700),
        ])
        #expect(dol.count == 0x900)
        #expect(check(makeISO(dol: dol), expecting: dol) == .ok)
    }

    @Test func aSectionWithNoSizeIsSkippedWhateverItsOffset() {
        let dol = makeDOL(standardSections + [Section(index: 3, offset: 0x7FFF_0000, size: 0)])
        #expect(dol.count == 0x600)
        #expect(check(makeISO(dol: dol), expecting: dol) == .ok)
    }

    @Test func aSectionThatEndsPastFourGigabytesIsUnreadableNotWrappedAround() {
        // 0xFFFFF000 + 0x2000 is 0x100001000, which a 32-bit sum would wrap to 0x1000.
        let dol = makeDOL([Section(index: 0, offset: 0xFFFF_F000, size: 0x2000)], length: 0x400)
        let result = check(makeISO(dol: dol), expecting: dol)
        #expect(isUnreadable(result), "\(result)")
    }

    @Test func aDOLWithNoSectionsIsUnreadable() {
        let dol = makeDOL([])
        let result = check(makeISO(dol: dol), expecting: dol)
        #expect(isUnreadable(result), "\(result)")
    }

    // MARK: Short files

    @Test(arguments: [0, 3, 4, 0x43F, 0x440, 0x3000, 0x3080, 0x30FF, 0x3100, 0x3101, standardDOLEnd - 1])
    func aTruncatedImageIsUnreadable(_ cut: Int) {
        let result = check(Data(standardISO.prefix(cut)), expecting: standardDOL)
        #expect(isUnreadable(result), "cut at \(cut): \(result)")
    }

    @Test func anImageThatEndsAtTheDOLsLastByteIsOK() {
        #expect(check(Data(standardISO.prefix(standardDOLEnd)), expecting: standardDOL) == .ok)
    }

    @Test func aFileWithNothingInItIsUnreadable() {
        let result = check(Data(), expecting: standardDOL)
        #expect(isUnreadable(result), "\(result)")
    }

    @Test func aFileThatIsntThereIsUnreadable() {
        let result = checkDisc(
            at: discPath, expectedID: kirbyID, expectedDOLSHA1: sha1(standardDOL),
            fs: FakeFileSystem())
        #expect(isUnreadable(result), "\(result)")
    }

    @Test func aDirectoryIsUnreadable() {
        let fs = FakeFileSystem()
        fs.addDirectory(discPath)
        let result = checkDisc(
            at: discPath, expectedID: kirbyID, expectedDOLSHA1: sha1(standardDOL), fs: fs)
        #expect(isUnreadable(result), "\(result)")
    }

    // MARK: Formats the build doesn't read

    @Test(arguments: UnsupportedDiscFormat.allCases)
    func aCompressedImageNeedsConversionToWhatItsMagicSays(_ format: UnsupportedDiscFormat) {
        let image = compressedImage(format)
        #expect(check(image, expecting: standardDOL) == .needsConversion(format: format))
        // Four bytes are enough to tell, so a cut-short image is still named.
        #expect(
            check(Data(image.prefix(4)), expecting: standardDOL) == .needsConversion(format: format))
    }

    @Test(arguments: UnsupportedDiscFormat.allCases)
    func aMagicWithAnyByteChangedIsNotThatFormat(_ format: UnsupportedDiscFormat) {
        for position in 0..<4 {
            var image = compressedImage(format)
            image[position] ^= 0x20
            let result = check(image, expecting: standardDOL)
            #expect(isWrongGame(result), "byte \(position) of \(format): \(result)")
        }
    }

    @Test func everyFormatHasItsOwnMagic() {
        let formats = UnsupportedDiscFormat.allCases
        #expect(Set(formats.map { compressedImage($0).prefix(4) }).count == formats.count)
        #expect(formats.map(\.rawValue).sorted() == ["GCZ", "RVZ", "WBFS", "WIA"])
    }

    // MARK: Reading in pieces

    @Test func aBigDOLIsReadInBoundedChunksAndHashedAcrossThem() {
        let dol = makeDOL([Section(index: 0, offset: 0x100, size: 0x27_FF00)])
        #expect(dol.count == 0x28_0000)
        let fs = FakeFileSystem()
        fs.addFile(discPath, makeISO(dol: dol, tail: 0x40_0000))

        #expect(
            checkDisc(at: discPath, expectedID: kirbyID, expectedDOLSHA1: sha1(dol), fs: fs) == .ok)
        let reads = fs.reads
        #expect(reads.count > 3)
        #expect(reads.allSatisfy { $0.count <= 1 << 20 })
        // The image is 6.5 MiB, and the check reads the DOL and little else.
        #expect(reads.map(\.returned).reduce(0, +) <= dol.count + 0x1000)
    }

    @Test func aCISOIsReadInBoundedPiecesToo() {
        let dol = makeDOL([Section(index: 0, offset: 0x100, size: 0x27_FF00)])
        let ciso = makeCISO(from: makeISO(dol: dol, tail: 0x40_0000))
        let fs = FakeFileSystem()
        fs.addFile(discPath, ciso)

        #expect(
            checkDisc(at: discPath, expectedID: kirbyID, expectedDOLSHA1: sha1(dol), fs: fs) == .ok)
        let reads = fs.reads
        #expect(reads.allSatisfy { $0.count <= 1 << 20 })
        #expect(reads.map(\.returned).reduce(0, +) <= 0x8000 + dol.count + 0x2000)
    }

    // MARK: On disk

    @Test func filesOnDiskWithSpacesInTheirPathsCheckOut() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("Dragoon disc tests \(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let isoPath = directory.appendingPathComponent("Kirby Air Ride (USA).gcm").path
        let cisoPath = directory.appendingPathComponent("Kirby Air Ride (USA).ciso").path
        let junkPath = directory.appendingPathComponent("Super Mario Sunshine (USA, Canada).gcm").path
        try standardISO.write(to: URL(fileURLWithPath: isoPath))
        try makeCISO(from: standardISO).write(to: URL(fileURLWithPath: cisoPath))
        try makeISO(id: Array("GMSE01".utf8), dol: standardDOL).write(to: URL(fileURLWithPath: junkPath))

        let sha = sha1(standardDOL)
        #expect(checkDisc(at: isoPath, expectedID: kirbyID, expectedDOLSHA1: sha) == .ok)
        #expect(checkDisc(at: cisoPath, expectedID: kirbyID, expectedDOLSHA1: sha) == .ok)
        #expect(
            checkDisc(at: junkPath, expectedID: kirbyID, expectedDOLSHA1: sha)
                == .wrongGame(foundID: "GMSE01"))
        #expect(isUnreadable(checkDisc(at: directory.path, expectedID: kirbyID, expectedDOLSHA1: sha)))
        #expect(
            isUnreadable(
                checkDisc(
                    at: directory.path + "/no such disc.gcm", expectedID: kirbyID,
                    expectedDOLSHA1: sha)))
    }
}

@Suite struct DiscCheckJSONTests {
    private func fields(_ check: DiscCheck) throws -> [String: String] {
        let data = Data(check.json().utf8)
        return try #require(try JSONSerialization.jsonObject(with: data) as? [String: String])
    }

    @Test func eachResultIsKeyedByStatusAndWhatItCarries() throws {
        #expect(try fields(.ok) == ["status": "ok"])
        #expect(try fields(.wrongGame(foundID: "GMSE01")) == ["status": "wrongGame", "foundID": "GMSE01"])
        #expect(
            try fields(.wrongRevision(foundSHA1: "ab12"))
                == ["status": "wrongRevision", "foundSHA1": "ab12"])
        #expect(
            try fields(.needsConversion(format: .rvz))
                == ["status": "needsConversion", "format": "RVZ"])
        #expect(
            try fields(.unreadable(reason: "It's \"short\".")) == ["status": "unreadable", "reason": "It's \"short\"."])
    }

    @Test func onlyOKIsOK() {
        #expect(DiscCheck.ok.isOK)
        #expect(!DiscCheck.wrongGame(foundID: "GMSE01").isOK)
        #expect(!DiscCheck.wrongRevision(foundSHA1: "ab12").isOK)
        #expect(!DiscCheck.needsConversion(format: .gcz).isOK)
        #expect(!DiscCheck.unreadable(reason: "x").isOK)
    }
}

@Suite struct ExpectedDiscTests {
    private let sha = String(repeating: "ab", count: 20)

    @Test func readsTheDiscIDAndTheDOLSHA1AndIgnoresTheRest() throws {
        let fs = FakeFileSystem()
        let path = home + "/Application Support/source-info.json"
        let json = #"{"dragoon": 5, "disc_id": "GKYE01", "dol_sha1": "\#(sha)", "extra": [1]}"#
        fs.addFile(path, Data(json.utf8))
        #expect(try ExpectedDisc.read(at: path, fs: fs) == ExpectedDisc(id: kirbyID, dolSHA1: sha))
    }

    @Test(arguments: [
        ("disc_id", #"{"dol_sha1": "SHA"}"#),
        ("disc_id", #"{"disc_id": "gkye01", "dol_sha1": "SHA"}"#),
        ("disc_id", #"{"disc_id": "GKYE0", "dol_sha1": "SHA"}"#),
        ("disc_id", #"{"disc_id": "GKYE011", "dol_sha1": "SHA"}"#),
        ("disc_id", #"{"disc_id": 123456, "dol_sha1": "SHA"}"#),
        ("dol_sha1", #"{"disc_id": "GKYE01"}"#),
        ("dol_sha1", #"{"disc_id": "GKYE01", "dol_sha1": "AB"}"#),
        ("dol_sha1", #"{"disc_id": "GKYE01", "dol_sha1": "ABABABABABABABABABABABABABABABABABABABAB"}"#),
        ("dol_sha1", #"{"disc_id": "GKYE01", "dol_sha1": "abababababababababababababababababababab0"}"#),
    ])
    func aMissingOrMalformedFieldIsRefusedByName(_ field: String, _ json: String) {
        let fs = FakeFileSystem()
        fs.addFile("/snapshot/source-info.json", Data(json.replacingOccurrences(of: "SHA", with: sha).utf8))
        let error = #expect(throws: SourceInfoError.self) {
            try ExpectedDisc.read(at: "/snapshot/source-info.json", fs: fs)
        }
        #expect(error?.description == "/snapshot/source-info.json: \(field) is missing or malformed")
    }

    @Test(arguments: ["", "not json", "[]", "\"GKYE01\""])
    func aFileThatIsntAJSONObjectIsRefusedByPath(_ text: String) {
        let fs = FakeFileSystem()
        fs.addFile("/snapshot/source-info.json", Data(text.utf8))
        let error = #expect(throws: SourceInfoError.self) {
            try ExpectedDisc.read(at: "/snapshot/source-info.json", fs: fs)
        }
        #expect(error?.description.hasPrefix("/snapshot/source-info.json: ") == true)
    }

    @Test func aFileThatIsntThereIsRefusedByPath() {
        let error = #expect(throws: SourceInfoError.self) {
            try ExpectedDisc.read(at: "/snapshot/source-info.json", fs: FakeFileSystem())
        }
        #expect(error?.description.hasPrefix("/snapshot/source-info.json: can't be read") == true)
    }
}

@Suite struct CheckDiscCommandTests {
    private func world(id: String = kirbyID, dolImage: Data = standardISO) -> FakeFileSystem {
        let fs = FakeFileSystem()
        fs.addFile(discPath, dolImage)
        let json = #"{"disc_id": "\#(id)", "dol_sha1": "\#(sha1(standardDOL))"}"#
        fs.addFile(bundledInfo, Data(json.utf8))
        return fs
    }

    private func run(_ arguments: [String], _ fs: FakeFileSystem) -> CheckDiscCommandResult {
        runCheckDisc(arguments, bundledSourceInfo: bundledInfo, fs: fs)
    }

    @Test func aDiscThatMatchesPrintsOKAndExits0() throws {
        let result = run([discPath], world())
        #expect(result == CheckDiscCommandResult(stdout: DiscCheck.ok.json() + "\n", stderr: "", status: 0))
    }

    @Test func aDiscThatDoesntMatchPrintsWhyAndExits1() {
        let result = run([discPath], world(id: "GMSE01"))
        #expect(result.stdout == DiscCheck.wrongGame(foundID: kirbyID).json() + "\n")
        #expect(result.stderr.isEmpty)
        #expect(result.status == 1)
    }

    @Test func aSourceInfoOfTheCallersChoiceIsUsedInPlaceOfTheBundledOne() {
        let fs = world(id: "GMSE01")
        fs.addFile("/elsewhere/source-info.json", Data(#"{"disc_id": "GKYE01", "dol_sha1": "\#(sha1(standardDOL))"}"#.utf8))
        #expect(run([discPath], fs).status == 1)
        #expect(run([discPath, "--source-info", "/elsewhere/source-info.json"], fs).status == 0)
    }

    @Test(arguments: [
        [], ["--source-info", "/x"], ["/disc", "--source-info"], ["/disc", "extra"],
        ["/disc", "--source-info", "/x", "extra"],
    ] as [[String]])
    func badArgumentsPrintUsageAndExit2(_ arguments: [String]) {
        let result = run(arguments, world())
        #expect(result.stdout.isEmpty)
        #expect(result.stderr.hasPrefix("usage: Dragoon --check-disc PATH [--source-info FILE]"))
        #expect(result.status == 2)
    }

    @Test func aSourceInfoThatCantBeUsedNamesItAndExits2() {
        let missing = run([discPath, "--source-info", "/nowhere/source-info.json"], world())
        #expect(missing.stdout.isEmpty)
        #expect(missing.stderr.contains("/nowhere/source-info.json"))
        #expect(missing.status == 2)

        let fs = world()
        fs.addFile(bundledInfo, Data(#"{"disc_id": "GKYE01"}"#.utf8))
        let malformed = run([discPath], fs)
        #expect(malformed.stderr == "\(bundledInfo): dol_sha1 is missing or malformed\n")
        #expect(malformed.status == 2)
    }
}
