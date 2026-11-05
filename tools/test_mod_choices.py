import json
import contextlib
import io
import os
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

    def test_out_is_never_a_package_and_nothing_on_is_null(self):
        self.package(default=0)
        (self.root / '.out' / 'riivolution').mkdir(parents=True)
        (self.root / '.out' / 'riivolution' / 'hidden.xml').write_text('<wiidisc version="1"/>')
        self.assertEqual([p['xml'] for p in self.run_tool('list')['packages']], ['a.xml'])
        result = self.run_tool('apply', '--disc', str(self.image))
        self.assertIsNone(result['overlay'])
        self.assertIsNone(result['ram_patches'])

    def test_missing_mods_and_missing_disc(self):
        import shutil
        shutil.rmtree(self.root)
        self.assertEqual(self.run_tool('list'), {'packages': []})
        self.assertIn('Pass --disc', self.run_tool('apply', code=2)['error'])

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

    def test_mods_txt_link_is_not_followed(self):
        self.package()
        target = self.data / 'target.txt'
        target.write_text('unchanged')
        os.symlink(target, self.data / 'mods.txt')
        self.assertIn('error', self.run_tool('set', 'a.xml', 'opt', 'off', code=1))
        self.assertEqual(target.read_text(), 'unchanged')


if __name__ == '__main__':
    unittest.main()
