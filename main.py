import vgm
import furnace
import transform

import sys
import argparse

def parse_args():
    parser = argparse.ArgumentParser(
        prog='vgm2fur',
        description='A utility to convert VGM files into Furnace modules')
    parser.add_argument('input', type=str)
    parser.add_argument('-o', type=str, required=True, dest='output')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    try:
        song = vgm.load(args.input)
    except Exception as err:
        print(f'error: could not open file "{args.input}": {err}', file=sys.stderr)
        exit(1)
    print('Constructing state table...')
    fm_chip, psg_chip = transform.tabulate(song.events, song.total_wait, 
        period=735, chips=['ym2612', 'sn76489'])
    print('Translating state table to tracker events...')
    psg1, psg2, psg3, noise = transform.to_patterns_psg(psg_chip)
    fm_channels, fm_voices = transform.to_patterns_fm(fm_chip, voice_start=1)
    fm1, fm2, fm3, fm4, fm5, fm6 = fm_channels
    print('Generating Furnace patterns...')
    fur = furnace.Module()
    fur.add_instrument(furnace.instr.psg_blank('PSG_BLANK'))
    for i, (voice, _) in enumerate(sorted(fm_voices.items(), key=lambda x: x[1])):
        fur.add_instrument(furnace.instr.fm_opn(voice, f'FM_VOICE_{i}'))
    fur.add_patterns(fm1, 'fm1')
    fur.add_patterns(fm2, 'fm2')
    fur.add_patterns(fm3, 'fm3')
    fur.add_patterns(fm4, 'fm4')
    fur.add_patterns(fm5, 'fm5')
    fur.add_patterns(fm6, 'fm6')
    fur.add_patterns(psg1, 'psg1')
    fur.add_patterns(psg2, 'psg2')
    fur.add_patterns(psg3, 'psg3')
    fur.add_patterns(noise, 'noise')
    fur.ym2612_volume = 0.5
    fur.song_comment = 'Generated with vgm2fur'
    print('Writing Furnace module...')
    result = fur.build()
    with open(args.output, 'wb') as f:
        f.write(result)
    print('Done.')
