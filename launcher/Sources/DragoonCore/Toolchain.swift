import Foundation

/// The build tools and the SDK the recipe takes, each by full path.
public struct Toolchain: Codable, Equatable, Sendable {
    public var developerDirectory: String
    /// The recipe's `--cc`.
    public var clang: String
    /// The recipe's `--cxx`.
    public var clangxx: String
    /// The recipe's `--make`.
    public var make: String
    /// The recipe's `--python`.
    public var python3: String
    /// The recipe's `--sdk`.
    public var sdk: String
    /// The first line of `clang --version`, which `sdk` was chosen against.
    public var clangVersion: String

    public init(
        developerDirectory: String, clang: String, clangxx: String, make: String, python3: String,
        sdk: String, clangVersion: String
    ) {
        self.developerDirectory = developerDirectory
        self.clang = clang
        self.clangxx = clangxx
        self.make = make
        self.python3 = python3
        self.sdk = sdk
        self.clangVersion = clangVersion
    }
}

public enum ToolchainStatus: Equatable, Sendable {
    /// No developer directory is selected, or a tool isn't in it.
    case missing
    /// The tools are there, but no SDK compiled and linked the probe. `tried` lists each one.
    case noLinkableSDK(tried: [String])
    case ready(Toolchain)
}

extension ToolchainStatus {
    public var isReady: Bool {
        if case .ready = self { return true }
        return false
    }

    /// The status as JSON, keyed by `status` and then `tried` or `toolchain`.
    public func json() -> String {
        String(decoding: encodeJSON(self), as: UTF8.self)
    }
}

extension ToolchainStatus: Encodable {
    private enum Keys: String, CodingKey {
        case status, tried, toolchain
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: Keys.self)
        switch self {
        case .missing:
            try container.encode("missing", forKey: .status)
        case .noLinkableSDK(let tried):
            try container.encode("noLinkableSDK", forKey: .status)
            try container.encode(tried, forKey: .tried)
        case .ready(let toolchain):
            try container.encode("ready", forKey: .status)
            try container.encode(toolchain, forKey: .toolchain)
        }
    }
}

extension Toolchain {
    /// Where the launcher keeps its data, until a caller names another place.
    public static var defaultDataDirectory: String {
        NSHomeDirectory() + "/Library/Application Support/Dragoon"
    }

    /// Finds the Command Line Tools or Xcode and an SDK that links, without opening Apple's
    /// install prompt. The first command is `xcode-select -p`, and nothing under `/usr/bin`
    /// that shims a developer tool runs until it has found a directory. The choice is kept in
    /// `<dataDirectory>/toolchain.json`, and the SDKs are probed again when `clang --version`
    /// says something new.
    public static func detect(
        runner: any ProcessRunner, fs: any FileSystem,
        dataDirectory: String = Toolchain.defaultDataDirectory
    ) async -> ToolchainStatus {
        await Detection(runner: runner, fs: fs, dataDirectory: dataDirectory).run()
    }
}

private func encodeJSON(_ value: some Encodable) -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    // Strings and arrays of them always encode.
    return try! encoder.encode(value)
}

private struct Detection {
    static let xcodeSelect = "/usr/bin/xcode-select"
    static let xcrun = "/usr/bin/xcrun"
    static let pkgutil = "/usr/sbin/pkgutil"
    static let toolsPackage = "com.apple.pkg.CLTools_Executables"
    /// A fixed PATH keeps a Homebrew tool from answering for one of Apple's, and a fixed
    /// DEVELOPER_DIR keeps every command on the directory `xcode-select -p` named.
    static let path = "/usr/bin:/bin:/usr/sbin:/sbin"
    /// Seconds a query may take, which is what `xcode-select`, `xcrun`, `pkgutil` and
    /// `clang --version` get. A query that outlasts it reads as having failed.
    static let queryTimeout: TimeInterval = 10
    /// Seconds the probe may take to compile and link. One that outlasts it reads as that SDK
    /// not linking.
    static let probeTimeout: TimeInterval = 60
    static let probeSource = """
        #include <cstdio>

        int main() {
            std::printf("dragoon\\n");
            return 0;
        }

        """

    let runner: any ProcessRunner
    let fs: any FileSystem
    let dataDirectory: String

    var cachePath: String { dataDirectory + "/toolchain.json" }
    var probePath: String { dataDirectory + "/probe/toolchain.cpp" }

    func run() async -> ToolchainStatus {
        guard let developer = await output(Self.xcodeSelect, ["-p"]), fs.isDirectory(at: developer)
        else { return .missing }
        let environment = ["DEVELOPER_DIR": developer, "PATH": Self.path]
        guard let clang = await find("clang", environment),
            let clangxx = await find("clang++", environment),
            let make = await find("make", environment),
            let python3 = await find("python3", environment),
            let versionOutput = await output(clang, ["--version"], environment),
            let versionLine = versionOutput.split(whereSeparator: \.isNewline).first
        else { return .missing }
        let toolchain = Toolchain(
            developerDirectory: developer, clang: clang, clangxx: clangxx, make: make,
            python3: python3, sdk: "", clangVersion: String(versionLine))

        if let cached = cachedChoice(for: toolchain) { return .ready(cached) }

        try? fs.writeData(Data(Self.probeSource.utf8), to: probePath)
        var tried: [String] = []
        func links(_ sdk: String) async -> Bool {
            if tried.contains(sdk) { return false }
            tried.append(sdk)
            return await compiles(with: sdk, toolchain, environment)
        }
        func chosen(_ sdk: String) -> ToolchainStatus {
            var choice = toolchain
            choice.sdk = sdk
            try? fs.writeData(encodeJSON(choice), to: cachePath)
            return .ready(choice)
        }

        // 1. Full Xcode's own answer, which has a Platforms directory beside it.
        if fs.isDirectory(at: developer + "/Platforms"),
            let sdk = await output(Self.xcrun, ["--sdk", "macosx", "--show-sdk-path"], environment),
            await links(sdk)
        {
            return chosen(sdk)
        }
        // 2. The SDK the tools call MacOSX.sdk.
        let sdks = developer + "/SDKs"
        let generic = fs.resolvingSymlinks(at: sdks + "/MacOSX.sdk")
        if fs.isDirectory(at: generic), await links(generic) {
            return chosen(generic)
        }
        // 3. Every other one, newest first, but none from after the tools.
        let others = otherSDKs(in: sdks, excluding: tried)
        if !others.isEmpty {
            let toolsMajor = await toolsMajorVersion(environment)
            for other in others {
                if let major = other.version?.first, let toolsMajor, major > toolsMajor { continue }
                if await links(other.path) { return chosen(other.path) }
            }
        }
        return .noLinkableSDK(tried: tried)
    }

    /// The trimmed stdout of a command that exited 0, or nil when it failed or printed nothing.
    private func output(
        _ executable: String, _ arguments: [String], _ environment: [String: String]? = nil
    ) async -> String? {
        guard
            let result = try? await runner.run(
                executable, arguments, environment: environment, timeout: Self.queryTimeout),
            result.status == 0
        else { return nil }
        let text = result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }

    private func find(_ tool: String, _ environment: [String: String]) async -> String? {
        await output(Self.xcrun, ["--find", tool], environment)
    }

    /// The cached choice, when it was made for these same tools and its SDK is still there.
    private func cachedChoice(for toolchain: Toolchain) -> Toolchain? {
        guard let data = try? fs.readData(at: cachePath),
            let cached = try? JSONDecoder().decode(Toolchain.self, from: data),
            fs.isDirectory(at: cached.sdk)
        else { return nil }
        var comparable = cached
        comparable.sdk = toolchain.sdk
        return comparable == toolchain ? cached : nil
    }

    private func compiles(
        with sdk: String, _ toolchain: Toolchain, _ environment: [String: String]
    ) async -> Bool {
        let result = try? await runner.run(
            toolchain.clangxx, ["-isysroot", sdk, probePath, "-o", "/dev/null"],
            environment: environment, timeout: Self.probeTimeout)
        return result?.status == 0
    }

    private struct SDK {
        var path: String
        var version: [Int]?
    }

    /// The `MacOSX*.sdk` directories in `directory` that aren't in `excluding`. Each has its
    /// links resolved and is listed once, newest first.
    private func otherSDKs(in directory: String, excluding: [String]) -> [SDK] {
        let names = (try? fs.contentsOfDirectory(at: directory)) ?? []
        let paths = names
            .filter { $0.hasPrefix("MacOSX") && $0.hasSuffix(".sdk") }
            .map { fs.resolvingSymlinks(at: directory + "/" + $0) }
            .filter { fs.isDirectory(at: $0) && !excluding.contains($0) }
        return Set(paths).map { SDK(path: $0, version: Self.version(ofSDKAt: $0)) }
            .sorted { Self.isNewer($0, than: $1) }
    }

    /// 26.5 for `.../MacOSX26.5.sdk`, or nil for a name with no version in it.
    private static func version(ofSDKAt path: String) -> [Int]? {
        let name = (path as NSString).lastPathComponent
        guard name.hasPrefix("MacOSX"), name.hasSuffix(".sdk") else { return nil }
        let parts = name.dropFirst("MacOSX".count).dropLast(".sdk".count).split(
            separator: ".", omittingEmptySubsequences: false)
        let numbers = parts.compactMap { Int($0) }
        return numbers.isEmpty || numbers.count != parts.count ? nil : numbers
    }

    private static func isNewer(_ left: SDK, than right: SDK) -> Bool {
        switch (left.version, right.version) {
        case (let a?, let b?):
            for index in 0..<max(a.count, b.count) {
                let x = index < a.count ? a[index] : 0
                let y = index < b.count ? b[index] : 0
                if x != y { return x > y }
            }
            return left.path < right.path
        case (_?, nil): return true
        case (nil, _?): return false
        case (nil, nil): return left.path < right.path
        }
    }

    /// The Command Line Tools' major version, or nil when pkgutil can't say.
    private func toolsMajorVersion(_ environment: [String: String]) async -> Int? {
        guard
            let info = await output(
                Self.pkgutil, ["--pkg-info=" + Self.toolsPackage], environment)
        else { return nil }
        for line in info.split(separator: "\n") where line.hasPrefix("version:") {
            let value = line.dropFirst("version:".count).trimmingCharacters(in: .whitespaces)
            return value.split(separator: ".").first.flatMap { Int($0) }
        }
        return nil
    }
}
