from . import vgm
from . import furnace
from . import transform

import sys
import getopt
import enum
import contextlib
import types

@contextlib.contextmanager
def open_or(filename, *args, defaultfile, **kwargs):
    if filename is None:
        yield defaultfile
    else:
        file = open(filename, *args, **kwargs)
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
    except Exception as err:
        print(f'error: could not open file "{filename_in}": {err}', file=sys.stderr)
        exit(1)

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
    fur.song_comment = 'Generated with vgm2fur'
    result = fur.build()
    with open(filename_out, 'wb') as f:
        f.write(result)

    print('Done.')

def _print(filename_in, filename_out, /, *, period):
    try:
        song = vgm.load(filename_in)
    except Exception as err:
        print(f'error: could not open file "{filename_in}": {err}', file=sys.stderr)
        exit(1)
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


if __name__ == '__main__':
    class Action(enum.Enum):
        UNSPEC = ''
        CONVERT = 'convert'
        PRINT = 'print'

    params = types.SimpleNamespace()
    params.infile = None
    params.outfile = None
    action = Action.UNSPEC

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'cpo:', ['convert', 'print'])
    except getopt.GetoptError as err:
        error(err)

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
                error('input file required')
            elif params.outfile is None:
                error('output file required')
            convert(input_file, output_file, period=735)
        case Action.PRINT:
            if params.infile is None:
                error('input file required')
            _print(input_file, output_file, period=735)
