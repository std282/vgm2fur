from . import __version__ as vgm2fur_version

from . import vgm
from . import furnace
from . import transform
from . import AppError

import sys
import getopt
import enum
import contextlib
import gzip
import zlib
from typing import NamedTuple, Any

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

    params = ParamList()

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'cpo:z', 
            ['convert', 'print', 'version', 'decompress'])
    except getopt.GetoptError as err:
        raise ArgParseError(err)

    def warn_ignored_action():
        if action != Action.UNSPEC:
            warning(f'"{action.value}" action ignored')

    io_target = {
        'infile': 'input file', 
        'outfile': 'output file'
    }
    for key, value in opts:
        param = Param(key, value)
        match key:
            case '-o':
                params.outfile = param
            case '-c' | '--convert':
                action = Action.CONVERT
                params.target = io_target | {'convert': None}
                params.convert = param
            case '-p' | '--print':
                action = Action.PRINT
                params.target = io_target | {'print': None}
                params.print = param
                params.outfile = DefaultValue(outfile)
            case '--version':
                action = Action.VERSION
                params.target = {'version': None}
                params.version = param
            case '-z' | '--decompress':
                action = Action.DECOMPRESS
                params.target = io_target | {'decompress': None}
                param.decompress = param

    try:
        iargs = iter(args)
        params.infile = Param.positional(next(iargs))
        for arg in iargs:
            params.ignored = Param.positional(arg)
    except StopIteration:
        pass
    del iargs

    params.check_target()
    match action:
        case Action.UNSPEC:            
            print_usage()
            exit(1)
        case Action.CONVERT:
            convert(params)
        case Action.PRINT:
            print_(params)
        case Action.VERSION:
            print(f'vgm2fur v{vgm2fur_version}')
        case Action.DECOMPRESS:
            decompress(params)


class Param(NamedTuple):
    cl_key: str
    value: Any = None
    
    @classmethod
    def positional(cls, value):
        return cls(cl_key=value, value=value)

class DefaultValue:
    __match_args__ = ['value']
    def __init__(self, value):
        self.value = value

class ParamList:
    def __init__(self):
        self._paramdict = dict()
        self._target = None

    @staticmethod
    def _warn_ignored_parameter(cl_key):
        if cl_key is not None:
            warning(f'parameter "{cl_key}" ignored')

    def __getattr__(self, key):
        try:
            return self._paramdict[key].value
        except KeyError:
            raise AttributeError(f'ParamList object has no attribute "{key}"') from None

    _reserved_fields = frozenset(['_paramdict', '_target', 'target', 'ignored'])
    def __setattr__(self, key, value):
        if key in ParamList._reserved_fields:
            super().__setattr__(key, value)
        else:
            self._add_param(key, value)

    def __getitem__(self, key):
        return self._paramdict[key]

    def __setitem__(self, key, value):
        self._add_param(key, value)

    def _add_param(self, key, value):
        match value:
            case DefaultValue(x):
                if key not in self._paramdict:
                    self._paramdict[key] = Param(None, x)
            case Param(_, _):
                self._paramdict[key] = value
                if self._target is not None and key not in self._target:
                    ParamList._warn_ignored_parameter(value.cl_key)
            case _:
                raise ValueError(f'invalid value assign: {value}')

    @property
    def target(self):
        return self._target

    @target.setter
    def target(self, value):
        self._target = value
        present_params = set(self._paramdict.keys())
        bad_params = present_params - set(self._target.keys())
        for param in bad_params:
            paraminfo = self._paramdict[param]
            ParamList._warn_ignored_parameter(paraminfo.cl_key)

    @property
    def ignored(self):
        return None

    @ignored.setter
    def ignored(self, value):
        ParamList._warn_ignored_parameter(value.cl_key)

    def check_target(self):
        for (key, name) in self._target.items():
            if key not in self._paramdict:
                raise MissingParameter(name)

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

class MissingParameter(AppError):
    def __init__(self, name):
        super().__init__(name)
    def __str__(self):
        return f'no {self.name} provided'

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

def convert(params):
    try:
        song = vgm.load(params.infile)
    except OSError as err:
        raise FileOpenReadError(params.infile) from None

    print('Constructing state table...')
    fm_chip, psg_chip = transform.tabulate(song.events, 
        length=song.total_wait,
        period=735, 
        chips=['ym2612', 'sn76489'])

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
    with open(params.outfile, 'wb') as f:
        f.write(result)
    print('Done.')

def print_(params):
    try:
        song = vgm.load(params.infile)
    except OSError as err:
        raise FileOpenReadError(params.infile) from None

    print('Constructing state table...')
    results = transform.tabulate(song.events,
        length=song.total_wait,
        period=735,
        chips=['ym2612', 'sn76489'])

    print('Writing output...')
    with open_or(params.outfile, 'w', defaultfile=sys.stdout) as f:
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

def decompress(params):
    with _open_read(params.infile) as f:
        data_in = f.read()

    print("Decompressing... ")
    for method in ['gzip', 'zlib']:
        data_out = _try_decompress(data_in, method)
        if data_out is not None:
            print(f'Decompressed using {method} method.')
            break
    else:
        raise InvalidCompressedFileFormat(params.infile)

    with _open_write(params.outfile) as f:
        f.write(data_out)
    print('Done.')
