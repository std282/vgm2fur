import vgm
import furnace
import transform

import sys
import getopt
import enum
import contextlib

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
    usage = '''usage: vgm2fur <vgm-file> -o <furnace-file> [--period=PERIOD]'''
    print(usage, file=sys.stderr)
    exit(1)

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

def dump(filename_in, filename_out, /, *, period):
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
        Convert = 1
        Dump = 2

    input_file = None
    output_file = None
    action = Action.Convert
    period = 735
    anything = False

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'o:', ['dump', 'period='])
    except getopt.GetoptError as err:
        error(err)

    for key, value in opts:
        match key:
            case '-o':
                output_file = value
            case '--dump':
                action = Action.Dump
            case 'period':
                try:
                    period = int(value)
                except Exception as err:
                    error(f'failed to parse period value: {err}')
                if period <= 0:
                    error(f'invalid period value ({period}); must be a positive number')
        anything = True

    try:
        iargs = iter(args)
        input_file = next(iargs)
        anything = True
        for arg in iargs:
            warning(f'ignored argument: {arg}')
    except StopIteration:
        pass
    del iargs

    if not anything:
        print_usage()

    match action:
        case Action.Convert:
            if input_file is None:
                error('input file required')
            elif output_file is None:
                error('output file required')
            elif period <= 0:
                error(f'invalid period value ({period}); must be a positive number')
            convert(input_file, output_file, period=period)
        case Action.Dump:
            if input_file is None:
                error('input file required')
            elif period < 0:
                error(f'invalid period value ({period}); must be a non-negative number')
            dump(input_file, output_file, period=period)
