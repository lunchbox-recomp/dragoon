import DragoonCore
import Foundation
import Testing

private let tools = "/Library/Developer/CommandLineTools"
private let xcode = "/Applications/Xcode.app/Contents/Developer"
private let data = "/Users/player/Library/Application Support/Dragoon"
private let clang26_6 = "Apple clang version 21.0.0 (clang-2100.1.1.101)"
private let clangNewer = "Apple clang version 21.0.1 (clang-2100.2.0.5)"

private func ok(_ stdout: String) -> ProcessResult { ProcessResult(status: 0, stdout: stdout) }

/// A Mac for `Toolchain.detect` to look at, as a fake runner and a fake file system. It starts
/// with a developer directory selected and its four tools found, and the test adds SDKs.
private struct FakeMac {
    let runner = FakeProcessRunner()
    let fs = FakeFileSystem()
    let developer: String
    let clangxx: String

    init(developer: String = tools, clangVersion: String = clang26_6) {
        self.developer = developer
        let isXcode = developer == xcode
        let toolchainBin = isXcode
            ? developer + "/Toolchains/XcodeDefault.xctoolchain/usr/bin" : developer + "/usr/bin"
        clangxx = toolchainBin + "/clang++"
        fs.addDirectory(developer)
        runner.respond(to: "/usr/bin/xcode-select", ["-p"], with: ok(developer + "\n"))
        for tool in ["clang", "clang++"] {
            runner.respond(to: "/usr/bin/xcrun", ["--find", tool], with: ok("\(toolchainBin)/\(tool)\n"))
        }
        for tool in ["make", "python3"] {
            runner.respond(to: "/usr/bin/xcrun", ["--find", tool], with: ok("\(developer)/usr/bin/\(tool)\n"))
        }
        setClangVersion(clangVersion)
        if isXcode { fs.addDirectory(developer + "/Platforms") }
    }

    func setClangVersion(_ line: String) {
        runner.respond(
            to: developer == xcode
                ? developer + "/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang"
                : developer + "/usr/bin/clang",
            ["--version"], with: ok(line + "\nTarget: arm64-apple-darwin25.6.0\nThread model: posix\n"))
    }

    func setToolsPackageVersion(_ version: String) {
        runner.respond(
            to: "/usr/sbin/pkgutil", ["--pkg-info=com.apple.pkg.CLTools_Executables"],
            with: ok("package-id: com.apple.pkg.CLTools_Executables\nversion: \(version)\nvolume: /\nlocation: /\n"))
    }

    func addSDK(_ name: String) { fs.addDirectory(developer + "/SDKs/" + name) }

    func addSDKLink(_ name: String, to target: String) {
        fs.addSymlink(developer + "/SDKs/" + name, to: target)
    }

    /// The command that compiles and links the probe against `sdk`.
    func probe(_ sdk: String) -> [String] {
        [clangxx, "-isysroot", sdk, data + "/probe/toolchain.cpp", "-o", "/dev/null"]
    }

    func setLinks(_ sdk: String, _ links: Bool) {
        let command = probe(sdk)
        runner.respond(
            to: command[0], Array(command.dropFirst()),
            with: ProcessResult(status: links ? 0 : 1, stderr: links ? "" : "ld: library 'c++' not found"))
    }

    func detect() async -> ToolchainStatus {
        await Toolchain.detect(runner: runner, fs: fs, dataDirectory: data)
    }

    /// Every command run so far, executable first.
    var commands: [[String]] { runner.calls.map { [$0.executable] + $0.arguments } }

    var probedSDKs: [String] {
        runner.calls.filter { $0.executable == clangxx }.map { $0.arguments[1] }
    }
}

private func cltToolchain(sdk: String, clangVersion: String = clang26_6) -> Toolchain {
    Toolchain(
        developerDirectory: tools, clang: tools + "/usr/bin/clang", clangxx: tools + "/usr/bin/clang++",
        make: tools + "/usr/bin/make", python3: tools + "/usr/bin/python3", sdk: sdk,
        clangVersion: clangVersion)
}

@Suite struct ToolchainTests {
    @Test func toolsAt26_6WithSDKs26_5And27_0Pick26_5AndNeverTry27_0() async {
        let mac = FakeMac()
        mac.setToolsPackageVersion("26.6.0.0.1781586589")
        mac.addSDK("MacOSX26.5.sdk")
        mac.addSDK("MacOSX27.0.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", true)

        #expect(await mac.detect() == .ready(cltToolchain(sdk: tools + "/SDKs/MacOSX26.5.sdk")))
        #expect(mac.probedSDKs == [tools + "/SDKs/MacOSX26.5.sdk"])
    }

    @Test func aGenericSDKThatLinksIsChosenWithoutLookingAtTheToolsVersion() async {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        mac.addSDK("MacOSX27.0.sdk")
        mac.addSDKLink("MacOSX.sdk", to: "MacOSX26.5.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", true)

        #expect(await mac.detect() == .ready(cltToolchain(sdk: tools + "/SDKs/MacOSX26.5.sdk")))
        #expect(!mac.commands.contains { $0.first == "/usr/sbin/pkgutil" })
    }

    @Test func aGenericSDKThatFailsToLinkIsNotTriedAgainAndANewerOneIsSkipped() async {
        let mac = FakeMac()
        mac.setToolsPackageVersion("26.6.0.0.1781586589")
        mac.addSDK("MacOSX26.5.sdk")
        mac.addSDK("MacOSX27.0.sdk")
        mac.addSDKLink("MacOSX.sdk", to: "MacOSX27.0.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX27.0.sdk", false)
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", true)

        #expect(await mac.detect() == .ready(cltToolchain(sdk: tools + "/SDKs/MacOSX26.5.sdk")))
        #expect(mac.probedSDKs == [tools + "/SDKs/MacOSX27.0.sdk", tools + "/SDKs/MacOSX26.5.sdk"])
    }

    @Test func otherSDKsAreTriedNewestFirstEachOnceWithLinksResolved() async {
        let mac = FakeMac()
        mac.setToolsPackageVersion("26.6.0.0.1781586589")
        mac.addSDK("MacOSX15.4.sdk")
        mac.addSDK("MacOSX26.5.sdk")
        mac.addSDK("MacOSX9.sdk")
        mac.addSDKLink("MacOSX.sdk", to: "MacOSX26.5.sdk")
        mac.addSDKLink("MacOSX26.sdk", to: "MacOSX26.5.sdk")
        mac.addSDKLink("MacOSX15.sdk", to: "MacOSX15.4.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", false)
        mac.setLinks(tools + "/SDKs/MacOSX15.4.sdk", false)
        mac.setLinks(tools + "/SDKs/MacOSX9.sdk", true)

        #expect(await mac.detect() == .ready(cltToolchain(sdk: tools + "/SDKs/MacOSX9.sdk")))
        #expect(mac.probedSDKs == [
            tools + "/SDKs/MacOSX26.5.sdk", tools + "/SDKs/MacOSX15.4.sdk",
            tools + "/SDKs/MacOSX9.sdk",
        ])
    }

    @Test func withoutPkgutilsAnswerNoSDKIsSkippedForItsVersion() async {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        mac.addSDK("MacOSX27.0.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX27.0.sdk", true)

        #expect(await mac.detect() == .ready(cltToolchain(sdk: tools + "/SDKs/MacOSX27.0.sdk")))
    }

    @Test func fullXcodeUsesTheSDKXcrunNames() async {
        let mac = FakeMac(developer: xcode)
        let named = xcode + "/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
        mac.runner.respond(
            to: "/usr/bin/xcrun", ["--sdk", "macosx", "--show-sdk-path"], with: ok(named + "\n"))
        mac.setLinks(named, true)

        let status = await mac.detect()
        guard case .ready(let toolchain) = status else {
            Issue.record("expected ready, got \(status)")
            return
        }
        #expect(toolchain.sdk == named)
        #expect(toolchain.developerDirectory == xcode)
        #expect(toolchain.clangxx == xcode + "/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++")
        #expect(mac.probedSDKs == [named])
    }

    @Test func xcrunIsOnlyAskedForAnSDKWhenXcodeIsSelected() async {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", true)
        _ = await mac.detect()

        #expect(!mac.commands.contains { $0.starts(with: ["/usr/bin/xcrun", "--sdk"]) })
    }

    @Test func xcodesSDKFailingToLinkFallsThroughToTheOthers() async {
        let mac = FakeMac(developer: xcode)
        let named = xcode + "/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
        mac.runner.respond(
            to: "/usr/bin/xcrun", ["--sdk", "macosx", "--show-sdk-path"], with: ok(named))
        mac.setLinks(named, false)
        mac.setToolsPackageVersion("26.6.0.0.1781586589")
        mac.addSDK("MacOSX26.5.sdk")
        mac.setLinks(xcode + "/SDKs/MacOSX26.5.sdk", true)

        let status = await mac.detect()
        #expect(status.isReady)
        #expect(mac.probedSDKs == [named, xcode + "/SDKs/MacOSX26.5.sdk"])
    }

    @Test func xcrunFindAnswersForAllFourToolsAndTheToolchainHoldsMake() async {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", true)
        let status = await mac.detect()

        #expect(status == .ready(cltToolchain(sdk: tools + "/SDKs/MacOSX26.5.sdk")))
        guard case .ready(let toolchain) = status else { return }
        #expect(toolchain.make == tools + "/usr/bin/make")
        #expect(mac.commands.filter { $0.starts(with: ["/usr/bin/xcrun", "--find"]) }.map { $0[2] }
                == ["clang", "clang++", "make", "python3"])
    }

    @Test func noSDKThatLinksListsEveryPathTriedAndNothingElse() async {
        let mac = FakeMac()
        mac.setToolsPackageVersion("26.6.0.0.1781586589")
        mac.addSDK("MacOSX15.4.sdk")
        mac.addSDK("MacOSX26.5.sdk")
        mac.addSDK("MacOSX27.0.sdk")
        mac.addSDKLink("MacOSX.sdk", to: "MacOSX26.5.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", false)
        mac.setLinks(tools + "/SDKs/MacOSX15.4.sdk", false)

        #expect(await mac.detect() == .noLinkableSDK(tried: [
            tools + "/SDKs/MacOSX26.5.sdk", tools + "/SDKs/MacOSX15.4.sdk",
        ]))
        #expect(mac.fs.fileExists(at: data + "/toolchain.json") == false)
    }

    @Test func aDirectoryWithNoSDKsAtAllHasNoneToTry() async {
        let mac = FakeMac()
        #expect(await mac.detect() == .noLinkableSDK(tried: []))
    }

    @Test func aProbeThatCantStartCountsAsNotLinking() async {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        #expect(await mac.detect() == .noLinkableSDK(tried: [tools + "/SDKs/MacOSX26.5.sdk"]))
    }

    @Test func noDeveloperDirectoryIsMissingAndOnlyXcodeSelectRan() async {
        let mac = FakeMac()
        mac.runner.respond(
            to: "/usr/bin/xcode-select", ["-p"],
            with: ProcessResult(status: 2, stderr: "xcode-select: error: unable to get active developer directory"))

        #expect(await mac.detect() == .missing)
        #expect(mac.commands == [["/usr/bin/xcode-select", "-p"]])
    }

    @Test func aDirectoryThatIsntThereIsMissingAndOnlyXcodeSelectRan() async {
        let mac = FakeMac()
        mac.runner.respond(
            to: "/usr/bin/xcode-select", ["-p"], with: ok("/Applications/Gone.app/Contents/Developer\n"))

        #expect(await mac.detect() == .missing)
        #expect(mac.commands == [["/usr/bin/xcode-select", "-p"]])
    }

    @Test func aToolXcrunCantFindIsMissing() async {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        mac.runner.respond(
            to: "/usr/bin/xcrun", ["--find", "make"],
            with: ProcessResult(status: 1, stderr: "xcrun: error: unable to find utility \"make\""))

        #expect(await mac.detect() == .missing)
        #expect(mac.commands.last == ["/usr/bin/xcrun", "--find", "make"])
    }

    @Test func everyCommandAfterXcodeSelectRunsOnAFixedPathAndTheFoundDirectory() async {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", true)
        _ = await mac.detect()

        let fixed = ["DEVELOPER_DIR": tools, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"]
        #expect(mac.runner.calls.count > 1)
        #expect(mac.runner.calls.dropFirst().allSatisfy { $0.environment == fixed })
    }

    @Test func theProbeIsAFileWithACstdioIncludeAndItsPathKeepsItsSpaces() async throws {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", true)
        _ = await mac.detect()

        let source = try String(decoding: mac.fs.readData(at: data + "/probe/toolchain.cpp"), as: UTF8.self)
        #expect(source.contains("#include <cstdio>"))
        #expect(mac.runner.calls.last?.arguments.contains(data + "/probe/toolchain.cpp") == true)
    }

    @Test func aCachedChoiceSkipsTheProbeUntilTheClangLineChanges() async throws {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", true)
        let first = await mac.detect()
        #expect(mac.probedSDKs.count == 1)

        let cache = try JSONDecoder().decode(
            Toolchain.self, from: mac.fs.readData(at: data + "/toolchain.json"))
        #expect(ToolchainStatus.ready(cache) == first)

        #expect(await mac.detect() == first)
        #expect(mac.probedSDKs.count == 1)

        mac.setClangVersion(clangNewer)
        let third = await mac.detect()
        #expect(mac.probedSDKs.count == 2)
        #expect(third == .ready(cltToolchain(sdk: tools + "/SDKs/MacOSX26.5.sdk", clangVersion: clangNewer)))

        #expect(await mac.detect() == third)
        #expect(mac.probedSDKs.count == 2)
    }

    @Test func aCachedChoiceIsProbedAgainWhenItsSDKIsGone() async throws {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", true)
        let gone = cltToolchain(sdk: tools + "/SDKs/MacOSX26.4.sdk")
        mac.fs.addFile(data + "/toolchain.json", try JSONEncoder().encode(gone))

        #expect(await mac.detect() == .ready(cltToolchain(sdk: tools + "/SDKs/MacOSX26.5.sdk")))
        #expect(mac.probedSDKs.count == 1)
    }

    @Test func aCacheForOtherToolsOrThatIsntJSONIsProbedAgain() async throws {
        let mac = FakeMac()
        mac.addSDK("MacOSX26.5.sdk")
        mac.setLinks(tools + "/SDKs/MacOSX26.5.sdk", true)
        var other = cltToolchain(sdk: tools + "/SDKs/MacOSX26.5.sdk")
        other.developerDirectory = xcode
        mac.fs.addFile(data + "/toolchain.json", try JSONEncoder().encode(other))
        _ = await mac.detect()
        #expect(mac.probedSDKs.count == 1)

        mac.fs.addFile(data + "/toolchain.json", Data("not json".utf8))
        _ = await mac.detect()
        #expect(mac.probedSDKs.count == 2)
    }
}

@Suite struct ToolchainStatusJSONTests {
    private func parse(_ status: ToolchainStatus) throws -> [String: Any] {
        let object = try JSONSerialization.jsonObject(with: Data(status.json().utf8))
        return try #require(object as? [String: Any])
    }

    @Test func missingIsJustAStatus() throws {
        #expect(try parse(.missing) as NSDictionary == ["status": "missing"])
    }

    @Test func noLinkableSDKListsWhatWasTried() throws {
        let json = try parse(.noLinkableSDK(tried: ["/a b/MacOSX26.5.sdk", "/a b/MacOSX15.4.sdk"]))
        #expect(json as NSDictionary == [
            "status": "noLinkableSDK", "tried": ["/a b/MacOSX26.5.sdk", "/a b/MacOSX15.4.sdk"],
        ])
    }

    @Test func readyHoldsEveryFieldOfTheToolchain() throws {
        let json = try parse(.ready(cltToolchain(sdk: tools + "/SDKs/MacOSX26.5.sdk")))
        #expect(json as NSDictionary == [
            "status": "ready",
            "toolchain": [
                "developerDirectory": tools,
                "clang": tools + "/usr/bin/clang",
                "clangxx": tools + "/usr/bin/clang++",
                "make": tools + "/usr/bin/make",
                "python3": tools + "/usr/bin/python3",
                "sdk": tools + "/SDKs/MacOSX26.5.sdk",
                "clangVersion": clang26_6,
            ] as [String: String],
        ])
    }

    @Test func slashesInPathsStayUnescaped() {
        #expect(ToolchainStatus.noLinkableSDK(tried: ["/a/b"]).json().contains("\"/a/b\""))
    }

    @Test func onlyReadyIsReady() {
        #expect(ToolchainStatus.ready(cltToolchain(sdk: "/sdk")).isReady)
        #expect(!ToolchainStatus.missing.isReady)
        #expect(!ToolchainStatus.noLinkableSDK(tried: []).isReady)
    }
}
