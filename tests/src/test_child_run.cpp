// Running a program with a time limit (src/child_run.h), on programs every Mac has.
#include "child_run.h"
#include <gtest/gtest.h>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <libproc.h>
#include <pthread.h>
#include <sys/proc.h>
#include <sys/time.h>
#include <thread>
#include <unistd.h>

namespace {

using dragoon::ChildResult;
using dragoon::child_run;
using End = ChildResult::End;

// The kill on the game's way out, after which runs start again, for the tests that follow.
bool kill_running() {
    const bool killed = dragoon::child_run_kill_running();
    dragoon::child_run_reopen();
    return killed;
}

timeval now() {
    timeval t;
    gettimeofday(&t, nullptr);
    return t;
}

// A live process at `pid` that started before `by`. One that started later took a freed pid.
bool started_before(pid_t pid, timeval by) {
    proc_bsdinfo info;
    if (proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, sizeof(info)) != (int)sizeof(info)) return false;
    if (info.pbi_status == SZOMB) return false;
    return info.pbi_start_tvsec < (uint64_t)by.tv_sec ||
           (info.pbi_start_tvsec == (uint64_t)by.tv_sec && info.pbi_start_tvusec < (uint64_t)by.tv_usec);
}

// Whether the process a run started, which printed its pid before `returned`, is gone within
// two seconds. One that's left is killed, so a failure leaves no process behind.
bool gone_by(pid_t pid, timeval returned) {
    for (int i = 0; i < 200; i++) {
        if (!started_before(pid, returned)) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    if (started_before(pid, returned)) kill(pid, SIGKILL);
    return false;
}

TEST(ChildRun, KeepsStdoutAndTheExitCode) {
    const auto start = std::chrono::steady_clock::now();
    const ChildResult r = child_run({"/bin/echo", "one two"}, {}, 5000);
    // The run ends when echo does, not at its limit.
    EXPECT_LT(std::chrono::steady_clock::now() - start, std::chrono::seconds(2));
    EXPECT_EQ(r.end, End::exited);
    EXPECT_EQ(r.code, 0);
    EXPECT_EQ(r.out, "one two\n");
}

TEST(ChildRun, GetsNoneOfTheGamesOtherFiles) {
    // The game opens files without O_CLOEXEC (gcn-recomp/runtime/platform.cpp), so fd 7 here
    // stays open across an exec unless the run closes it.
    ASSERT_EQ(fcntl(7, F_GETFD), -1);
    const int fd = open("/dev/null", O_RDONLY);
    ASSERT_GE(fd, 0);
    ASSERT_EQ(dup2(fd, 7), 7);
    close(fd);
    const ChildResult r = child_run({"/bin/sh", "-c", "exec 2>/dev/null 0<&7"}, {}, 5000);
    close(7);
    EXPECT_EQ(r.end, End::exited);
    EXPECT_NE(r.code, 0);
}

TEST(ChildRun, TakesTheSignalsTheGameBlocks) {
    // The game's threads block SIGINT, SIGTERM and SIGHUP (gcn-recomp/runtime/platform.cpp).
    ChildResult r;
    std::thread blocking([&r] {
        sigset_t term;
        sigemptyset(&term);
        sigaddset(&term, SIGTERM);
        pthread_sigmask(SIG_BLOCK, &term, nullptr);
        r = child_run({"/bin/sh", "-c", "kill -TERM $$"}, {}, 5000);
    });
    blocking.join();
    EXPECT_EQ(r.end, End::signaled);
    EXPECT_EQ(r.code, SIGTERM);
}

TEST(ChildRun, TakesSigpipeThoughTheGameIgnoresIt) {
    // The recorder ignores SIGPIPE (gcn-recomp/runtime/record.cpp), and exec keeps an ignored
    // signal ignored.
    void (*was)(int) = signal(SIGPIPE, SIG_IGN);
    const ChildResult r = child_run({"/bin/sh", "-c", "kill -PIPE $$"}, {}, 5000);
    signal(SIGPIPE, was);
    EXPECT_EQ(r.end, End::signaled);
    EXPECT_EQ(r.code, SIGPIPE);
}

TEST(ChildRun, KeepsANonzeroExit) {
    const ChildResult r = child_run({"/bin/sh", "-c", "printf partial; exit 3"}, {}, 5000);
    EXPECT_EQ(r.end, End::exited);
    EXPECT_EQ(r.code, 3);
    EXPECT_EQ(r.out, "partial");
}

TEST(ChildRun, GivesOnlyTheEnvironmentAsked) {
    const ChildResult r = child_run({"/usr/bin/env"}, {"A=1", "B=two"}, 5000);
    EXPECT_EQ(r.end, End::exited);
    EXPECT_EQ(r.out, "A=1\nB=two\n");
}

TEST(ChildRun, ReadsNothingOnStdin) {
    const ChildResult r = child_run({"/bin/cat"}, {}, 5000);
    EXPECT_EQ(r.end, End::exited);
    EXPECT_EQ(r.code, 0);
    EXPECT_EQ(r.out, "");
}

TEST(ChildRun, StopsARunPastItsTime) {
    const auto start = std::chrono::steady_clock::now();
    const ChildResult r = child_run({"/bin/sh", "-c", "printf started; exec /bin/sleep 30"}, {}, 200);
    const auto took = std::chrono::steady_clock::now() - start;
    EXPECT_EQ(r.end, End::timed_out);
    EXPECT_EQ(r.out, "started");
    EXPECT_LT(took, std::chrono::seconds(5));
}

TEST(ChildRun, ATimeoutEndsWhatTheRunStarted) {
    // The shell prints the pid of a sleep it starts, then waits for it.
    const ChildResult r = child_run({"/bin/sh", "-c", "/bin/sleep 30 & echo $!; wait"}, {}, 300);
    const timeval returned = now();
    const pid_t sleeper = (pid_t)atoi(r.out.c_str());
    ASSERT_GT(sleeper, 0);
    EXPECT_TRUE(gone_by(sleeper, returned));
    EXPECT_EQ(r.end, End::timed_out);
}

TEST(ChildRun, ATimeoutEndsWhatTheRunLeftHoldingStdout) {
    // The shell exits at once, and the sleep it started keeps stdout open past the limit.
    const ChildResult r = child_run({"/bin/sh", "-c", "/bin/sleep 30 & echo $!"}, {}, 300);
    const timeval returned = now();
    const pid_t sleeper = (pid_t)atoi(r.out.c_str());
    ASSERT_GT(sleeper, 0);
    EXPECT_TRUE(gone_by(sleeper, returned));
    EXPECT_EQ(r.end, End::timed_out);
}

TEST(ChildRun, TheKillOnTheWayOutEndsARunAndWhatItStarted) {
    // The shell starts a sleep, names its pid in a file once it's up and waits for it.
    std::string dir = std::string(getenv("TMPDIR") ? getenv("TMPDIR") : "/tmp") + "/child_run.XXXXXX";
    ASSERT_NE(mkdtemp(dir.data()), nullptr);
    const std::string named = dir + "/pid";
    const auto start = std::chrono::steady_clock::now();
    ChildResult r;
    std::thread running([&r, &named] {
        r = child_run({"/bin/sh", "-c", "/bin/sleep 30 & echo $! > \"$0.new\" && /bin/mv \"$0.new\" \"$0\"; wait",
                       named},
                      {}, 30000);
    });
    pid_t sleeper = 0;
    for (int i = 0; i < 500 && sleeper == 0; i++) {
        if (FILE* f = fopen(named.c_str(), "r")) {
            if (fscanf(f, "%d", &sleeper) != 1) sleeper = 0;
            fclose(f);
        }
        if (sleeper == 0) std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    const bool killed = kill_running();
    running.join();
    const timeval returned = now();
    unlink(named.c_str());
    rmdir(dir.c_str());
    ASSERT_GT(sleeper, 0);
    EXPECT_TRUE(gone_by(sleeper, returned));
    EXPECT_TRUE(killed);
    EXPECT_EQ(r.end, End::signaled);
    EXPECT_EQ(r.code, SIGKILL);
    EXPECT_LT(std::chrono::steady_clock::now() - start, std::chrono::seconds(10));
}

TEST(ChildRun, ARunThatEndedIsntKilledOnTheWayOut) {
    child_run({"/bin/echo"}, {}, 5000);
    EXPECT_FALSE(kill_running());
    child_run({"/bin/sh", "-c", "exec /bin/sleep 30"}, {}, 100);
    EXPECT_FALSE(kill_running());
    // A run stopped while it waits, after stdout's close. 100 ms can pass under load before the
    // shell closes it, and the run then stops in the read instead.
    child_run({"/bin/sh", "-c", "exec >&-; exec /bin/sleep 30"}, {}, 1000);
    EXPECT_FALSE(kill_running());
    child_run({"/nonexistent/python3"}, {}, 5000);
    EXPECT_FALSE(kill_running());
}

TEST(ChildRun, NoRunStartsAfterTheKillOnTheWayOut) {
    dragoon::child_run_kill_running();
    const ChildResult r = child_run({"/bin/echo", "late"}, {}, 5000);
    dragoon::child_run_reopen();
    EXPECT_EQ(r.end, End::not_started);
    EXPECT_EQ(r.code, ECANCELED);
    EXPECT_EQ(r.out, "");
    // And the tests' reopen lets one start again.
    EXPECT_EQ(child_run({"/bin/echo"}, {}, 5000).end, End::exited);
}

TEST(ChildRun, StopsARunThatClosedStdoutButGoesOn) {
    const ChildResult r = child_run({"/bin/sh", "-c", "exec >&-; exec /bin/sleep 30"}, {}, 200);
    EXPECT_EQ(r.end, End::timed_out);
}

void hold_a_second(int) {
    const timespec second{1, 0};
    nanosleep(&second, nullptr);
}

TEST(ChildRun, AnEndReadPastTheLimitKeepsItsExit) {
    // A signal holds the thread running it past the limit while the child ends, so it reads the
    // close of stdout only after the deadline.
    struct sigaction hold {}, was{};
    hold.sa_handler = hold_a_second;
    sigemptyset(&hold.sa_mask);
    sigaction(SIGUSR1, &hold, &was);
    ChildResult r;
    std::thread running([&r] { r = child_run({"/bin/sleep", "0.3"}, {}, 400); });
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
    pthread_kill(running.native_handle(), SIGUSR1);
    running.join();
    sigaction(SIGUSR1, &was, nullptr);
    EXPECT_EQ(r.end, End::exited);
    EXPECT_EQ(r.code, 0);
}

TEST(ChildRun, SaysWhichSignalEndedIt) {
    const ChildResult r = child_run({"/bin/sh", "-c", "kill -TERM $$"}, {}, 5000);
    EXPECT_EQ(r.end, End::signaled);
    EXPECT_EQ(r.code, SIGTERM);
}

TEST(ChildRun, SaysWhyAProgramDidntStart) {
    const ChildResult r = child_run({"/nonexistent/python3", "x"}, {}, 5000);
    EXPECT_EQ(r.end, End::not_started);
    EXPECT_EQ(r.code, ENOENT);
}

}  // namespace
