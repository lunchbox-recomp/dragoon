import DragoonCore
import Foundation
import ImageIO
import Testing

private let discPath = "/Users/Test Player/Games/Kirby Air Ride (USA).gcm"

/// A root with a file before the banner, a directory and a file after it, so the walk has to
/// step over each.
private func standardRoot(_ bnr: Data) -> [DiscNode] {
    [
        .file("a.dat", Data(repeating: 0xAA, count: 0x40)),
        .directory("sub", [.file("b.dat", Data(repeating: 0xBB, count: 0x10))]),
        .file("opening.bnr", bnr),
        .file("z.dat", Data(repeating: 0xCC, count: 0x10)),
    ]
}

private func standardDisc(_ bnr: Data = makeBNR(), id: String = "GKYE01") -> DiscFixture {
    makeDisc(id: id, root: standardRoot(bnr))
}

private func read(_ image: Data, fs: FakeFileSystem = FakeFileSystem()) -> DiscBanner? {
    fs.addFile(discPath, image)
    return DiscBanner.read(at: discPath, fs: fs)
}

/// A banner whose every pixel is `value`.
private func filled(_ value: UInt16, id: String = "GKYE01") -> DiscBanner? {
    read(standardDisc(makeBNR(pixels: Array(repeating: value, count: bannerPixelCount)), id: id)
        .image)
}

private func pixel(_ banner: DiscBanner, _ x: Int, _ y: Int) -> [UInt8] {
    let at = (y * DiscBanner.width + x) * 4
    return Array(banner.rgba[at..<at + 4])
}

private func text(_ text: BannerText, encoding: String.Encoding = .utf8) -> DiscBanner.Text {
    func string(_ bytes: [UInt8]) -> String { String(data: Data(bytes), encoding: encoding)! }
    return DiscBanner.Text(
        shortName: string(text.shortName), shortMaker: string(text.shortMaker),
        longName: string(text.longName), longMaker: string(text.longMaker),
        description: string(text.description))
}

/// An RGB555 word and the pixel it gives. Each 5-bit channel widens as `v << 3 | v >> 2`.
private let rgb555Cases: [(UInt16, [UInt8])] = [
    (0x8000, [0, 0, 0, 255]),
    (0xFFFF, [255, 255, 255, 255]),
    (0xFC00, [255, 0, 0, 255]),
    (0x83E0, [0, 255, 0, 255]),
    (0x801F, [0, 0, 255, 255]),
    (0x8421, [8, 8, 8, 255]),
    (0xC210, [132, 132, 132, 255]),
    (0xC03E, [132, 8, 247, 255]),
]

/// An A3RGB444 word and the pixel it gives, with its color as it is whatever the alpha.
private let a3rgb444Cases: [(UInt16, [UInt8])] = [
    (0x0000, [0, 0, 0, 0]),
    (0x0FFF, [255, 255, 255, 0]),
    (0x7F00, [255, 0, 0, 255]),
    (0x70F0, [0, 255, 0, 255]),
    (0x700F, [0, 0, 255, 255]),
    (0x7123, [17, 34, 51, 255]),
    (0x3A5C, [170, 85, 204, 109]),
]

/// Each 3-bit alpha and what it widens to, as `v << 5 | v << 2 | v >> 1`.
private let alphaCases: [(UInt16, UInt8)] = [
    (0, 0), (1, 36), (2, 73), (3, 109), (4, 146), (5, 182), (6, 219), (7, 255),
]

/// A pixel's place in the file and the x and y it lands at.
private let tileCases: [(Int, Int, Int)] = [
    (0, 0, 0), (1, 1, 0), (3, 3, 0), (4, 0, 1), (15, 3, 3), (16, 4, 0), (17, 5, 0), (20, 4, 1),
    (23 * 16, 92, 0), (23 * 16 + 15, 95, 3), (24 * 16, 0, 4), (24 * 16 + 5, 1, 5), (3071, 95, 31),
]

@Suite struct DiscBannerTests {
    // MARK: Finding it

    @Test func aBNR1OnTheRootIsReadWithItsBytesAndStrings() throws {
        let bnr = makeBNR(pixels: distinctPixels)
        #expect(bnr.count == 0x1960)
        let banner = try #require(read(standardDisc(bnr).image))
        #expect(banner.format == .bnr1)
        #expect(banner.bytes == bnr)
        #expect(banner.texts == [text(BannerText())])
        #expect(banner.rgba.count == 96 * 32 * 4)
    }

    @Test func aBNR2HasSixInfoBlocksInTheFilesOrder() throws {
        let bnr = makeBNR(magic: "BNR2", texts: sixTexts)
        #expect(bnr.count == 0x1FA0)
        let banner = try #require(read(standardDisc(bnr).image))
        #expect(banner.format == .bnr2)
        #expect(banner.texts == sixTexts.map { text($0) })
        #expect(banner.bytes == bnr)
    }

    @Test func aDiscWithNoOpeningBNRHasNoBanner() {
        #expect(read(makeDisc(root: [.file("a.dat", Data(count: 0x10))]).image) == nil)
        #expect(read(makeDisc(root: []).image) == nil)
    }

    @Test func aFileThatIsntThereHasNoBanner() {
        #expect(DiscBanner.read(at: discPath, fs: FakeFileSystem()) == nil)
    }

    @Test(arguments: ["Opening.bnr", "OPENING.BNR", "opening.bnr2", "opening.bn", "xopening.bnr",
                      "opening", ""])
    func onlyTheExactNameIsTaken(_ name: String) {
        #expect(read(makeDisc(root: [.file(name, makeBNR())]).image) == nil)
    }

    @Test func anOpeningBNRInsideADirectoryIsNotTaken() {
        #expect(read(makeDisc(root: [.directory("sub", [.file("opening.bnr", makeBNR())])]).image)
            == nil)
        let deep = makeDisc(root: [
            .directory("a", [.directory("b", [.file("opening.bnr", makeBNR())])]),
            .file("c.dat", Data(count: 0x10)),
        ])
        #expect(read(deep.image) == nil)
    }

    @Test func theRootsOwnIsTakenOverOneInADirectoryBeforeIt() throws {
        let red = makeBNR(pixels: Array(repeating: 0xFC00, count: bannerPixelCount))
        let blue = makeBNR(pixels: Array(repeating: 0x801F, count: bannerPixelCount))
        let disc = makeDisc(root: [
            .directory("sub", [.file("x.dat", Data(count: 4)), .file("opening.bnr", red)]),
            .file("opening.bnr", blue),
        ])
        let banner = try #require(read(disc.image))
        #expect(banner.bytes == blue)
        #expect(pixel(banner, 0, 0) == [0, 0, 255, 255])
    }

    @Test func aCISOGivesTheSameBannerAsThePlainImage() throws {
        let image = standardDisc(makeBNR(pixels: distinctPixels)).image
        let plain = try #require(read(image))
        #expect(read(makeCISO(from: image)) == plain)
    }

    @Test func aCompressedOrTinyFileHasNoBanner() {
        var wia = standardDisc().image
        wia.replaceSubrange(0..<4, with: Array("WIA".utf8) + [0x01])
        #expect(read(wia) == nil)
        #expect(read(Data()) == nil)
        #expect(read(Data(count: 0x43F)) == nil)
    }

    // MARK: The banner file

    @Test(arguments: ["BNR3", "bnr1", "BNR ", "RNB1", "\0\0\0\0"])
    func aWrongMagicHasNoBanner(_ magic: String) {
        #expect(read(standardDisc(makeBNR(magic: magic)).image) == nil)
    }

    @Test func eachMagicNeedsItsOwnSize() {
        #expect(read(standardDisc(makeBNR(magic: "BNR1", texts: sixTexts)).image) == nil)
        #expect(read(standardDisc(makeBNR(magic: "BNR2", texts: [BannerText()])).image) == nil)
    }

    @Test(arguments: [-1, 1, -0x1960, 0x1FA0 - 0x1960 + 1])
    func aSizeOtherThanTheTwoHasNoBanner(_ change: Int) {
        var bnr = makeBNR()
        if change > 0 { bnr.append(Data(count: change)) } else { bnr.removeLast(-change) }
        #expect(read(standardDisc(bnr).image) == nil)
    }

    @Test func aBannerThatEndsPastTheImageHasNoBanner() {
        var disc = standardDisc()
        let entry = disc.entries["opening.bnr"]!
        disc.poke(entry + 4, UInt32(disc.image.count - 0x100))
        #expect(read(disc.image) == nil)
        disc.poke(entry + 4, 0xFFFF_FFFF)
        #expect(read(disc.image) == nil)
    }

    // MARK: A table that can't be trusted

    @Test(arguments: [1, 12, 64])
    func aTableThatEndsPastTheImageHasNoBanner(_ past: Int) {
        var disc = standardDisc()
        // The image's last bytes copy the table, so only its end being past the image refuses it.
        let table = disc.image.subdata(in: disc.fstOffset..<disc.fstOffset + disc.fstSize)
        let start = disc.image.count - disc.fstSize + past
        disc.image.replaceSubrange(start..<disc.image.count, with: table.prefix(disc.fstSize - past))
        disc.poke(0x424, UInt32(start))
        #expect(read(disc.image) == nil)
        disc.poke(0x424, 0xFFFF_FFF0)
        #expect(read(disc.image) == nil)
    }

    @Test(arguments: [UInt32(0), 1, 11])
    func aTableUnder12BytesHasNoBanner(_ size: UInt32) {
        var disc = standardDisc()
        disc.poke(0x428, size)
        #expect(read(disc.image) == nil)
    }

    @Test(arguments: [UInt32(0x10_0001), 0x7FFF_FFFF, 0xFFFF_FFFF])
    func aTableOver1MiBHasNoBannerAndIsntRead(_ size: UInt32) {
        var disc = standardDisc()
        disc.poke(0x428, size)
        let fs = FakeFileSystem()
        #expect(read(disc.image, fs: fs) == nil)
        #expect(fs.reads.allSatisfy { $0.count <= 0x440 })
    }

    @Test(arguments: [UInt32(0), 0x1555_5556, 0xFFFF_FFFF])
    func anEntryCountThatDoesntFitHasNoBanner(_ count: UInt32) {
        // 0x1555_5556 entries of 12 bytes is 8 bytes past 4 GiB, which a 32-bit product wraps
        // to 8.
        var disc = standardDisc()
        disc.poke(disc.fstOffset + 8, count)
        #expect(read(disc.image) == nil)
    }

    @Test func anEntryCountWhoseEntriesFillTheTableHasNoBanner() {
        var disc = standardDisc()
        disc.poke(disc.fstOffset + 8, UInt32(disc.fstSize / 12 + 1))
        #expect(read(disc.image) == nil)
    }

    @Test func aTableWhoseLastByteIsntNULHasNoBanner() {
        var disc = standardDisc()
        disc.image[disc.fstOffset + disc.fstSize - 1] = 0x41
        #expect(read(disc.image) == nil)
    }

    @Test(arguments: ["a.dat", "opening.bnr"])
    func aNameOffsetPastTheEndHasNoBanner(_ name: String) {
        let names = standardDisc().fstSize - standardDisc().stringTable
        for offset in [UInt32(names), UInt32(names + 1), 0xFF_FFFF] {
            var disc = standardDisc()
            disc.poke(disc.entries[name]!, offset)
            #expect(read(disc.image) == nil)
        }
    }

    @Test func aDirectoryThatEndsAtOrBeforeItselfHasNoBanner() {
        var disc = standardDisc()
        let sub = disc.entries["sub"]!
        let index = UInt32((sub - disc.fstOffset) / 12)
        for end in [index, index - 1, 0] {
            disc.poke(sub + 8, end)
            #expect(read(disc.image) == nil)
        }
    }

    @Test func aDirectoryThatEndsPastTheTableEndsTheWalk() {
        var disc = makeDisc(root: [.directory("sub", []), .file("opening.bnr", makeBNR())])
        disc.poke(disc.entries["sub"]! + 8, 0x7FFF_FFFF)
        #expect(read(disc.image) == nil)
    }

    /// An entry count past the table and a directory that ends past it would walk off the
    /// table's end, but the count alone refuses it first.
    @Test func anEntryCountPastTheTableWithADirectoryPastItHasNoBanner() {
        var disc = makeDisc(root: [.directory("sub", []), .file("opening.bnr", makeBNR())])
        disc.poke(disc.fstOffset + 8, 0xFFFF_FFFF)
        disc.poke(disc.entries["sub"]! + 8, UInt32(disc.fstSize / 12 + 1))
        #expect(read(disc.image) == nil)
    }

    // MARK: How much is read

    @Test(arguments: [("BNR1", [BannerText()]), ("BNR2", sixTexts)])
    func aPlainImageReadsTheHeaderTheTableAndTheBannerAndNothingElse(
        _ magic: String, _ texts: [BannerText]
    ) throws {
        let bnr = makeBNR(magic: magic, texts: texts)
        let disc = standardDisc(bnr)
        let fs = FakeFileSystem()
        #expect(read(disc.image, fs: fs) != nil)
        let total = fs.reads.map(\.returned).reduce(0, +)
        #expect(total <= 0x440 + disc.fstSize + bnr.count)
        #expect(total <= 0x440 + disc.fstSize + 0x1FA0)
    }

    /// An `opening.bnr` whose size is neither banner's is never read, however big it says it is.
    @Test(arguments: [UInt32(0x1961), 0x1_0000, 0x4000_0000, 0xFFFF_FFFF])
    func anOpeningBNROfAnotherSizeIsntRead(_ size: UInt32) {
        var disc = standardDisc()
        disc.poke(disc.entries["opening.bnr"]! + 8, size)
        let fs = FakeFileSystem()
        #expect(read(disc.image, fs: fs) == nil)
        #expect(fs.reads.allSatisfy { $0.count <= 0x1FA0 })
    }

    @Test func aCISOReadsItsHeaderToo() {
        let disc = standardDisc()
        let fs = FakeFileSystem()
        #expect(read(makeCISO(from: disc.image), fs: fs) != nil)
        let total = fs.reads.map(\.returned).reduce(0, +)
        #expect(total <= 0x440 + 0x8000 + 0x440 + disc.fstSize + 0x1960)
    }

    // MARK: Pixels

    @Test(arguments: rgb555Cases)
    func anRGB555PixelIsOpaqueWithEachChannelWidened(_ value: UInt16, _ expected: [UInt8]) throws {
        let banner = try #require(filled(value))
        #expect(pixel(banner, 0, 0) == expected)
        #expect(pixel(banner, 95, 31) == expected)
    }

    @Test(arguments: a3rgb444Cases)
    func anA3RGB444PixelKeepsItsColorUnderItsAlpha(_ value: UInt16, _ expected: [UInt8]) throws {
        let banner = try #require(filled(value))
        #expect(pixel(banner, 0, 0) == expected)
    }

    @Test(arguments: alphaCases)
    func eachOfTheEightAlphas(_ alpha: UInt16, _ expected: UInt8) throws {
        let banner = try #require(filled(alpha << 12 | 0x0842))
        #expect(pixel(banner, 7, 9) == [136, 68, 34, expected])
    }

    /// The file keeps 4x4 tiles, 24 across and 8 down, each one's 16 pixels row by row.
    @Test(arguments: tileCases)
    func eachPixelLandsByItsTile(_ inFile: Int, _ x: Int, _ y: Int) throws {
        var pixels = Array(repeating: UInt16(0), count: bannerPixelCount)
        pixels[inFile] = 0xFC00
        let banner = try #require(read(standardDisc(makeBNR(pixels: pixels)).image))
        for row in 0..<32 {
            for column in 0..<96 {
                let expected: [UInt8] = (column, row) == (x, y) ? [255, 0, 0, 255] : [0, 0, 0, 0]
                #expect(pixel(banner, column, row) == expected)
            }
        }
    }

    @Test func everyPixelLandsSomewhereOfItsOwn() throws {
        let banner = try #require(read(standardDisc(makeBNR(pixels: distinctPixels)).image))
        let seen = Set((0..<bannerPixelCount).map { pixel(banner, $0 % 96, $0 / 96) })
        #expect(seen.count == bannerPixelCount)
    }

    // MARK: Strings

    @Test func stringsAreWindows1252() throws {
        var text = BannerText()
        text.shortName = Array("Caf".utf8) + [0xE9, 0x20, 0x80]
        let banner = try #require(read(standardDisc(makeBNR(texts: [text])).image))
        #expect(banner.texts[0].shortName == "Café €")
    }

    /// Windows-1252 leaves 0x81, 0x8D, 0x8F, 0x90 and 0x9D undefined, so such a string reads as
    /// Latin-1, where each byte is the code point of its value.
    @Test func aStringWindows1252CantDecodeReadsAsLatin1() throws {
        var text = BannerText()
        text.shortName = [0x41, 0x81, 0x42, 0x8D, 0x90]
        let banner = try #require(read(standardDisc(makeBNR(texts: [text])).image))
        #expect(banner.texts[0].shortName == "A\u{81}B\u{8D}\u{90}")
    }

    @Test func stringsAreShiftJISOnAJapaneseDisc() throws {
        var text = BannerText()
        text.shortName = Array("テスト".data(using: .shiftJIS)!)
        let japanese = try #require(read(standardDisc(makeBNR(texts: [text]), id: "TSTJ01").image))
        #expect(japanese.texts[0].shortName == "テスト")
        let american = try #require(read(standardDisc(makeBNR(texts: [text]), id: "TSTE01").image))
        #expect(american.texts[0].shortName != "テスト")
    }

    @Test func aStringEndsAtItsFirstNULOrItsField() throws {
        var text = BannerText()
        text.shortName = Array("AB".utf8) + [0] + Array("CD".utf8)
        text.shortMaker = Array(repeating: 0x4D, count: 0x20)
        let banner = try #require(read(standardDisc(makeBNR(texts: [text])).image))
        #expect(banner.texts[0].shortName == "AB")
        #expect(banner.texts[0].shortMaker == String(repeating: "M", count: 0x20))
    }

    @Test func theBytesAloneDecodeToTheSameBanner() throws {
        let banner = try #require(read(standardDisc(makeBNR(pixels: distinctPixels)).image))
        #expect(DiscBanner(bytes: banner.bytes, discID: "GKYE01") == banner)
        #expect(DiscBanner(bytes: Data(banner.bytes.dropLast()), discID: "GKYE01") == nil)
        #expect(DiscBanner(bytes: Data(), discID: "GKYE01") == nil)
    }

    // MARK: PNG

    @Test func thePNGHoldsThePixelsWithStraightAlpha() throws {
        var pixels = distinctPixels
        pixels[0] = 0x3A5C
        pixels[1] = 0x0FFF
        let banner = try #require(read(standardDisc(makeBNR(pixels: pixels)).image))
        let png = try #require(banner.png())
        let source = try #require(CGImageSourceCreateWithData(png as CFData, nil))
        let image = try #require(CGImageSourceCreateImageAtIndex(source, 0, nil))
        #expect(image.width == 96 && image.height == 32)
        #expect(image.bitsPerPixel == 32 && image.alphaInfo == .last)
        #expect(image.bytesPerRow == 96 * 4)
        let data = try #require(image.dataProvider?.data)
        #expect(Array(data as Data) == banner.rgba)
    }
}
