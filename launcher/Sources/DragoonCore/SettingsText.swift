import Foundation

/// The engine's `settings.txt` as bytes, read and changed the way gcn-recomp's
/// `runtime/settings.cpp` does it, so the launcher and the game's own Display page write the
/// same file the same way.
///
/// One `key value` a line, the value being the rest of the line without the spaces, tabs and
/// CRs around it. A blank line, or one whose first character past any spaces is `#`, holds no
/// key. A UTF-8 byte order mark at the start isn't part of the first line. Bytes that aren't
/// UTF-8 stay as they are.
public enum SettingsText {
    public static let fileName = "settings.txt"

    private static let byteOrderMark: [UInt8] = [0xEF, 0xBB, 0xBF]
    private static let newline: UInt8 = 0x0A
    private static let carriageReturn: UInt8 = 0x0D

    /// Each line's key and value, in order, skipping lines that hold none. A key can come more
    /// than once, and the engine's load takes the last line whose value it accepts.
    public static func entries(in data: Data) -> [(key: [UInt8], value: [UInt8])] {
        lines(of: data).lines.compactMap(split)
    }

    /// `data` with each given key set to its value, as `settings_save` writes it.
    ///
    /// Each line of a given key becomes `key value`, keeping a CR the line ended with. A given
    /// key the file lacks is added at the end. That line, and a last line the file left without a
    /// newline, end as the file's first newline does, in CR LF or LF. Every other line is kept
    /// byte for byte, and so is a byte order mark at the start.
    public static func setting(_ values: [(key: String, value: String)], in data: Data) -> Data {
        let file = lines(of: data)
        let owned = values.map { (key: Array($0.key.utf8), value: Array($0.value.utf8)) }
        var written = [Bool](repeating: false, count: owned.count)
        var text = file.byteOrderMark ? byteOrderMark : []
        let ending: [UInt8] = file.crlf ? [carriageReturn, newline] : [newline]
        for (n, line) in file.lines.enumerated() {
            var out = line
            if let (key, _) = split(line) {
                for (i, pair) in owned.enumerated() where pair.key == key {
                    out = key + [0x20] + pair.value + (line.last == carriageReturn ? [carriageReturn] : [])
                    written[i] = true
                }
            }
            let last = n + 1 == file.lines.count
            text += out + (file.open && last && line.last != carriageReturn ? ending : [newline])
        }
        for (i, pair) in owned.enumerated() where !written[i] {
            text += pair.key + [0x20] + pair.value + ending
        }
        return Data(text)
    }

    /// A file's lines without their newlines, and what `setting` keeps of its shape: whether it
    /// starts with a byte order mark, whether its first newline follows a CR and whether its last
    /// line has no newline.
    private struct Lines {
        var lines: [[UInt8]] = []
        var byteOrderMark = false
        var crlf = false
        var open = false
    }

    private static func lines(of data: Data) -> Lines {
        var bytes = [UInt8](data)
        var file = Lines()
        file.byteOrderMark = bytes.starts(with: byteOrderMark)
        if file.byteOrderMark { bytes.removeFirst(byteOrderMark.count) }
        if let first = bytes.firstIndex(of: newline) {
            file.crlf = first > 0 && bytes[first - 1] == carriageReturn
        }
        file.open = !bytes.isEmpty && bytes.last != newline
        var start = 0
        while start < bytes.count {
            let end = bytes[start...].firstIndex(of: newline) ?? bytes.count
            file.lines.append(Array(bytes[start..<end]))
            start = end + 1
        }
        return file
    }

    /// `bytes` without the spaces, tabs and CRs around them.
    private static func trimmed(_ bytes: ArraySlice<UInt8>) -> ArraySlice<UInt8> {
        let space: (UInt8) -> Bool = { $0 == 0x20 || $0 == 0x09 || $0 == carriageReturn }
        guard let first = bytes.firstIndex(where: { !space($0) }),
            let last = bytes.lastIndex(where: { !space($0) })
        else { return [] }
        return bytes[first...last]
    }

    /// A line's key and value, or nil for a blank line or a comment.
    private static func split(_ line: [UInt8]) -> (key: [UInt8], value: [UInt8])? {
        let text = trimmed(line[...])
        guard let first = text.first, first != UInt8(ascii: "#") else { return nil }
        let end = text.firstIndex { $0 == 0x20 || $0 == 0x09 } ?? text.endIndex
        return (Array(text[..<end]), Array(trimmed(text[end...])))
    }
}
