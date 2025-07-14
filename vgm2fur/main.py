from . import __version__ as vgm2fur_version

from . import vgm
from . import furnace
from . import transform
from . import AppError

import sys
import getopt
import enum
import contextlib
import types
import gzip
import zlib

def main():
    try:
        _main()
    except AppError as err:
        print(f'error: {err}', file=sys.stderr)

def _main():
    class Action(enum.Enum):
        UNSPEC = ''
        CONVERT = 'convert'
        PRINT = 'print'
        VERSION = 'version'
        DECOMPRESS = 'decompress'

    params = types.SimpleNamespace()
    params.infile = None
    params.outfile = None
    action = Action.UNSPEC

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'cpo:z', 
            ['convert', 'print', 'version', 'decompress'])
    except getopt.GetoptError as err:
        raise ArgParseError(err)

    def warn_ignored_action():
        if action != Action.UNSPEC:
            warning(f'"{action.value}" action ignored')

    for key, value in opts:
        match key:
            case '-o':
                params.outfile = value
            case '-c' | '--convert':
                warn_ignored_action()
                action = Action.CONVERT
            case '-p' | '--print':
                warn_ignored_action()
                action = Action.PRINT
            case '--version':
                warn_ignored_action()
                action = Action.VERSION
            case '-z' | '--decompress':
                warn_ignored_action()
                action = Action.DECOMPRESS

    try:
        iargs = iter(args)
        params.infile = next(iargs)
        for arg in iargs:
            warning(f'ignored argument: {arg}')
    except StopIteration:
        pass
    del iargs

    match action:
        case Action.UNSPEC:            
            print_usage()
            exit(1)
        case Action.CONVERT:
            if params.infile is None:
                raise NoInputFile()
            elif params.outfile is None:
                raise NoOutputFile()
            convert(params.infile, params.outfile, period=735)
        case Action.PRINT:
            if params.infile is None:
                raise NoInputFile()
            print_(params.infile, params.outfile, period=735)
        case Action.VERSION:
            print(f'vgm2fur v{vgm2fur_version}')
        case Action.DECOMPRESS:
            if params.infile is None:
                raise NoInputFile()
            elif params.outfile is None:
                raise NoOutputFile()    
            decompress(params.infile, params.outfile)

class FileOpenReadError(AppError):
    def __init__(self, filename, err):
        super().__init__(filename, err)
        self.filename = filename
        self.err = err
    def __str__(self):
        return f'could not open file "{self.filename}" for reading: {self.err}'

class FileOpenWriteError(AppError):
    def __init__(self, filename, err):
        super().__init__(filename, err)
        self.filename = filename
        self.err = err
    def __str__(self):
        return f'could not open file "{self.filename}" for writing: {self.err}'

class ArgParseError(AppError):
    def __init__(self, err):
        super().__init__(err)
        self.err = err
    def __str__(self):
        return str(self.err)

class InvalidCompressedFileFormat(AppError):
    def __init__(self, filename):
        super().__init__(filename)
        self.filename = filename
    def __str__(self):
        return f'unable to decompress file "{self.filename}": unknown file format'

class NoInputFile(AppError):
    def __init__(self):
        super().__init__()
    def __str__(self):
        return f'no input file provided'

class NoOutputFile(AppError):
    def __init__(self):
        super().__init__()
    def __str__(self):
        return f'no output file provided'

def _open_read(filename):
    try:
        return open(filename, 'rb')
    except OSError as err:
        raise FileOpenReadError(filename, err)

def _open_write(filename):
    try:
        return open(filename, 'wb')
    except OSError as err:
        raise FileOpenWriteError(filename, err)

@contextlib.contextmanager
def _open_write_or(filename, /, *, defaultfile):
    if filename is None:
        yield defaultfile
    else:
        file = _open_write(filename)
        try:
            yield file
        finally:
            file.close()

def warning(message):
    print(f'warning: {message}')

def error(message):
    print(f'error: {message}', file=sys.stderr)
    exit(1)

def print_usage():
    usage = '''usage:
  vgm2fur -c input.vgm -o output.fur'''
    print(usage, file=sys.stderr)

def convert(filename_in, filename_out, /, *, period):
    try:
        song = vgm.load(filename_in)
    except OSError as err:
        raise FileOpenReadError(filename_in) from None

    print('Constructing state table...')
    fm_chip, psg_chip = transform.tabulate(song.events, song.total_wait,
        period=period, chips=['ym2612', 'sn76489'])

    print('Translating state table to tracker events...')
    fur = furnace.Module()

    psg1, psg2, psg3, noise = transform.to_patterns_psg(psg_chip)
    fur.add_instrument(furnace.instr.psg_blank('PSG_BLANK'))
    fur.add_patterns(psg1, 'psg1')
    fur.add_patterns(psg2, 'psg2')
    fur.add_patterns(psg3, 'psg3')
    fur.add_patterns(noise, 'noise')

    fm1, fm2, fm3, fm4, fm5, fm6 = transform.prepare_fm(fm_chip)
    voices = transform.collect_fm_voices(fm1, fm2, fm3, fm4, fm5, fm6,
        voice_start=fur.instrument_count)
    for i, (voice, _) in enumerate(sorted(voices.items(), key=lambda x: x[1])):
        fur.add_instrument(furnace.instr.fm_opn(voice, f'FM_VOICE_{i}'))
    fur.add_patterns(transform.to_patterns_fm(fm1, voices), 'fm1')
    fur.add_patterns(transform.to_patterns_fm(fm2, voices), 'fm2')
    fur.add_patterns(transform.to_patterns_fm3(fm3, voices), 'fm3')
    fur.add_patterns(transform.to_patterns_fm(fm4, voices), 'fm4')
    fur.add_patterns(transform.to_patterns_fm(fm5, voices), 'fm5')
    fur.add_patterns(transform.to_patterns_fm6(fm6, voices), 'fm6')

    print('Writing Furnace module...')
    fur.song_comment = f'Generated with vgm2fur v{vgm2fur_version}'
    result = fur.build()
    with open(filename_out, 'wb') as f:
        f.write(result)
    print('Done.')

def print_(filename_in, filename_out, /, *, period):
    try:
        song = vgm.load(filename_in)
    except OSError as err:
        raise FileOpenReadError(filename_in) from None

    print('Constructing state table...')
    results = transform.tabulate(song.events, song.total_wait,
        period=period, chips=['ym2612', 'sn76489'])

    print('Writing output...')
    with open_or(filename_out, 'w', defaultfile=sys.stdout) as f:
        if period == 0:
            for (t, fm, psg) in results:
                print(f'{t: 8d} || {fm} || {psg}', file=f)
        else:
            for i, (fm, psg) in enumerate(zip(*results)):
                print(f'{i: 8d} || {fm} || {psg}', file=f)
    print('Done.')

def _try_decompress(data, method):
    try:
        match method:
            case 'zlib':
                return zlib.decompress(data)
            case 'gzip':
                return gzip.decompress(data)
            case _:
                return None
    except:
        return None

def decompress(filename_in, filename_out):
    with _open_read(filename_in) as f:
        data_in = f.read()

    print("Decompressing... ")
    for method in ['gzip', 'zlib']:
        data_out = _try_decompress(data_in, method)
        if data_out is not None:
            print(f'Decompressed using {method} method.')
            break
    else:
        raise InvalidCompressedFileFormat(filename_in)

    with _open_write(filename_out) as f:
        f.write(data_out)
    print('Done.')
