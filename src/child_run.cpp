// See child_run.h. posix_spawn rather than fork, since the game has many threads.
#include "child_run.h"
#include <cerrno>
#include <chrono>
#include <csignal>
#include <fcntl.h>
#include <mutex>
#include <poll.h>
#include <spawn.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>

namespace dragoon {

namespace {

using Clock = std::chrono::steady_clock;

// The groups of the runs still going, by their child's pid. A run's group leaves the list under
// the lock before or as its child is reaped, which frees the group's id, so a kill from
// child_run_kill_running never reaches another process's group.
std::mutex g_running_lock;
std::vector<pid_t> g_running;

void kill_group(pid_t pid) {
    std::lock_guard<std::mutex> lock(g_running_lock);
    kill(-pid, SIGKILL);
    std::erase(g_running, pid);
}

// Whether the child has ended, reaping it if so.
bool ended(pid_t pid, int& status) {
    std::lock_guard<std::mutex> lock(g_running_lock);
    if (waitpid(pid, &status, WNOHANG) != pid) return false;
    std::erase(g_running, pid);
    return true;
}

int ms_left(Clock::time_point deadline) {
    const auto left = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count();
    return left > 0 ? (int)left : 0;
}

std::vector<char*> pointers(const std::vector<std::string>& strings) {
    std::vector<char*> out;
    for (const std::string& s : strings) out.push_back(const_cast<char*>(s.c_str()));
    out.push_back(nullptr);
    return out;
}

// What the child writes until it closes stdout or the deadline passes.
void read_until(int fd, Clock::time_point deadline, std::string& out) {
    for (;;) {
        pollfd p{fd, POLLIN, 0};
        const int ready = poll(&p, 1, ms_left(deadline));
        if (ready < 0 && errno == EINTR) continue;
        if (ready <= 0) return;
        char buf[4096];
        const ssize_t got = read(fd, buf, sizeof(buf));
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) return;
        out.append(buf, (size_t)got);
    }
}

bool reap(pid_t pid, int& status) {
    pid_t got;
    while ((got = waitpid(pid, &status, 0)) < 0 && errno == EINTR) {
    }
    return got == pid;
}

}  // namespace

ChildResult child_run(const std::vector<std::string>& argv, const std::vector<std::string>& env, int timeout_ms) {
    ChildResult r;
    const Clock::time_point deadline = Clock::now() + std::chrono::milliseconds(timeout_ms);
    int out[2];
    if (pipe(out) != 0) {
        r.code = errno;
        return r;
    }
    fcntl(out[0], F_SETFD, FD_CLOEXEC);
    fcntl(out[1], F_SETFD, FD_CLOEXEC);
    posix_spawn_file_actions_t files;
    posix_spawn_file_actions_init(&files);
    posix_spawn_file_actions_addopen(&files, 0, "/dev/null", O_RDONLY, 0);
    posix_spawn_file_actions_adddup2(&files, out[1], 1);
    posix_spawn_file_actions_addinherit_np(&files, 2);
    posix_spawnattr_t attr;
    posix_spawnattr_init(&attr);
    // Its own group, for the kill below, and no descriptor of the game's but these three. The
    // game's threads block SIGINT, SIGTERM and SIGHUP and its recorder ignores SIGPIPE, and the
    // child would keep both, so it starts with no signal blocked and SIGPIPE's default action.
    sigset_t none, pipe_signal;
    sigemptyset(&none);
    sigemptyset(&pipe_signal);
    sigaddset(&pipe_signal, SIGPIPE);
    posix_spawnattr_setsigmask(&attr, &none);
    posix_spawnattr_setsigdefault(&attr, &pipe_signal);
    posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSIGMASK |
                                        POSIX_SPAWN_SETSIGDEF);
    posix_spawnattr_setpgroup(&attr, 0);
    std::vector<char*> args = pointers(argv), vars = pointers(env);
    pid_t pid;
    int failed;
    {
        // A kill of every run can't come between the spawn and the list.
        std::lock_guard<std::mutex> lock(g_running_lock);
        failed = posix_spawn(&pid, argv[0].c_str(), &files, &attr, args.data(), vars.data());
        if (!failed) g_running.push_back(pid);
    }
    posix_spawnattr_destroy(&attr);
    posix_spawn_file_actions_destroy(&files);
    close(out[1]);
    if (failed) {
        close(out[0]);
        r.code = failed;
        return r;
    }
    read_until(out[0], deadline, r.out);
    close(out[0]);
    int status = 0;
    if (ms_left(deadline) == 0) {
        // Something in the group held stdout to the deadline, though the child itself may have
        // ended. The kill comes before the reap, which frees the group's id for reuse.
        kill_group(pid);
        reap(pid, status);
        r.end = ChildResult::End::timed_out;
        return r;
    }
    while (!ended(pid, status)) {
        if (ms_left(deadline) == 0) {
            kill_group(pid);
            // A child that ended by itself just before the kill keeps its own end.
            if (reap(pid, status) && !(WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL)) break;
            r.end = ChildResult::End::timed_out;
            return r;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    if (WIFSIGNALED(status)) {
        r.end = ChildResult::End::signaled;
        r.code = WTERMSIG(status);
    } else {
        r.end = ChildResult::End::exited;
        r.code = WEXITSTATUS(status);
    }
    return r;
}

bool child_run_kill_running() {
    std::lock_guard<std::mutex> lock(g_running_lock);
    for (pid_t pid : g_running) kill(-pid, SIGKILL);
    return !g_running.empty();
}

}  // namespace dragoon
