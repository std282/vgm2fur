import vgm
import furnace
import transform

# example for testing

song = vgm.load('songs/s3_aiz2.vgz')
print('Constructing state table...')
psg_chip = transform.tabulate(song.events, song.total_wait, period=735, chips=['sn76489'])
print('Translating state table to tracker events...')
psg1, psg2, psg3, noise = transform.to_patterns_psg(psg_chip)
fur = furnace.Module()
fur.add_instrument(furnace.PSG_BLANK)
fur.add_patterns(psg1, 'psg1')
fur.add_patterns(psg2, 'psg2')
fur.add_patterns(psg3, 'psg3')
fur.add_patterns(noise, 'noise')
print('Generating Furnace module...')
result = fur.build()
print('Writing results...')
with open('songs/output.fur', 'wb') as f:
    f.write(result)
print('Done.')
