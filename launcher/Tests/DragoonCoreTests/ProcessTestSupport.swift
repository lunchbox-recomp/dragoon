import Foundation

/// What the tests that start real processes need to see of them.
enum Processes {
    /// Whether any process is left in the group `pgid` leads. A zombie counts until it's collected,
    /// which init does soon after.
    static func groupExists(_ pgid: pid_t) -> Bool {
        kill(-pgid, 0) == 0 || errno != ESRCH
    }

    static func exists(_ pid: pid_t) -> Bool {
        kill(pid, 0) == 0 || errno != ESRCH
    }

    /// The pid a script wrote to `path`, or nil when it hasn't yet.
    static func pid(inFile path: String) -> pid_t? {
        guard let text = try? String(contentsOfFile: path, encoding: .utf8) else { return nil }
        return pid_t(text.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    /// Polls until `condition` holds, for at most `timeout` seconds. Returns whether it did.
    static func eventually(timeout: Double = 10, _ condition: () -> Bool) async -> Bool {
        let deadline = ContinuousClock.now + .seconds(timeout)
        while ContinuousClock.now < deadline {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(20))
        }
        return condition()
    }

    /// Waits for a script to write its pid to `path`.
    static func waitForPid(inFile path: String) async -> pid_t? {
        _ = await eventually { pid(inFile: path) != nil }
        return pid(inFile: path)
    }

    /// Kills whatever a failing test left running in the group.
    static func killGroup(_ pgid: pid_t?) {
        if let pgid { killpg(pgid, SIGKILL) }
    }
}

/// `text` as one shell word, for paths with spaces in a script. The paths here hold no quote.
func shellWord(_ text: String) -> String {
    "'" + text + "'"
}
