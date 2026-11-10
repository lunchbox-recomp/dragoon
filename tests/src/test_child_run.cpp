// Running a program with a time limit (src/child_run.h), on programs every Mac has.
#include "child_run.h"
#include <gtest/gtest.h>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <fcntl.h>
#include <pthread.h>
#include <thread>
#include <unistd.h>

namespace {

using dragoon::ChildResult;
using dragoon::child_run;
using End = ChildResult::End;

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
    ASSERT_EQ(r.end, End::timed_out);
    const pid_t sleeper = (pid_t)atoi(r.out.c_str());
    ASSERT_GT(sleeper, 0);
    // launchd reaps it soon after it's killed.
    bool gone = false;
    for (int i = 0; i < 200 && !gone; i++) {
        gone = kill(sleeper, 0) != 0 && errno == ESRCH;
        if (!gone) std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    EXPECT_TRUE(gone);
}

TEST(ChildRun, StopsARunThatClosedStdoutButGoesOn) {
    const ChildResult r = child_run({"/bin/sh", "-c", "exec >&-; exec /bin/sleep 30"}, {}, 200);
    EXPECT_EQ(r.end, End::timed_out);
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
