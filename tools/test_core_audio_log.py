import unittest
from datetime import datetime

import core_audio_log

# Captured from `/usr/bin/log show --style compact` on this Mac on 2026-10-22: the header,
# Core Audio lines with no overload in them (one from a process whose name has spaces and
# parentheses) and the log command's own line, whose arguments hold the word.
CAPTURED = """\
Timestamp               Ty Process[PID:TID]
2026-10-22 15:31:56.439 Df AudioComponentRegistrar[34384:ea28544] [com.apple.coreaudio:AudioCompReg] AudioComponentRegistrar.mm:194   (main 1  pid 71918)
2026-10-22 14:35:14.094 Df coreaudiod[434:108692d1] [com.apple.coreaudio:AMCP]   HALS_IOContext_Legacy_Impl.cpp:4808  AllowNegotiateAdaptInSetComposition: useCaseID = 0, isServerBuild = true, isIsolatedUseCase = false, isSharedDsp = false, istvos = false, adaptNow = false
2026-10-22 15:32:14.170 E  coreaudiod[434:1089ba35] [com.apple.coreaudio:AMCP]                  HALS_PlugIn.cpp:847   HALS_PlugIn::HostInterface_PropertiesChanged: the object is not valid
2026-10-22 15:39:18.769 Df Google Chrome Helper (Aperitif)[26999:108cbe64] [com.apple.coreaudio:audiocomp] AudioComponentPluginMgr.mm:907   First wildcard component search: acdc/lpcm/0
2026-10-22 15:55:32.884 Df log[90664:108f19a3] [com.apple.log:] log run noninteractively, parent: 90663 (zsh), args: '/usr/bin/log' 'show' '--last' '6h' '--predicate' 'eventMessage CONTAINS[c] "overload"' '--style' 'compact'
"""

# No overload was logged on this Mac in the days `log show` keeps, so these are written in the
# captured lines' layout with the message Core Audio logs when it skips an IO cycle.
OVERLOAD = "HALC_ProxyIOContext::IOWorkLoop: skipping cycle due to overload"
BUILT = f"""\
2026-10-22 16:01:02.003 E  coreaudiod[434:108cbe44] [com.apple.coreaudio:AMCP] {OVERLOAD}
2026-10-22 16:01:02.014 E  dragoon[5150:20a1] [com.apple.coreaudio:] HALC_ProxyIOContext.cpp:1620  {OVERLOAD}
2026-10-22 16:01:09.500 E  dragoon[5150:20a1] [com.apple.coreaudio:] HALC_ProxyIOContext.cpp:1620  {OVERLOAD.upper()}
2026-10-22 16:01:09.900 E  Google Chrome Helper (Aperitif)[26999:108cbe64] [com.apple.coreaudio:AMCP] {OVERLOAD}
2026-10-22 16:01:10.000 E  dragoon[5150:20a1] [com.apple.audio.toolbox:] {OVERLOAD}
"""


class OverloadsTest(unittest.TestCase):
    def test_the_captured_lines_have_none(self):
        self.assertEqual(core_audio_log.overloads(CAPTURED), {})

    def test_counts_core_audio_overloads_by_process(self):
        self.assertEqual(core_audio_log.overloads(CAPTURED + BUILT),
                         {"coreaudiod": 1, "dragoon": 2, "Google Chrome Helper (Aperitif)": 1})

    def test_the_captured_layout_parses(self):
        fields = [core_audio_log.LINE.match(line) for line in CAPTURED.splitlines()[1:]]
        self.assertEqual([(m[3], m[5]) for m in fields],
                         [("AudioComponentRegistrar", "com.apple.coreaudio"), ("coreaudiod", "com.apple.coreaudio"),
                          ("coreaudiod", "com.apple.coreaudio"), ("Google Chrome Helper (Aperitif)", "com.apple.coreaudio"),
                          ("log", "com.apple.log")])

    def test_another_subsystem_saying_overload_isnt_counted(self):
        self.assertEqual(core_audio_log.overloads(BUILT.splitlines()[-1]), {})


class CommandTest(unittest.TestCase):
    def test_reads_the_window_in_compact_style_with_the_predicate(self):
        cmd = core_audio_log.command(datetime(2026, 10, 22, 16, 0, 0), datetime(2026, 10, 22, 16, 30, 5))
        self.assertEqual(cmd, ["/usr/bin/log", "show", "--style", "compact", "--start", "2026-10-22 16:00:00",
                               "--end", "2026-10-22 16:30:05", "--predicate",
                               'subsystem == "com.apple.coreaudio" AND eventMessage CONTAINS[c] "overload"'])


if __name__ == "__main__":
    unittest.main()
