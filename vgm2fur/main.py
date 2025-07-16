from . import __version__ as vgm2fur_version

from . import vgm, furnace, transform, chips
from . import AppError

import sys
import getopt
import enum
import contextlib
import gzip
import zlib
import itertools
import warnings
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
        PRINT_ISTATE = 'print-istate'
        VERSION = 'version'
        DECOMPRESS = 'decompress'
        PRINT_VGM = 'print-vgm'

    params = ParamList()

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'co:z',
            ['convert', 'print-istate=', 'version', 'decompress', 'unsampled',
            'print-vgm', 'playback-rate=', 'row-duration=', 'pattern-length=',
            'skip-samples=', 'sn76489-volume=', 'ym2612-volume='])
    except getopt.GetoptError as err:
        raise ArgParseError(err)

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
                params.target = io_target | {
                    'convert': '',
                    'pattern_length': 'pattern length',
                    'row_duration': 'row duration',
                    'playback_rate': 'playback rate',
                    'skip_samples': 'skipped samples count',
                    'ym2612_volume': 'YM2612 volume',
                    'sn76489_volume': 'SN76489 volume',
                }
                params.convert = param
                params.playback_rate = DefaultValue(None)
                params.row_duration = DefaultValue(None)
                params.pattern_length = DefaultValue(128)
                params.skip_samples = DefaultValue(0)
                params.ym2612_volume = DefaultValue(1.0)
                params.sn76489_volume = DefaultValue(1.0)
            case '--print-istate':
                action = Action.PRINT_ISTATE
                params.target = io_target | {
                    'csv_features': 'CSV feature list',
                    'unsampled': '',
                    'pattern_length': 'pattern length',
                    'row_duration': 'row duration',
                    'skip_samples': 'skipped samples count'
                }
                params.csv_features = param
                params.outfile = DefaultValue(None)
                params.unsampled = DefaultValue(False)
                params.pattern_length = DefaultValue(128)
                params.row_duration = DefaultValue(735)
                params.skip_samples = DefaultValue(0)
            case '--version':
                action = Action.VERSION
                params.target = {'version': None}
                params.version = param
            case '-z' | '--decompress':
                action = Action.DECOMPRESS
                params.target = io_target | {'decompress': None}
                param.decompress = param
            case '--unsampled':
                params.unsampled = Param(key, True)
            case '--print-vgm':
                action = Action.PRINT_VGM
                params.target = io_target
                params.outfile = DefaultValue(None)
            case '--pattern-length':
                params.pattern_length = _parse_param(param, int)
                _assert_param(params['pattern_length'], lambda x: 0 < x and x <= 256)
            case '--row-duration':
                params.row_duration = _parse_param(param, float)
                _assert_param(params['row_duration'], lambda x: x > 0)
            case '--playback-rate':
                params.playback_rate = _parse_param(param, float)
                _assert_param(params['playback_rate'], lambda x: x > 0)
            case '--skip-samples':
                params.skip_samples = _parse_param(param, float)
                _assert_param(params['skip_samples'], lambda x: x >= 0)
            case '--ym2612-volume':
                params.ym2612_volume = _parse_param(param, float)
                _assert_param(params['ym2612_volume'], lambda x: x >= 0)
            case '--sn76489-volume':
                params.sn76489_volume = _parse_param(param, float)
                _assert_param(params['sn76489_volume'], lambda x: x >= 0)


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
        case Action.PRINT_ISTATE:
            print_istate(params)
        case Action.VERSION:
            print(f'vgm2fur v{vgm2fur_version}')
        case Action.DECOMPRESS:
            decompress(params)
        case Action.PRINT_VGM:
            print_vgm(params)

class Param(NamedTuple):
    cl_key: str
    value: Any = None

    @classmethod
    def positional(cls, value):
        return cls(cl_key=value, value=value)

class DefaultValue:
    __match_args__ = ('value', )
    def __init__(self, value):
        self.value = value

class ParamList:
    def __init__(self):
        self._paramdict = dict()
        self._target = None

    @staticmethod
    def _warn_ignored_parameter(cl_key):
        if cl_key is not None:
            warnings.warn(f'parameter "{cl_key}" ignored')

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
        self.name = name
    def __str__(self):
        return f'no {self.name} provided'

class InvalidParameter(AppError):
    def __init__(self, param):
        super().__init__(param)
        self.param = param
    def __str__(self):
        return f'parameter "{self.param[0]}" has invalid value: "{self.param[1]}"'

def _parse_param(param, parse):
    try:
        if type(param[1]) is str:
            return Param(param[0], parse(param[1]))
        else:
            return param
    except ValueError:
        raise InvalidParameter(param)

def _assert_param(param, cond):
    if not cond(param[1]):
        raise InvalidParameter(param)

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

def _open_write_text(filename):
    try:
        return open(filename, 'w')
    except OSError as err:
        raise FileOpenWriteError(filename, err)

@contextlib.contextmanager
def _open_write_or(filename, /, *, defaultfile):
    if filename is None:
        yield defaultfile
    else:
        file = _open_write_text(filename)
        try:
            yield file
        finally:
            file.close()

def eprint(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)

def _warning(message, category, filename, lineno, file=None, line=None):
    if file is None:
        file = sys.stderr
    print(f'warning: {message}', file=file)
warnings.showwarning = _warning

def convert(params):
    try:
        song = vgm.load(params.infile)
    except OSError as err:
        raise FileOpenReadError(params.infile, err) from None

    match (params.row_duration, params.playback_rate, song.playback_rate):
        case (None, None, 0):
            row_duration = 735.0
            playback_rate = 60.0
        case (None, None, z):
            row_duration = vgm.SAMPLE_RATE / z
            playback_rate = z
        case (x, None, _):
            row_duration = x
            playback_rate = vgm.SAMPLE_RATE / x
        case (None, y, _):
            row_duration = vgm.SAMPLE_RATE / y
            playback_rate = y
        case (x, y, _):
            row_duration = x
            playback_rate = y

    eprint('Constructing state table...')
    fm_chip, psg_chip = transform.tabulate(song.events,
        length=song.total_wait,
        period=row_duration,
        chips=['ym2612', 'sn76489'],
        skip=params.skip_samples)

    eprint('Translating state table to tracker events...')
    fur = furnace.Module()
    fur.ticks_per_second = playback_rate
    fur.pattern_length = params.pattern_length

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

    fur.ym2612_volume = params.ym2612_volume
    fur.sn76489_volume = params.sn76489_volume

    eprint('Writing Furnace module...')
    fur.song_comment = f'Generated with vgm2fur v{vgm2fur_version}'
    result = fur.build()
    with open(params.outfile, 'wb') as f:
        f.write(result)
    eprint('Done.')

def print_istate(params):
    try:
        song = vgm.load(params.infile)
    except OSError as err:
        raise FileOpenReadError(params.infile, err) from None

    features = params.csv_features.split(',')
    if len(features) == 0:
        raise MissingParameter('CSV feature list')

    if params.unsampled:
        eprint('Constructing state table...')
        t, fm, psg = transform.tabulate_unsampled(song.events,
            chips=['ym2612', 'sn76489'])

        eprint('Writing output...')
        fm = chips.ym2612_csv(fm, features)
        psg = chips.sn76489_csv(psg, features)
        t = ['Sample'] + list(map(str, t))
        with _open_write_or(params.outfile, defaultfile=sys.stdout) as f:
            for (t_csv, csv_fm, csv_psg) in zip(t, fm, psg):
                print(','.join([t_csv, csv_fm, csv_psg]), file=f)
        eprint('Done.')
    else:
        pattern_length = params.pattern_length

        eprint('Constructing state table...')
        fm, psg = transform.tabulate(song.events,
            length=song.total_wait,
            period=params.row_duration,
            chips=['ym2612', 'sn76489'],
            skip=params.skip_samples)

        eprint('Writing output...')
        fm = chips.ym2612_csv(fm, features)
        psg = chips.sn76489_csv(psg, features)
        icsv = iter(zip(itertools.count(-1), fm, psg))
        with _open_write_or(params.outfile, defaultfile=sys.stdout) as f:
            (_, csv_fm, csv_psg) = next(icsv)
            print(','.join(['Pat:Row', csv_fm, csv_psg]), file=f)
            for (n, csv_fm, csv_psg) in icsv:
                pat = n // pattern_length
                row = n % pattern_length
                print(','.join([f'{pat}:{row}', csv_fm, csv_psg]), file=f)
        eprint('Done.')

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

def print_usage():
    usage = '''usage:
  vgm2fur -c input.vgm -o output.fur'''
    eprint(usage)

def print_vgm(params):
    try:
        song = vgm.load(params.infile)
    except OSError as err:
        raise FileOpenReadError(params.infile, err) from None

    eprint('Writing output...')
    with _open_write_or(params.outfile, defaultfile=sys.stdout) as f:
        for csv in vgm.events_csv(song.events('ym2612', 'sn76489')):
            print(csv, file=f)
    eprint('Done.')
