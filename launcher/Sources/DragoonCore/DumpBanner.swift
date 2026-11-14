import Foundation

/// `Dragoon --dump-banner DISC OUT.png`, given every argument after the program's name. It
/// writes the banner of the disc image at DISC to OUT.png, prints the format and the first info
/// block's names as JSON, and prints how long reading and decoding took on stderr. The status
/// is 0 when the PNG is written, 1 when the disc has no banner that can be read or the PNG
/// can't be written, and 2 for any other arguments.
public func runDumpBanner(_ arguments: [String], fs: any FileSystem = SystemFileSystem())
    -> CheckDiscCommandResult
{
    guard arguments.count == 3, arguments[0] == "--dump-banner" else {
        return CheckDiscCommandResult(
            stdout: "", stderr: "usage: Dragoon --dump-banner DISC OUT.png\n", status: 2)
    }
    let disc = arguments[1]
    let out = arguments[2]
    let clock = ContinuousClock()
    let start = clock.now
    let banner = DiscBanner.read(at: disc, fs: fs)
    let took = clock.now - start
    guard let banner else {
        return CheckDiscCommandResult(
            stdout: "", stderr: "\(disc): no opening.bnr found on the root\n", status: 1)
    }
    guard let png = banner.png() else {
        return CheckDiscCommandResult(
            stdout: "", stderr: "the banner couldn't be made into a PNG\n", status: 1)
    }
    do {
        try fs.writeData(png, to: out)
    } catch {
        return CheckDiscCommandResult(
            stdout: "", stderr: "\(out): can't be written (\(error.localizedDescription))\n",
            status: 1)
    }
    let first = banner.texts[0]
    let fields = [
        "format": banner.format.rawValue, "shortName": first.shortName,
        "shortMaker": first.shortMaker, "longName": first.longName, "longMaker": first.longMaker,
    ]
    let milliseconds = Double(took.components.seconds) * 1000
        + Double(took.components.attoseconds) / 1e15
    return CheckDiscCommandResult(
        stdout: String(decoding: encodeJSON(fields), as: UTF8.self) + "\n",
        stderr: String(format: "read and decoded in %.3f ms\n", milliseconds), status: 0)
}
