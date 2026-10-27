import Foundation

/// How a process started by `ProcessGroup.run` ended.
struct ProcessGroupOutcome: Equatable, Sendable {
    /// The exit code, or the signal number when a signal ended the process.
    var status: Int32
    /// Whether a signal ended the process rather than the process itself.
    var signaled: Bool
    /// Whether the timeout ran out while the process, or something it started, was still running.
    var timedOut: Bool
    /// Whether the task was cancelled while the process, or something it started, was still
    /// running.
    var cancelled: Bool
}

/// What a process leaves when its exit can't be collected, as when SIGCHLD is ignored or
/// something else has collected it. `code` is the errno of the failed wait.
struct ProcessWaitFailure: Error, Equatable {
    var code: Int32
}

/// Starts a process as the leader of a process group of its own, so one signal reaches it and
/// every helper it starts. Both real runners start their children here, which is where a
/// timeout or a cancelled task stops them.
enum ProcessGroup {
    /// Seconds between SIGTERM and SIGKILL when the calling task is cancelled.
    static let killGrace: TimeInterval = 10

    /// Seconds a pipe held open by something that outlived the SIGKILL is waited on before it is
    /// given up on.
    private static let abandonDelay: TimeInterval = 1

    /// Seconds between looks at whether a group being stopped is empty yet.
    private static let groupCheckInterval: TimeInterval = 0.02

    /// Runs `executable` and hands what it prints to `onStdout` and `onStderr` as it arrives, each
    /// from a thread of its own. Returns once the process has exited and both pipes have closed.
    ///
    /// A process still running after `timeout` seconds, or one that left something running that
    /// holds a pipe, is sent SIGKILL together with its group. Canceling the calling task sends
    /// the group SIGTERM, then SIGKILL `killGrace` seconds later if anything is left. Either way
    /// this returns only once the group holds nothing but the exited process, or a second after
    /// the SIGKILL, and the outcome says what stopped it. Throws when the process can't be
    /// started, or `CancellationError` when the task was canceled before it started.
    static func run(
        _ executable: String, _ arguments: [String], environment: [String: String]?,
        timeout: TimeInterval?, killGrace: TimeInterval = ProcessGroup.killGrace,
        onStdout: @escaping @Sendable (Data) -> Void,
        onStderr: @escaping @Sendable (Data) -> Void
    ) async throws -> ProcessGroupOutcome {
        try Task.checkCancellation()
        let control = Control(killGrace: killGrace)
        return try await withTaskCancellationHandler {
            // Waiting for a process blocks, so it runs off the concurrency pool.
            try await withCheckedThrowingContinuation { continuation in
                DispatchQueue.global().async {
                    continuation.resume(with: Result {
                        try runBlocking(
                            executable, arguments, environment, timeout, control, onStdout, onStderr)
                    })
                }
            }
        } onCancel: {
            control.cancel()
        }
    }

    private static func runBlocking(
        _ executable: String, _ arguments: [String], _ environment: [String: String]?,
        _ timeout: TimeInterval?, _ control: Control,
        _ onStdout: @escaping @Sendable (Data) -> Void,
        _ onStderr: @escaping @Sendable (Data) -> Void
    ) throws -> ProcessGroupOutcome {
        let child = try spawn(executable, arguments, environment)
        control.begin(pid: child.pid, timeout: timeout)
        for (descriptor, handler) in [(child.stdout, onStdout), (child.stderr, onStderr)] {
            DispatchQueue.global().async {
                drain(descriptor, handler)
                control.readerFinished()
            }
        }
        // The exit is waited for without collecting it, so the pid stays taken while helpers
        // are left and a signal to the group can never reach another process's.
        var info = siginfo_t()
        while waitid(P_PID, id_t(child.pid), &info, WEXITED | WNOWAIT) < 0, errno == EINTR {}
        control.awaitReaders()
        control.awaitGroupEmpty()
        return try control.reap()
    }

    private static func drain(_ descriptor: Int32, _ handler: @Sendable (Data) -> Void) {
        defer { close(descriptor) }
        var buffer = [UInt8](repeating: 0, count: 65536)
        while true {
            let got = buffer.withUnsafeMutableBytes { read(descriptor, $0.baseAddress, $0.count) }
            if got > 0 {
                handler(Data(buffer[..<got]))
            } else if got == 0 || errno != EINTR {
                return
            }
        }
    }

    /// Starts the process in a group of its own with stdin on /dev/null, and gives back its pid
    /// and the read ends of its stdout and stderr. Only those three descriptors reach it, and it
    /// starts with default signal handling and an empty signal mask, whatever this process has.
    private static func spawn(
        _ executable: String, _ arguments: [String], _ environment: [String: String]?
    ) throws -> (pid: pid_t, stdout: Int32, stderr: Int32) {
        var outPipe: [Int32] = [-1, -1]
        var errPipe: [Int32] = [-1, -1]
        guard pipe(&outPipe) == 0 else { throw posixError(errno) }
        outPipe.forEach { _ = fcntl($0, F_SETFD, FD_CLOEXEC) }
        guard pipe(&errPipe) == 0 else {
            let failure = errno
            outPipe.forEach { close($0) }
            throw posixError(failure)
        }
        // Close-on-exec from the start, so a spawn that doesn't ask for CLOEXEC_DEFAULT, started
        // from another thread meanwhile, can't inherit a write end and hold the pipe open. The
        // dup2 actions below give the child its own copies, which are not close-on-exec.
        errPipe.forEach { _ = fcntl($0, F_SETFD, FD_CLOEXEC) }

        var actions: posix_spawn_file_actions_t?
        posix_spawn_file_actions_init(&actions)
        defer { posix_spawn_file_actions_destroy(&actions) }
        posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0)
        posix_spawn_file_actions_adddup2(&actions, outPipe[1], 1)
        posix_spawn_file_actions_adddup2(&actions, errPipe[1], 2)

        var attributes: posix_spawnattr_t?
        posix_spawnattr_init(&attributes)
        defer { posix_spawnattr_destroy(&attributes) }
        var everySignal = sigset_t()
        sigfillset(&everySignal)
        var noSignals = sigset_t()
        sigemptyset(&noSignals)
        posix_spawnattr_setsigdefault(&attributes, &everySignal)
        posix_spawnattr_setsigmask(&attributes, &noSignals)
        posix_spawnattr_setpgroup(&attributes, 0)
        posix_spawnattr_setflags(
            &attributes,
            Int16(
                POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSIGDEF
                    | POSIX_SPAWN_SETSIGMASK))

        var argv = ([executable] + arguments).map { strdup($0) }
        argv.append(nil)
        var envp = (environment ?? ProcessInfo.processInfo.environment)
            .map { strdup("\($0.key)=\($0.value)") }
        envp.append(nil)
        defer {
            argv.forEach { free($0) }
            envp.forEach { free($0) }
        }

        var pid: pid_t = 0
        let failure = posix_spawn(&pid, executable, &actions, &attributes, argv, envp)
        close(outPipe[1])
        close(errPipe[1])
        guard failure == 0 else {
            close(outPipe[0])
            close(errPipe[0])
            throw posixError(failure)
        }
        return (pid, outPipe[0], errPipe[0])
    }

    private static func posixError(_ code: Int32) -> POSIXError {
        POSIXError(POSIXErrorCode(rawValue: code) ?? .EIO)
    }

    /// What can stop a running process, and the wait for it to end. Everything it holds is
    /// guarded by one condition, which also wakes the waiter when a pipe closes or a SIGKILL goes
    /// out.
    private final class Control: @unchecked Sendable {
        private enum Due {
            case timeout, kill
        }

        private let condition = NSCondition()
        private let killGrace: TimeInterval
        private var pid: pid_t = 0
        /// Between the process starting and it being collected. Nothing is signaled outside it.
        private var live = false
        private var cancelRequested = false
        private var cancelled = false
        private var timedOut = false
        private var killSentAt: Date?
        private var openPipes = 2
        private var timers: [DispatchWorkItem] = []

        init(killGrace: TimeInterval) {
            self.killGrace = killGrace
        }

        /// Called once the process exists. A cancel that came before it takes effect now.
        func begin(pid: pid_t, timeout: TimeInterval?) {
            condition.lock()
            defer { condition.unlock() }
            self.pid = pid
            live = true
            if let timeout { schedule(.timeout, after: timeout) }
            if cancelRequested { terminate() }
        }

        func cancel() {
            condition.lock()
            defer { condition.unlock() }
            guard !cancelRequested else { return }
            cancelRequested = true
            if live { terminate() }
        }

        func readerFinished() {
            condition.lock()
            defer { condition.unlock() }
            openPipes -= 1
            condition.broadcast()
        }

        /// Waits until both pipes have closed. Once a SIGKILL has gone out, something that still
        /// holds one a second later is given up on, since it isn't in the group.
        func awaitReaders() {
            condition.lock()
            defer { condition.unlock() }
            while openPipes > 0 {
                if let sent = killSentAt {
                    if !condition.wait(until: sent.addingTimeInterval(ProcessGroup.abandonDelay)) {
                        return
                    }
                } else {
                    condition.wait()
                }
            }
        }

        /// After a SIGTERM or a SIGKILL has gone out, waits until nothing but the exited leader
        /// is left in the group, or until a second after the SIGKILL. The leader stays
        /// uncollected meanwhile, so its pid can't be reused while the timer can still fire.
        /// A group nobody has tried to stop is left alone.
        func awaitGroupEmpty() {
            condition.lock()
            defer { condition.unlock() }
            while cancelled || killSentAt != nil {
                if !othersInGroup() { return }
                if let sent = killSentAt, Date() >= sent.addingTimeInterval(ProcessGroup.abandonDelay) {
                    return
                }
                _ = condition.wait(until: Date().addingTimeInterval(ProcessGroup.groupCheckInterval))
            }
        }

        /// Whether any process but the leader itself is in the leader's group.
        private func othersInGroup() -> Bool {
            var members = [pid_t](repeating: 0, count: 1024)
            let bytes = members.withUnsafeMutableBytes {
                proc_listpids(UInt32(PROC_PGRP_ONLY), UInt32(pid), $0.baseAddress, Int32($0.count))
            }
            guard bytes > 0 else { return false }
            return members.prefix(Int(bytes) / MemoryLayout<pid_t>.size).contains {
                $0 != 0 && $0 != pid
            }
        }

        /// Collects the exit, which ends the signaling. Throws when the exit can't be collected,
        /// as when something else has already, so a lost status never reads as exit 0.
        func reap() throws -> ProcessGroupOutcome {
            condition.lock()
            defer { condition.unlock() }
            var raw: Int32 = 0
            var failure: Int32 = 0
            while waitpid(pid, &raw, 0) < 0 {
                if errno == EINTR { continue }
                failure = errno
                break
            }
            live = false
            timers.forEach { $0.cancel() }
            if failure != 0 { throw ProcessWaitFailure(code: failure) }
            let signal = raw & 0x7f
            return ProcessGroupOutcome(
                status: signal == 0 ? (raw >> 8) & 0xff : signal, signaled: signal != 0,
                timedOut: timedOut, cancelled: cancelled)
        }

        private func terminate() {
            cancelled = true
            killpg(pid, SIGTERM)
            schedule(.kill, after: killGrace)
        }

        private func schedule(_ due: Due, after seconds: TimeInterval) {
            let timer = DispatchWorkItem { [self] in fire(due) }
            timers.append(timer)
            DispatchQueue.global().asyncAfter(deadline: .now() + seconds, execute: timer)
        }

        private func fire(_ due: Due) {
            condition.lock()
            defer { condition.unlock() }
            guard live else { return }
            if due == .timeout { timedOut = true }
            killpg(pid, SIGKILL)
            if killSentAt == nil { killSentAt = Date() }
            condition.broadcast()
        }
    }
}
