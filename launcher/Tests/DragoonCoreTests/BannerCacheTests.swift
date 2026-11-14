import DragoonCore
import Foundation
import Testing

private let data = "/Users/Test Player/Library/Application Support/Dragoon"
private let cached = data + "/disc/opening.bnr"
private let disc = "/Users/Test Player/Games/Kirby Air Ride (USA).gcm"

@Suite struct BannerCacheTests {
    @Test func theCacheIsTheDataFoldersDiscOpeningBNR() {
        #expect(BannerCache.path(data: data) == cached)
    }

    @Test(arguments: [("BNR1", [BannerText()]), ("BNR2", sixTexts)])
    func aDiscsBannerIsKeptAsTheFileItIs(_ magic: String, _ texts: [BannerText]) throws {
        let bnr = makeBNR(magic: magic, pixels: distinctPixels, texts: texts)
        let fs = FakeFileSystem()
        fs.addFile(disc, makeDisc(root: [.file("opening.bnr", bnr)]).image)
        let banner = try #require(BannerCache.readAndKeep(disc: disc, data: data, fs: fs))
        #expect(banner == DiscBanner.read(at: disc, fs: fs))
        #expect(fs.writes == [.init(path: cached, data: bnr)])
    }

    @Test func aDiscWithNoBannerLeavesTheCacheAlone() throws {
        let fs = FakeFileSystem()
        fs.addFile(disc, makeDisc(root: []).image)
        fs.addFile(cached, makeBNR())
        #expect(BannerCache.readAndKeep(disc: disc, data: data, fs: fs) == nil)
        #expect(fs.writes.isEmpty)
        #expect(try fs.readData(at: cached) == makeBNR())
    }

    @Test func aCacheThatCantBeWrittenStillGivesTheBanner() {
        let fs = FakeFileSystem()
        fs.addFile(disc, makeDisc(root: [.file("opening.bnr", makeBNR())]).image)
        fs.failWrites(with: POSIXError(.EACCES))
        #expect(BannerCache.readAndKeep(disc: disc, data: data, fs: fs)
            == DiscBanner(bytes: makeBNR(), discID: "GKYE01"))
    }

    @Test func theCachedBannerLoadsWithNoDisc() {
        let fs = FakeFileSystem()
        fs.addFile(cached, makeBNR(pixels: distinctPixels))
        #expect(BannerCache.load(data: data, discID: "GKYE01", fs: fs)
            == DiscBanner(bytes: makeBNR(pixels: distinctPixels), discID: "GKYE01"))
    }

    @Test func theCachedStringsAreDecodedForTheDisc() throws {
        var text = BannerText()
        text.shortName = Array("テスト".data(using: .shiftJIS)!)
        let fs = FakeFileSystem()
        fs.addFile(cached, makeBNR(texts: [text]))
        let banner = try #require(BannerCache.load(data: data, discID: "TSTJ01", fs: fs))
        #expect(banner.texts[0].shortName == "テスト")
    }

    @Test func noCacheOrAnUnusableOneLoadsNothing() {
        let fs = FakeFileSystem()
        #expect(BannerCache.load(data: data, discID: "GKYE01", fs: fs) == nil)
        fs.addFile(cached, Data("not a banner".utf8))
        #expect(BannerCache.load(data: data, discID: "GKYE01", fs: fs) == nil)
        fs.addFile(cached, makeBNR().dropLast())
        #expect(BannerCache.load(data: data, discID: "GKYE01", fs: fs) == nil)
    }

    @Test func theCacheWorksOnDiskWithSpacesInItsPath() throws {
        let scratch = try ScratchDirectory("banner")
        defer { scratch.remove() }
        let fs = SystemFileSystem()
        let folder = scratch.data
        let image = scratch.path + "/Games/Kirby Air Ride (USA).gcm"
        try fs.writeData(makeDisc(root: [.file("opening.bnr", makeBNR())]).image, to: image)
        let banner = try #require(BannerCache.readAndKeep(disc: image, data: folder, fs: fs))
        #expect(try fs.readData(at: folder + "/disc/opening.bnr") == makeBNR())
        #expect(BannerCache.load(data: folder, discID: "GKYE01", fs: fs) == banner)
    }
}
