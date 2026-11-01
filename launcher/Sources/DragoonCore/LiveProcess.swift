import Foundation

/// What the kernel says about a process by its pid. The process needn't be this one's child.
public enum LiveProcess {
    /// When the process `pid` started, in microseconds since 1970, or nil when there's none.
    static func startTime(of pid: pid_t) -> UInt64? {
        var info = proc_bsdinfo()
        let size = Int32(MemoryLayout<proc_bsdinfo>.size)
        guard pid > 0, proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, size) == size else { return nil }
        return info.pbi_start_tvsec * 1_000_000 + info.pbi_start_tvusec
    }

    /// The path of the file the process `pid` runs, with every link resolved, or nil when
    /// there's none.
    static func executable(of pid: pid_t) -> String? {
        // PROC_PIDPATHINFO_MAXSIZE, which Swift doesn't import.
        var path = [UInt8](repeating: 0, count: 4 * Int(MAXPATHLEN))
        let length = pid > 0 ? proc_pidpath(pid, &path, UInt32(path.count)) : 0
        return length > 0 ? String(decoding: path[..<Int(length)], as: UTF8.self) : nil
    }

    /// Returns once the process `pid` has ended, or at once when there's none. kqueue's exit
    /// note works for a process that isn't this one's child, and Dispatch gives it at once for
    /// a pid with no process.
    public static func waitForEnd(of pid: pid_t) async {
        await withCheckedContinuation { (ended: CheckedContinuation<Void, Never>) in
            let source = DispatchSource.makeProcessSource(
                identifier: pid, eventMask: .exit, queue: .global())
            source.setEventHandler {
                source.cancel()
                ended.resume()
            }
            source.resume()
        }
    }
}
