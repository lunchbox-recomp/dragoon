// Runs a program and keeps what it prints, with a time limit and no shell.
#pragma once
#include <string>
#include <vector>

namespace dragoon {

struct ChildResult {
    enum class End { exited, signaled, timed_out, not_started };
    End end = End::not_started;
    int code = 0;     // the exit code, the signal, or errno when it didn't start
    std::string out;  // what it wrote on stdout
};

// Runs `argv[0]`, a path that isn't searched for, with `argv` as its arguments and `env` as
// its whole environment, in the working directory. Its stdin is /dev/null, its stdout is kept
// and its stderr is this process's. It gets a process group of its own, and the group is
// killed once `timeout_ms` has passed. That ends anything it started too.
ChildResult child_run(const std::vector<std::string>& argv, const std::vector<std::string>& env, int timeout_ms);

// Kills the group of every run still going. The game's quit and restart call it (plat_at_exit),
// since a group of its own goes on past both. Each run then returns signaled with SIGKILL. True
// if there was one.
bool child_run_kill_running();

}  // namespace dragoon
