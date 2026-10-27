import CryptoKit
import Foundation

/// A disc image format the build doesn't read. The player converts it to an ISO first.
public enum UnsupportedDiscFormat: String, CaseIterable, Equatable, Sendable {
    case rvz = "RVZ"
    case gcz = "GCZ"
    case wia = "WIA"
    case wbfs = "WBFS"
}

/// What `checkDisc` found out about a disc image.
public enum DiscCheck: Equatable, Sendable {
    /// The right game and revision, in a format the build reads.
    case ok
    /// Another game. `foundID` is the image's disc ID, with each byte that isn't printable ASCII
    /// shown as `?`.
    case wrongGame(foundID: String)
    /// The right game, but its main.dol isn't the supported build's. `foundSHA1` is the
    /// main.dol's, in lowercase hex.
    case wrongRevision(foundSHA1: String)
    /// A format the build doesn't read, named by its magic.
    case needsConversion(format: UnsupportedDiscFormat)
    /// A file that isn't there, can't be read, or ends before the check is through.
    case unreadable(reason: String)
}

extension DiscCheck {
    public var isOK: Bool {
        if case .ok = self { return true }
        return false
    }

    /// The result as JSON, keyed by `status` and then by what that status carries.
    public func json() -> String {
        String(decoding: encodeJSON(self), as: UTF8.self)
    }
}

extension DiscCheck: Encodable {
    private enum Keys: String, CodingKey {
        case status, foundID, foundSHA1, format, reason
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: Keys.self)
        switch self {
        case .ok:
            try container.encode("ok", forKey: .status)
        case .wrongGame(let foundID):
            try container.encode("wrongGame", forKey: .status)
            try container.encode(foundID, forKey: .foundID)
        case .wrongRevision(let foundSHA1):
            try container.encode("wrongRevision", forKey: .status)
            try container.encode(foundSHA1, forKey: .foundSHA1)
        case .needsConversion(let format):
            try container.encode("needsConversion", forKey: .status)
            try container.encode(format.rawValue, forKey: .format)
        case .unreadable(let reason):
            try container.encode("unreadable", forKey: .status)
            try container.encode(reason, forKey: .reason)
        }
    }
}

/// Checks that the image at `path` is the game `expectedID` names and the build
/// `expectedDOLSHA1` names, in a format the build reads. It follows
/// `gcn-recomp/recomp/extract_dol.py` and `recomp/dol.py`.
///
/// The disc ID is the image's first 6 bytes. main.dol starts at the big-endian word at 0x420.
/// Its length is the largest offset plus size among its 18 sections that have a size, with the
/// offsets at 0x00 and the sizes at 0x90 of its header, and the SHA-1 covers that many bytes from
/// its start. `expectedDOLSHA1` is compared as given, so it has to be lowercase hex, as
/// `source-info.json` keeps it.
///
/// The image is read through a file handle a piece at a time, so a 1.4 GB disc never sits in
/// memory. Reading is the only thing this does to the file.
public func checkDisc(
    at path: String, expectedID: String, expectedDOLSHA1: String,
    fs: any FileSystem = SystemFileSystem()
) -> DiscCheck {
    let file: any FileReader
    do {
        file = try fs.openReader(at: path)
    } catch {
        return .unreadable(
            reason: "The disc image couldn't be opened (\(error.localizedDescription)).")
    }
    do {
        return try inspect(file, expectedID: expectedID, expectedDOLSHA1: expectedDOLSHA1)
    } catch let cutShort as DiscUnreadable {
        return .unreadable(reason: cutShort.reason)
    } catch {
        return .unreadable(
            reason: "The disc image couldn't be read (\(error.localizedDescription)).")
    }
}

// MARK: - The check

/// Where things are on a disc and in a DOL, from `extract_dol.py`.
private enum Layout {
    static let idLength = 6
    static let headerLength = 0x440
    static let dolOffsetWord = 0x420
    static let dolHeaderLength = 0x100
    static let dolSectionCount = 18
    static let dolOffsetsAt = 0x00
    static let dolSizesAt = 0x90
    /// The most one read asks of the file, which is also the most the check holds at once.
    static let chunkLength = 1 << 20
}

/// Each magic is the word Dolphin reads at offset 0 of the file. They are little-endian, as
/// Dolphin's own comments say.
private enum Magic {
    /// `CISO_MAGIC`, Source/Core/DiscIO/CISOBlob.h:15. `dol.py` tests for the same four bytes.
    static let ciso: UInt32 = 0x4F53_4943
    /// `WIA_MAGIC`, Source/Core/DiscIO/WIABlob.h:40.
    static let wia: UInt32 = 0x0141_4957
    /// `RVZ_MAGIC`, Source/Core/DiscIO/WIABlob.h:41.
    static let rvz: UInt32 = 0x015A_5652
    /// `GCZ_MAGIC`, Source/Core/DiscIO/CompressedBlob.h:25.
    static let gcz: UInt32 = 0xB10B_C001
    /// `WBFS_MAGIC`, Source/Core/DiscIO/WbfsBlob.h:16.
    static let wbfs: UInt32 = 0x5346_4257
}

private struct DiscUnreadable: Error {
    var reason: String

    static let cutShort = DiscUnreadable(reason: "The disc image is cut short.")
}

private func inspect(
    _ file: any FileReader, expectedID: String, expectedDOLSHA1: String
) throws -> DiscCheck {
    let plain = PlainImage(file: file)
    let image: any DiscBytes
    switch littleEndianWord(try plain.read(at: 0, count: 4), at: 0) {
    case Magic.wia: return .needsConversion(format: .wia)
    case Magic.rvz: return .needsConversion(format: .rvz)
    case Magic.gcz: return .needsConversion(format: .gcz)
    case Magic.wbfs: return .needsConversion(format: .wbfs)
    case Magic.ciso: image = try CISOImage(file: file)
    default: image = plain
    }

    let header = try image.read(at: 0, count: Layout.headerLength)
    let found = header.prefix(Layout.idLength)
    guard found.elementsEqual(expectedID.utf8) else {
        return .wrongGame(foundID: printable(found))
    }

    let dolOffset = UInt64(bigEndianWord(header, at: Layout.dolOffsetWord))
    let dolHeader = try image.read(at: dolOffset, count: Layout.dolHeaderLength)
    var dolLength: UInt64 = 0
    for section in 0..<Layout.dolSectionCount {
        let size = UInt64(bigEndianWord(dolHeader, at: Layout.dolSizesAt + 4 * section))
        if size == 0 { continue }
        let offset = UInt64(bigEndianWord(dolHeader, at: Layout.dolOffsetsAt + 4 * section))
        dolLength = max(dolLength, offset + size)
    }
    guard dolLength > 0 else {
        throw DiscUnreadable(reason: "The disc's main.dol lists no sections.")
    }

    var hash = Insecure.SHA1()
    var done: UInt64 = 0
    while done < dolLength {
        let count = Int(min(dolLength - done, UInt64(Layout.chunkLength)))
        hash.update(data: try image.read(at: dolOffset + done, count: count))
        done += UInt64(count)
    }
    let sha1 = hash.finalize().map { String(format: "%02x", $0) }.joined()
    return sha1 == expectedDOLSHA1 ? .ok : .wrongRevision(foundSHA1: sha1)
}

private func printable(_ bytes: Data) -> String {
    String(bytes.map { (0x20...0x7E).contains($0) ? Character(Unicode.Scalar($0)) : "?" })
}

private func littleEndianWord(_ data: Data, at offset: Int) -> UInt32 {
    let start = data.startIndex + offset
    return (0..<4).reduce(0) { $0 | UInt32(data[start + $1]) << (8 * UInt32($1)) }
}

private func bigEndianWord(_ data: Data, at offset: Int) -> UInt32 {
    let start = data.startIndex + offset
    return (0..<4).reduce(0) { $0 << 8 | UInt32(data[start + $1]) }
}

// MARK: - The image as a run of bytes

/// A disc image as one run of bytes, whatever it's stored as.
private protocol DiscBytes {
    /// Exactly `count` bytes at `offset`, or `DiscUnreadable` when the image ends first.
    func read(at offset: UInt64, count: Int) throws -> Data
}

private struct PlainImage: DiscBytes {
    let file: any FileReader

    func read(at offset: UInt64, count: Int) throws -> Data {
        let data = try file.read(at: offset, count: count)
        guard data.count == count else { throw DiscUnreadable.cutShort }
        return data
    }
}

/// A CISO is a 0x8000-byte header followed by the stored blocks in order. The header is "CISO",
/// a little-endian block size, then a byte per block that says whether it's stored, which only a
/// 1 does. A block that isn't stored reads as zeros. The map covers 0x8000 - 8 blocks, and the
/// image ends where it does, as it does in Dolphin's `CISOFileReader::Read`.
private struct CISOImage: DiscBytes {
    static let headerLength = 0x8000
    static let mapStart = 8

    let file: PlainImage
    let blockSize: UInt64
    /// For each block the map covers, its place among the stored blocks, or nil when it has none.
    let slots: [UInt64?]

    init(file: any FileReader) throws {
        let plain = PlainImage(file: file)
        let header = try plain.read(at: 0, count: Self.headerLength)
        let size = littleEndianWord(header, at: 4)
        guard size != 0 else {
            throw DiscUnreadable(reason: "The disc image is a CISO with a block size of zero.")
        }
        var stored: UInt64 = 0
        var slots: [UInt64?] = []
        for byte in header.dropFirst(Self.mapStart) {
            if byte == 1 {
                slots.append(stored)
                stored += 1
            } else {
                slots.append(nil)
            }
        }
        self.file = plain
        self.blockSize = UInt64(size)
        self.slots = slots
    }

    func read(at offset: UInt64, count: Int) throws -> Data {
        var data = Data(capacity: count)
        var offset = offset
        var left = count
        while left > 0 {
            let block = offset / blockSize
            let within = offset % blockSize
            guard block < UInt64(slots.count) else { throw DiscUnreadable.cutShort }
            let piece = Int(min(UInt64(left), blockSize - within))
            if let slot = slots[Int(block)] {
                let at = UInt64(Self.headerLength) + slot * blockSize + within
                data.append(try file.read(at: at, count: piece))
            } else {
                data.append(Data(count: piece))
            }
            offset += UInt64(piece)
            left -= piece
        }
        return data
    }
}

// MARK: - The disc a snapshot builds

/// The disc ID and main.dol SHA-1 a source snapshot builds, which its `source-info.json` keeps as
/// `disc_id` and `dol_sha1`.
public struct ExpectedDisc: Equatable, Sendable {
    public var id: String
    public var dolSHA1: String

    public init(id: String, dolSHA1: String) {
        self.id = id
        self.dolSHA1 = dolSHA1
    }

    /// Reads the two fields from the file at `path`. Any other field is ignored, and one of the
    /// two that is missing or malformed throws `SourceInfoError`, as `tools/source_info.py` would
    /// refuse it: a disc ID is six of 0-9 and A-Z, and a SHA-1 is forty of 0-9 and a-f.
    public static func read(
        at path: String, fs: any FileSystem = SystemFileSystem()
    ) throws -> ExpectedDisc {
        let data: Data
        do {
            data = try fs.readData(at: path)
        } catch {
            throw SourceInfoError("\(path): can't be read (\(error.localizedDescription))")
        }
        let parsed: Any
        do {
            parsed = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw SourceInfoError("\(path): not JSON")
        }
        guard let fields = parsed as? [String: Any] else {
            throw SourceInfoError("\(path): not a JSON object")
        }
        guard let id = fields["disc_id"] as? String, isValid(id, length: 6, allowing: idBytes)
        else { throw SourceInfoError("\(path): disc_id is missing or malformed") }
        guard let sha1 = fields["dol_sha1"] as? String,
            isValid(sha1, length: 40, allowing: sha1Bytes)
        else { throw SourceInfoError("\(path): dol_sha1 is missing or malformed") }
        return ExpectedDisc(id: id, dolSHA1: sha1)
    }

    private static let idBytes = Array("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ".utf8)
    private static let sha1Bytes = Array("0123456789abcdef".utf8)

    private static func isValid(_ value: String, length: Int, allowing bytes: [UInt8]) -> Bool {
        value.utf8.count == length && value.utf8.allSatisfy { bytes.contains($0) }
    }
}

/// Why a `source-info.json` couldn't be used. It names the file.
public struct SourceInfoError: Error, Equatable, CustomStringConvertible, Sendable {
    public var description: String

    init(_ description: String) {
        self.description = description
    }
}

// MARK: - The command line

public struct CheckDiscCommandResult: Equatable, Sendable {
    public var stdout: String
    public var stderr: String
    public var status: Int32

    public init(stdout: String, stderr: String, status: Int32) {
        self.stdout = stdout
        self.stderr = stderr
        self.status = status
    }
}

/// `Dragoon --check-disc PATH [--source-info FILE]`, given the arguments after `--check-disc`.
/// It checks the image at PATH against the disc `FILE` names, which is `bundledSourceInfo` when
/// no FILE is given, and prints the result as JSON. The status is 0 for `ok`, 1 for any other
/// result, and 2 when the arguments or the source-info are unusable, which prints on stderr.
public func runCheckDisc(
    _ arguments: [String], bundledSourceInfo: String, fs: any FileSystem = SystemFileSystem()
) -> CheckDiscCommandResult {
    var sourceInfo = bundledSourceInfo
    switch arguments.count {
    case 1: break
    case 3 where arguments[1] == "--source-info": sourceInfo = arguments[2]
    default:
        return CheckDiscCommandResult(
            stdout: "", stderr: "usage: Dragoon --check-disc PATH [--source-info FILE]\n",
            status: 2)
    }
    let expected: ExpectedDisc
    do {
        expected = try ExpectedDisc.read(at: sourceInfo, fs: fs)
    } catch {
        return CheckDiscCommandResult(stdout: "", stderr: "\(error)\n", status: 2)
    }
    let check = checkDisc(
        at: arguments[0], expectedID: expected.id, expectedDOLSHA1: expected.dolSHA1, fs: fs)
    return CheckDiscCommandResult(
        stdout: check.json() + "\n", stderr: "", status: check.isOK ? 0 : 1)
}
