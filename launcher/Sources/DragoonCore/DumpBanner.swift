import Foundation

/// `Dragoon --dump-banner DISC OUT.png`, given every argument after the program's name. It
/// writes the banner of the disc image at DISC to OUT.png, prints the format and the first info
/// block's names as JSON, and prints how long reading and decoding took on stderr. The status
/// is 0 when the PNG is written, 1 when DISC is a folder, the disc can't be opened, has no
/// banner that can be read or the PNG can't be written, and 2 for any other arguments. Each 1
/// says which. Only a regular file opens, and a FIFO is refused without waiting for a writer.
public func runDumpBanner(_ arguments: [String], fs: any FileSystem = SystemFileSystem())
    -> CommandResult
{
    guard arguments.count == 3, arguments[0] == "--dump-banner" else {
        return CommandResult(
            stdout: "", stderr: "usage: Dragoon --dump-banner DISC OUT.png\n", status: 2)
    }
    let disc = arguments[1]
    let out = arguments[2]
    if fs.isDirectory(at: disc) {
        return CommandResult(
            stdout: "", stderr: "\(disc): is a folder, not a disc image\n", status: 1)
    }
    let clock = ContinuousClock()
    let start = clock.now
    let file: any FileReader
    do {
        file = try fs.openReader(at: disc)
    } catch {
        return CommandResult(
            stdout: "", stderr: "\(disc): can't be opened (\(error.localizedDescription))\n",
            status: 1)
    }
    let banner = DiscBanner.read(from: file)
    let took = clock.now - start
    guard let banner else {
        return CommandResult(
            stdout: "", stderr: "\(disc): no opening.bnr on the root that can be read\n",
            status: 1)
    }
    guard let png = banner.png() else {
        return CommandResult(
            stdout: "", stderr: "the banner couldn't be made into a PNG\n", status: 1)
    }
    do {
        try fs.writeData(png, to: out)
    } catch {
        return CommandResult(
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
    return CommandResult(
        stdout: String(decoding: encodeJSON(fields), as: UTF8.self) + "\n",
        stderr: String(format: "read and decoded in %.3f ms\n", milliseconds), status: 0)
}
