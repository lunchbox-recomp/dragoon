/// What one of the launcher's command-line modes prints and exits with.
public struct CommandResult: Equatable, Sendable {
    public var stdout: String
    public var stderr: String
    public var status: Int32

    public init(stdout: String, stderr: String, status: Int32) {
        self.stdout = stdout
        self.stderr = stderr
        self.status = status
    }
}
