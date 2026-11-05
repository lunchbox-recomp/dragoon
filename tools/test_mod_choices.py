import json
import contextlib
import io
import os
import time
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mod_choices


TOOL = Path(__file__).with_name('mod_choices.py')


class ModChoicesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not mod_choices.RIIVOLUTION.is_file():
            raise unittest.SkipTest("gcn-recomp isn't checked out: git submodule update --init")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='mod choices test ')
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name, 'player data')
        self.root = self.data / 'mods'
        (self.root / 'riivolution').mkdir(parents=True)
        self.image = Path(tmp.name, 'made up.iso')
        image = bytearray(0x3000)
        image[:6] = b'FAKE42'
        # One file in the FST, using the same header and entry format as test_fst.py.
        fst = struct.pack('>III', 0x01000000, 0, 2)
        fst += struct.pack('>III', 0, 0x2800, 4) + b'tiny\0'
        struct.pack_into('>4I', image, 0x420, 0x1000, 0x2000, len(fst), len(fst) + 0x40)
        image[0x2000:0x2000 + len(fst)] = fst
        image[0x2800:0x2804] = b'fake'
        self.image.write_bytes(image)

    def package(self, name='a.xml', body='<memory offset="0x1200" value="abcd"/>', default=1):
        xml = ('<wiidisc version="1"><id game="FAKE"/><options><section name="Made up">'
               '<option name="Option" id="opt" default="%s"><choice name="First"><patch id="p"/>'
               '</choice><choice name="Second"/></option></section></options><patch id="p">%s'
               '</patch></wiidisc>') % (default, body)
        (self.root / 'riivolution' / name).write_text(xml)

    def run_tool(self, *args, code=0):
        done = subprocess.run([sys.executable, str(TOOL), args[0], '--data', str(self.data),
                               *args[1:]], capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, code, done.stderr + done.stdout)
        self.assertEqual(len(done.stdout.splitlines()), 1, done.stdout)
        return json.loads(done.stdout)

    def test_list_defaults_and_saved_choices(self):
        self.package('a:b.xml')
        self.package('z.xml', default=0)
        packages = self.run_tool('list')['packages']
        self.assertEqual([p['options'][0]['choice'] for p in packages], [1, 0])
        self.assertEqual(self.run_tool('set', 'a:b.xml', 'opt', 'off')['choice'], 0)
        self.assertEqual(self.run_tool('list')['packages'][0]['options'][0]['choice'], 0)
        self.assertEqual((self.data / 'mods.txt').read_text(), 'a:b.xml:opt=0\n')

    def test_set_keeps_order_and_drops_gone_lines(self):
        self.package()
        self.package('b.xml')
        (self.data / 'mods.txt').write_text('b.xml:opt=0\ngone.xml:opt=1\na.xml:opt=0\n')
        self.run_tool('set', 'a.xml', 'opt', '1')
        self.assertEqual((self.data / 'mods.txt').read_text(), 'b.xml:opt=0\na.xml:opt=1\n')

    def test_saved_lines_filter_duplicates_and_invalid_choices(self):
        self.package()
        (self.data / 'mods.txt').write_text(
            'a.xml:opt=0\na.xml:opt=2\na.xml:gone=1\na.xml:opt=3\n')
        self.assertEqual(self.run_tool('list')['packages'][0]['options'][0]['choice'], 0)
        self.run_tool('set', 'a.xml', 'opt', '2')
        self.assertEqual((self.data / 'mods.txt').read_text(), 'a.xml:opt=2\n')

    def test_past_last_choice_alone_is_dropped(self):
        self.package()
        self.package('b.xml')
        (self.data / 'mods.txt').write_text('a.xml:opt=3\n')
        self.assertEqual(self.run_tool('list')['packages'][0]['options'][0]['choice'], 1)
        self.run_tool('set', 'b.xml', 'opt', 'off')
        self.assertEqual((self.data / 'mods.txt').read_text(), 'b.xml:opt=0\n')

    def test_last_equals_sign_and_cr_in_option_id(self):
        self.package()
        xml = (self.root / 'riivolution' / 'a.xml').read_text().replace('id="opt"',
                                                                      'id="x=y&#13;z"')
        (self.root / 'riivolution' / 'a.xml').write_text(xml)
        self.run_tool('set', 'a.xml', 'x=y\rz', 'off')
        self.assertEqual(self.run_tool('list')['packages'][0]['options'][0]['choice'], 0)
        self.assertEqual((self.data / 'mods.txt').read_bytes(), b'a.xml:x=y\rz=0\n')

    def test_line_break_in_option_id_is_refused(self):
        self.package()
        xml = (self.root / 'riivolution' / 'a.xml').read_text().replace('id="opt"',
                                                                      'id="x&#10;z"')
        (self.root / 'riivolution' / 'a.xml').write_text(xml)
        error = self.run_tool('set', 'a.xml', 'x\nz', '1', code=1)['error']
        self.assertIn('line break', error)
        self.assertFalse((self.data / 'mods.txt').exists())

    def test_errored_package_line_survives_set(self):
        self.package()
        (self.root / 'riivolution' / 'bad.xml').write_text('<!DOCTYPE wiidisc []><wiidisc/>')
        (self.data / 'mods.txt').write_text('bad.xml:old=1\na.xml:opt=0\n')
        self.run_tool('set', 'a.xml', 'opt', '2')
        self.assertEqual((self.data / 'mods.txt').read_text(), 'bad.xml:old=1\na.xml:opt=2\n')

    def test_set_preserves_position_and_accepts_last_choice(self):
        self.package()
        self.package('b.xml')
        (self.data / 'mods.txt').write_text('a.xml:opt=0\nb.xml:opt=0\n')
        self.run_tool('set', 'a.xml', 'opt', '2')
        self.assertEqual((self.data / 'mods.txt').read_text(), 'a.xml:opt=2\nb.xml:opt=0\n')

    def test_saved_lines_split_on_newlines_only(self):
        self.package()
        (self.data / 'mods.txt').write_bytes(b'a.xml:opt=0\r\n')
        self.assertEqual(self.run_tool('list')['packages'][0]['options'][0]['choice'], 1)
        self.run_tool('set', 'a.xml', 'opt', 'off')
        self.assertEqual((self.data / 'mods.txt').read_bytes(), b'a.xml:opt=0\n')

    def test_set_refuses_unknown_names_and_choice(self):
        self.package()
        for xml, option, choice in [('gone.xml', 'opt', '1'), ('a.xml', 'gone', '1'),
                                    ('a.xml', 'opt', '3')]:
            with self.subTest(xml=xml, option=option, choice=choice):
                self.assertIn('error', self.run_tool('set', xml, option, choice, code=1))
        self.assertFalse((self.data / 'mods.txt').exists())

    def test_apply_writes_both_paths_and_elapsed_time(self):
        (self.root / 'payload').mkdir()
        (self.root / 'payload' / 'small').write_bytes(b'new')
        self.package(body='<file disc="/tiny" external="/payload/small"/>'
                          '<memory offset="0x1200" value="abcd"/>')
        result = self.run_tool('apply', '--disc', str(self.image))
        self.assertEqual(result['overlay'], 'mods/.out/disc-overlay.txt')
        self.assertEqual(result['ram_patches'], 'mods/.out/ram-patches.txt')
        self.assertEqual(result['failed'], [])
        self.assertIsInstance(result['ms'], int)

    def test_apply_failing_package_leaves_good_one_on(self):
        self.package('good.xml')
        self.package('bad.xml', '<savegame external="x"/>')
        result = self.run_tool('apply', '--disc', str(self.image))
        self.assertIsNone(result['overlay'])
        self.assertEqual(result['ram_patches'], 'mods/.out/ram-patches.txt')
        self.assertEqual([x['xml'] for x in result['failed']], ['bad.xml'])
        self.assertIn('savegame', result['failed'][0]['error'])

    def test_failed_saved_choice_is_off_on_retry(self):
        self.package('good.xml')
        self.package('bad.xml', '<savegame external="x"/>')
        self.run_tool('set', 'bad.xml', 'opt', '1')
        result = self.run_tool('apply', '--disc', str(self.image))
        self.assertEqual([x['xml'] for x in result['failed']], ['bad.xml'])
        self.assertEqual(result['ram_patches'], 'mods/.out/ram-patches.txt')

    def test_dash_named_xml_and_disc(self):
        self.package('-a.xml')
        self.run_tool('set', '--', '-a.xml', 'opt', '1')
        image = self.data / '-made.iso'
        image.write_bytes(self.image.read_bytes())
        result = self.run_tool('apply', '--disc', str(image))
        self.assertEqual(result['ram_patches'], 'mods/.out/ram-patches.txt')
        done = subprocess.run([sys.executable, str(TOOL), 'apply', '--data',
                               str(self.data), '--disc=-made.iso'], cwd=self.data,
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(json.loads(done.stdout)['ram_patches'],
                         'mods/.out/ram-patches.txt')

    def test_conflict_leaves_both_off(self):
        self.package('a.xml')
        self.package('b.xml')
        result = self.run_tool('apply', '--disc', str(self.image))
        self.assertEqual([x['xml'] for x in result['failed']], ['a.xml', 'b.xml'])
        self.assertIsNone(result['ram_patches'])
        self.assertIsNone(result['overlay'])

    def test_list_error_is_reported_by_apply(self):
        self.package('good.xml')
        (self.root / 'riivolution' / 'bad.xml').write_text('<!DOCTYPE wiidisc []><wiidisc/>')
        self.assertIn('error', self.run_tool('list')['packages'][0])
        result = self.run_tool('apply', '--disc', str(self.image))
        self.assertEqual([x['xml'] for x in result['failed']], ['bad.xml'])
        self.assertEqual(result['ram_patches'], 'mods/.out/ram-patches.txt')

    def test_nothing_on_is_null(self):
        self.package(default=0)
        # The engine scans only the top of mods/riivolution and never enters .out.
        result = self.run_tool('apply', '--disc', str(self.image))
        self.assertIsNone(result['overlay'])
        self.assertIsNone(result['ram_patches'])

    def test_missing_mods_and_missing_disc(self):
        import shutil
        shutil.rmtree(self.root)
        self.assertEqual(self.run_tool('list'), {'packages': []})
        repo = self.data / 'empty repo'
        repo.mkdir()
        output = io.StringIO()
        with mock.patch.object(mod_choices, 'REPO', repo), contextlib.redirect_stdout(output):
            self.assertEqual(mod_choices.main(['apply', '--data', str(self.data)]), 2)
        self.assertIn('Pass --disc', json.loads(output.getvalue())['error'])
        self.assertEqual(self.run_tool('apply', '--disc', str(self.image))['failed'], [])

    def test_apply_disc_defaults_to_cache_path(self):
        self.package()
        repo = self.data / 'fake repo'
        (repo / 'build').mkdir(parents=True)
        (repo / 'build' / 'CMakeCache.txt').write_text('GAME_ISO:FILEPATH=%s\n' % self.image)
        output = io.StringIO()
        with mock.patch.object(mod_choices, 'REPO', repo), contextlib.redirect_stdout(output):
            self.assertEqual(mod_choices.main(['apply', '--data', str(self.data)]), 0)
        self.assertEqual(json.loads(output.getvalue())['ram_patches'],
                         'mods/.out/ram-patches.txt')

    def test_cache_path_keeps_equals_sign(self):
        self.package()
        image = self.data / 'a=b.iso'
        image.write_bytes(self.image.read_bytes())
        repo = self.data / 'fake repo'
        (repo / 'build').mkdir(parents=True)
        (repo / 'build' / 'CMakeCache.txt').write_text('GAME_ISO:FILEPATH=%s\n' % image)
        output = io.StringIO()
        with mock.patch.object(mod_choices, 'REPO', repo), contextlib.redirect_stdout(output):
            self.assertEqual(mod_choices.main(['apply', '--data', str(self.data)]), 0)
        self.assertEqual(json.loads(output.getvalue())['ram_patches'],
                         'mods/.out/ram-patches.txt')

    def test_default_data_is_current_folder(self):
        self.package()
        output = io.StringIO()
        old = os.getcwd()
        with contextlib.redirect_stdout(output):
            os.chdir(self.data)
            try:
                self.assertEqual(mod_choices.main(['list']), 0)
            finally:
                os.chdir(old)
        self.assertEqual(json.loads(output.getvalue())['packages'][0]['xml'], 'a.xml')

    def test_mods_txt_folder_and_fifo_are_refused(self):
        self.package()
        target = self.data / 'mods.txt'
        target.mkdir()
        self.assertIn('regular file', self.run_tool('list', code=1)['error'])
        target.rmdir()
        os.mkfifo(target)
        start = time.monotonic()
        self.assertIn('regular file', self.run_tool('list', code=1)['error'])
        self.assertLess(time.monotonic() - start, 3)

    def test_non_utf8_mods_txt_has_actionable_error(self):
        self.package()
        (self.data / 'mods.txt').write_bytes(b'\xff')
        self.assertIn('UTF-8', self.run_tool('list', code=2)['error'])
        self.assertIn('Delete', self.run_tool('list', code=2)['error'])

    def test_non_utf8_cache_names_cache(self):
        self.package()
        repo = self.data / 'fake repo'
        (repo / 'build').mkdir(parents=True)
        (repo / 'build' / 'CMakeCache.txt').write_bytes(b'\xff')
        output = io.StringIO()
        with mock.patch.object(mod_choices, 'REPO', repo), contextlib.redirect_stdout(output):
            self.assertEqual(mod_choices.main(['apply', '--data', str(self.data)]), 2)
        error = json.loads(output.getvalue())['error']
        self.assertIn('CMakeCache.txt', error)
        self.assertIn('--disc', error)

    def test_mods_txt_link_is_not_followed(self):
        self.package()
        target = self.data / 'target.txt'
        target.write_text('unchanged')
        os.symlink(target, self.data / 'mods.txt')
        self.assertIn('error', self.run_tool('set', 'a.xml', 'opt', 'off', code=1))
        self.assertEqual(target.read_text(), 'unchanged')

    def test_write_replaces_link_without_following_it(self):
        target = self.data / 'other.txt'
        target.write_text('unchanged')
        os.symlink(target, self.data / 'mods.txt')
        mod_choices.write_choices(self.data, [('a.xml', 'opt', 0)])
        self.assertEqual(target.read_text(), 'unchanged')
        self.assertEqual((self.data / 'mods.txt').read_text(), 'a.xml:opt=0\n')


class FakeEngineTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='fake mod engine ')
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name, 'data')
        (self.data / 'mods').mkdir(parents=True)
        self.image = Path(tmp.name, 'image.iso')
        self.image.write_bytes(b'made up')
        self.engine = Path(tmp.name, 'fake engine.py')

    def run_fake(self, script, *args, code):
        self.engine.write_text('import json, sys\n' + script)
        output = io.StringIO()
        with mock.patch.object(mod_choices, 'RIIVOLUTION', self.engine), \
                contextlib.redirect_stdout(output):
            actual = mod_choices.main(list(args))
        self.assertEqual(actual, code, output.getvalue())
        return json.loads(output.getvalue())

    def test_list_failure_is_not_ignored(self):
        result = self.run_fake('print(json.dumps({"error":"bad package folder"})); sys.exit(1)\n',
                               'list', '--data', str(self.data), code=2)
        self.assertIn('bad package folder', result['error'])
        self.assertIn('Check', result['error'])

    def test_missing_engine_names_checkout_step(self):
        missing = self.data / 'missing riivolution.py'
        output = io.StringIO()
        with mock.patch.object(mod_choices, 'RIIVOLUTION', missing), \
                contextlib.redirect_stdout(output):
            self.assertEqual(mod_choices.main(['list', '--data', str(self.data)]), 2)
        error = json.loads(output.getvalue())['error']
        self.assertIn('gcn-recomp', error)
        self.assertIn('git submodule update --init', error)

    def test_package_error_has_punctuation_and_action(self):
        listing = ('{"packages":[{"xml":"bad.xml","error":'
                   '"savegame does not redirect saves","options":[]}]}')
        script = 'print(%r)\n' % listing
        result = self.run_fake(script, 'list', '--data', str(self.data), code=0)
        self.assertIn("saves. ", result['packages'][0]['error'])
        self.assertIn('author', result['packages'][0]['error'])

    def test_file_error_names_path_and_reason(self):
        output = io.StringIO()
        path = str(self.data / 'mods.txt')
        found = [{'xml': 'a.xml', 'options': [{'id': 'opt', 'choices': ['one']}]}]
        with mock.patch.object(mod_choices, 'packages', return_value=found), \
                mock.patch.object(mod_choices, 'write_choices',
                               side_effect=PermissionError(13, 'Permission denied', path)), \
                contextlib.redirect_stdout(output):
            self.assertEqual(mod_choices.main(['set', '--data', str(self.data),
                                               'a.xml', 'opt', 'off']), 2)
        error = json.loads(output.getvalue())['error']
        self.assertIn(path, error)
        self.assertIn('Permission denied', error)
        self.assertIn('writable', error)

    def test_engine_bad_exit_and_no_json(self):
        for script, expected in [
            ('sys.exit(2)\n', 'rejected'),
            ('sys.exit(3)\n', 'rejected'),
            ('print("not JSON")\n', 'no JSON'),
        ]:
            with self.subTest(script=script):
                result = self.run_fake(script, 'list', '--data', str(self.data), code=2)
                self.assertIn(expected, result['error'])

    def test_engine_timeout(self):
        with mock.patch.object(mod_choices.subprocess, 'run',
                               side_effect=subprocess.TimeoutExpired('fake', 10)):
            result = self.run_fake('', 'list', '--data', str(self.data), code=2)
        self.assertIn('timed out', result['error'])

    def test_apply_missing_error_and_unknown_culprit(self):
        listing = '{"packages":[{"xml":"a.xml","options":[{"id":"opt","default":1,"choices":["one"]}]}]}'
        for failure in ['{"packages":["a.xml"]}',
                        '{"error":"unknown package","packages":["gone.xml"]}']:
            script = ('if sys.argv[1] == "list": print(%r)\n'
                      'else: print(%r); sys.exit(1)\n') % (listing, failure)
            result = self.run_fake(script, 'apply', '--data', str(self.data),
                                   '--disc', str(self.image), code=1)
            self.assertIn('error', result)

    def test_apply_no_mods_never_calls_engine(self):
        (self.data / 'mods').rmdir()
        result = self.run_fake('raise RuntimeError("engine ran")\n', 'apply', '--data',
                               str(self.data), '--disc', str(self.image), code=0)
        self.assertIsNone(result['overlay'])

    def test_apply_already_failed_culprit_stops(self):
        listing = {'packages': [{'xml': 'a.xml', 'options': [
            {'id': 'opt', 'default': 1, 'choices': ['one']}]}]}
        failure = {'error': 'still fails', 'packages': ['a.xml']}
        output = io.StringIO()
        with mock.patch.object(mod_choices, 'call_engine', side_effect=[
                (0, listing), (1, failure), (1, failure), AssertionError('looped')]) as calls, \
                contextlib.redirect_stdout(output):
            self.assertEqual(mod_choices.main(['apply', '--data', str(self.data),
                                               '--disc', str(self.image)]), 1)
        self.assertEqual(calls.call_count, 3)
        self.assertIn('still fails', json.loads(output.getvalue())['error'])

    def test_apply_failure_without_package_stops(self):
        script = ('if sys.argv[1] == "list": print("{\\"packages\\":[]}")\n'
                  'else: print(json.dumps({"error":"no package named","packages":[]})); '
                  'sys.exit(1)\n')
        result = self.run_fake(script, 'apply', '--data', str(self.data),
                               '--disc', str(self.image), code=1)
        self.assertIn('no package named', result['error'])
        self.assertIn('Check', result['error'])

    def test_apply_time_includes_list(self):
        script = ('import time\n'
                  'if sys.argv[1] == "list":\n'
                  '    time.sleep(0.15)\n'
                  '    print("{\\"packages\\":[]}")\n'
                  'else: print("{}")\n')
        result = self.run_fake(script, 'apply', '--data', str(self.data),
                               '--disc', str(self.image), code=0)
        self.assertGreaterEqual(result['ms'], 140)


if __name__ == '__main__':
    unittest.main()
