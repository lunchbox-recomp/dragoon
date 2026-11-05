#!/usr/bin/env python3
"""Keep Riivolution choices beside settings.txt and apply them to a disc image."""
import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
RIIVOLUTION = REPO / 'gcn-recomp' / 'recomp' / 'riivolution.py'


class ArgumentError(Exception):
    pass


class ChoiceError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentError(message)


def call_engine(args):
    try:
        done = subprocess.run([sys.executable, str(RIIVOLUTION), *args],
                              capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired as exc:
        raise ArgumentError('Riivolution timed out. Check the mods folder and try again.') from exc
    except OSError as exc:
        raise ArgumentError('Riivolution could not start. Check the engine script and try again.') from exc
    if done.returncode not in (0, 1):
        raise ArgumentError('Riivolution rejected the arguments or crashed. Check the disc and mods folder.')
    try:
        result = json.loads(done.stdout.strip())
    except (ValueError, TypeError) as exc:
        raise ArgumentError('Riivolution returned no JSON. Check the mods folder and try again.') from exc
    return done.returncode, result


def packages(root):
    if not root.exists():
        return []
    code, result = call_engine(['list', str(root)])
    if code:
        detail = result.get('error', 'Riivolution could not list the packages.')
        raise ArgumentError('%s Check the mods folder and try again.' % detail)
    return result['packages']


def split_choice(line, found):
    """Match parse_picks in riivolution.py: last =, then longest XML prefix."""
    parts = re.fullmatch(r'(.*)=([0-9]+)', line)
    if parts is None:
        return None
    head, value = parts.group(1), int(parts.group(2))
    xml = max((x for x in found if head.startswith(x + ':')), key=len, default=None)
    if xml is None:
        return None
    return xml, head[len(xml) + 1:], value


def read_choices(data, found):
    path = data / 'mods.txt'
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NONBLOCK |
                     getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        return []
    except OSError as exc:
        if path.is_symlink():
            raise ChoiceError('mods.txt is a link. Remove the link or move the file.') from exc
        raise
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ChoiceError('mods.txt is not a regular file. Replace it with a regular UTF-8 file.')
    with os.fdopen(fd, 'r', encoding='utf-8', newline='') as file:
        lines = file.read().split('\n')
    valid = {(p['xml'], o['id']): len(o['choices']) for p in found
             for o in p.get('options', [])}
    errored = {p['xml'] for p in found if 'error' in p}
    kept = []
    seen = set()
    for line in lines:
        parsed = split_choice(line, [p['xml'] for p in found])
        if parsed and ((parsed[:2] in valid and parsed[2] <= valid[parsed[:2]])
                       or parsed[0] in errored):
            if parsed[:2] not in seen:
                kept.append(parsed)
                seen.add(parsed[:2])
    return kept


def listing(data, found):
    chosen = {(xml, option): number for xml, option, number in read_choices(data, found)}
    for package in found:
        for option in package.get('options', []):
            option['choice'] = chosen.get((package['xml'], option['id']), option['default'])
    return {'packages': found}


def write_choices(data, choices):
    target = data / 'mods.txt'
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(data),
                                         prefix='.mods-', delete=False) as file:
            temp = file.name
            for xml, option, number in choices:
                file.write('%s:%s=%d\n' % (xml, option, number))
        try:
            mode = target.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise ChoiceError('mods.txt is not a regular file. Replace it with a regular UTF-8 file.')
        except FileNotFoundError:
            pass
        os.replace(temp, target)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def disc_from_cache():
    cache = REPO / 'build' / 'CMakeCache.txt'
    try:
        for line in cache.read_text(encoding='utf-8').split('\n'):
            if line.startswith('GAME_ISO:') and '=' in line:
                return line.split('=', 1)[1]
    except OSError:
        pass
    raise ArgumentError('GAME_ISO is missing from build/CMakeCache.txt. Pass --disc IMAGE.')


def apply(data, found, disc, started):
    root = data / 'mods'
    output = root / '.out'
    failed = {p['xml']: p['error'] for p in found if 'error' in p}
    chosen = read_choices(data, found)
    # Every errored package has no usable options. The engine skips it by default.
    if not root.exists():
        return {'overlay': None, 'ram_patches': None, 'failed': [],
                'ms': round((time.monotonic() - started) * 1000)}
    while True:
        specs = ['%s:%s=%d' % (xml, option, 0 if xml in failed else number)
                 for xml, option, number in chosen]
        # Defaults also need an explicit off for a package refused in an earlier run.
        for package in found:
            if package['xml'] in failed:
                specs.extend('%s:%s=0' % (package['xml'], option['id'])
                             for option in package.get('options', [])
                             if (package['xml'], option['id']) not in
                             {(xml, key) for xml, key, _ in chosen})
        args = ['apply', str(Path(disc).absolute()), str(root), str(output)]
        for spec in specs:
            args.append('--choice=' + spec)
        code, result = call_engine(args)
        if code == 0:
            break
        culprits = result.get('packages', [])
        if not culprits or all(xml in failed for xml in culprits):
            detail = result.get('error', 'Riivolution could not apply the packages.')
            raise ChoiceError('%s Check the disc and mods folder, then try again.' % detail)
        for xml in culprits:
            detail = result.get('error', 'Riivolution refused a package.')
            failed[xml] = '%s Check the package and try again.' % detail
    return {'overlay': 'mods/.out/disc-overlay.txt' if (output / 'disc-overlay.txt').is_file() else None,
            'ram_patches': 'mods/.out/ram-patches.txt' if (output / 'ram-patches.txt').is_file() else None,
            'failed': [{'xml': xml, 'error': failed[xml]} for xml in sorted(failed)],
            'ms': round((time.monotonic() - started) * 1000)}


def main(argv=None):
    started = time.monotonic()
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    for name in ('list', 'set', 'apply'):
        command = commands.add_parser(name)
        command.add_argument('--data', default='.', metavar='DIR')
        if name == 'set':
            command.add_argument('xml')
            command.add_argument('option')
            command.add_argument('choice')
        if name == 'apply':
            command.add_argument('--disc', metavar='IMAGE')
    try:
        args = parser.parse_args(argv)
        data = Path(args.data).absolute()
        if not data.is_dir() or not os.access(data, os.R_OK | os.X_OK):
            raise ArgumentError('The data folder cannot be read. Pass --data with a readable folder.')
        root = data / 'mods'
        found = packages(root)
        if args.command == 'list':
            result = listing(data, found)
        elif args.command == 'set':
            if args.choice == 'off':
                number = 0
            elif re.fullmatch(r'[0-9]+', args.choice):
                number = int(args.choice)
            else:
                raise ChoiceError('The choice is not a number or off. Pass a choice number or off.')
            match = next((o for p in found if p['xml'] == args.xml
                          for o in p.get('options', []) if o['id'] == args.option), None)
            if match is None:
                raise ChoiceError('The package or option is not listed. Run list and choose one shown there.')
            if '\n' in args.xml or '\n' in args.option:
                raise ChoiceError('The package or option ID holds a line break, so it cannot be saved in mods.txt. Ask the package author to fix it.')
            if number > len(match['choices']):
                raise ChoiceError('The choice is past the last one. Run list and choose a shown number.')
            old = read_choices(data, found)
            key = (args.xml, args.option)
            replacement = (args.xml, args.option, number)
            choices = [replacement if item[:2] == key else item for item in old]
            if not any(item[:2] == key for item in old):
                choices.append(replacement)
            write_choices(data, choices)
            result = {'xml': args.xml, 'option': args.option, 'choice': number}
        else:
            disc = args.disc or disc_from_cache()
            if not Path(disc).is_file():
                raise ArgumentError('The disc image is not a file. Pass --disc with a readable image.')
            result = apply(data, found, disc, started)
        print(json.dumps(result, sort_keys=True))
        return 0
    except ChoiceError as exc:
        print(json.dumps({'error': str(exc)}))
        return 1
    except UnicodeError:
        print(json.dumps({'error': "mods.txt isn't UTF-8. Delete it or save it as UTF-8."}))
        return 2
    except OSError as exc:
        print(json.dumps({'error': 'A file operation failed. Check the data folder and try again.'}))
        return 2
    except ArgumentError as exc:
        print(json.dumps({'error': str(exc)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
