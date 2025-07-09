import vgm
import chips
from collections import namedtuple
import bisect
import furnace

class FmWrite:
    __match_args__ = ('port', 'addr', 'data')
    def __init__(self, port, addr, data):
        self.port = port
        self.addr = addr
        self.data = data

class PsgWrite:
    __match_args__ = ('data', )
    def __init__(self, data):
        self.data = data

class Wait:
    __match_args__ = ('wait', )
    def __init__(self, wait):
        self.wait = wait

class Unknown:
    def __init__(self, event):
        self.event = event

def event_to_action(event):
    match event:
        case (0x52, addr, data):
            return FmWrite(0, addr, data)
        case (0x53, addr, data):
            return FmWrite(1, addr, data)
        case (0x50, data):
            return PsgWrite(data)
        case (0x61, wait_l, wait_h):
            wait = wait_l + wait_h * 256
            return Wait(wait)
        case (0x62, ):
            return Wait(735)
        case (0x63, ):
            return Wait(882)
        case _:
            if 0x70 <= event[0] and event[0] <= 0x7F:
                return Wait(event[0] - 0x70 + 1)
            elif 0x81 <= event[0] and event[0] <= 0x8F:
                return Wait(event[0] - 0x80)
            else:
                return Unknown(event)

TableState = namedtuple('State', 't, fm, psg')
def tabulate_genesis(events):
    fm = chips.YM2612()
    psg = chips.SN76489()
    t = 0
    table = []
    for action in map(event_to_action, events):
        match action:
            case FmWrite(port, addr, data):
                fm = fm.updated(port, addr, data)
            case PsgWrite(data):
                psg = psg.updated(data)
            case Wait(delta_t):
                if len(table) == 0 or table[-1].fm != fm or table[-1].psg != psg:
                    table.append(TableState(t, fm, psg))
                t += delta_t
    return table

def decimate_table(table, period):
    dectable = []
    t_end = table[-1].t
    t = 0
    i = 0
    while t < t_end:
        while not (table[i].t <= t and t < table[i+1].t) and i < len(table) - 1:
            i += 1
        dectable.append(TableState(t, table[i].fm, table[i].psg))
        t += period
    return dectable

def _make_psg_note_map():
    freqs = [
        0x3F9, 0x3C0, 0x38A, 0x357, 0x327, 0x2FA, 0x2CF, 0x2A7, 0x281, 0x25D, # F#1 
        0x23B, 0x21B, 0x1FC, 0x1E0, 0x1C5, 0x1AC, 0x194, 0x17D, 0x168, 0x153, # E-2
        0x140, 0x12E, 0x11D, 0x10D, 0x0FE, 0x0F0, 0x0E2, 0x0D6, 0x0CA, 0x0BE, # D-3
        0x0B4, 0x0AA, 0x0A0, 0x097, 0x08F, 0x087, 0x07F, 0x078, 0x071, 0x06B, # C-4
        0x065, 0x05F, 0x05A, 0x055, 0x050, 0x04C, 0x047, 0x043, 0x040, 0x03C, # A#4
        0x039, 0x035, 0x032, 0x030, 0x02D, 0x02A, 0x028, 0x026, 0x024, 0x022, # G#5
        0x020, 0x01E, 0x01C, 0x01B, 0x019, 0x018, 0x016, 0x015, 0x014, 0x013, # F#6
        0x012, 0x011, 0x010, 0x00F, 0x00E, 0x00D, 0x00C, 0x00B, 0x00A, 0x009, # E-7
        0x008, 0x007, 0x006, 0x005, 0x004, 0x003, 0x002, 0x001, 0x000         # C#8
    ]

    notemap = [(furnace.notes.A0 + i, freq) for (i, freq) in enumerate(freqs)]
    return notemap[::-1]

PSG_NOTE_MAP = _make_psg_note_map()

def find_psg_best_note(freq):
    i = bisect.bisect(PSG_NOTE_MAP, freq, key=lambda x: x[1])
    if i < 1:
        (note_l, freq_l) = PSG_NOTE_MAP[0]
        (note_r, freq_r) = PSG_NOTE_MAP[1]
        diff_l = freq - freq_l
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_r, diff_r)]
    elif i >= len(PSG_NOTE_MAP) - 2:
        (note_l, freq_l) = PSG_NOTE_MAP[-2]
        (note_r, freq_r) = PSG_NOTE_MAP[-1]
        diff_l = freq - freq_l
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_r, diff_r)]
    else:
        (note_l, freq_l) = PSG_NOTE_MAP[i-1]
        (note_c, freq_c) = PSG_NOTE_MAP[i]
        (note_r, freq_r) = PSG_NOTE_MAP[i+1]
        diff_l = freq - freq_l
        diff_c = freq - freq_c
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_c, diff_c), (note_r, diff_r)]
    return min(candidates, key=lambda x: abs(x[1]))

def find_notes(chips):
    n1, d1 = find_psg_best_note(chips.psg.tonal[0].freq)
    v1 = chips.psg.tonal[0].vol
    n2, d2 = find_psg_best_note(chips.psg.tonal[1].freq)
    v2 = chips.psg.tonal[1].vol
    n3, d3 = find_psg_best_note(chips.psg.tonal[2].freq)
    v3 = chips.psg.tonal[2].vol
    mn = chips.psg.noise.mode
    vn = chips.psg.noise.vol
    return ((n1, d1, v1), (n2, d2, v2), (n3, d3, v3), (mn, vn))

def get_psg_channel(notetable, channel):
    if 0 <= channel and channel < 2:
        return [x[channel] for x in notetable]
    elif channel == 2:
        return [(n, d, v, m) for (_, _, (n, d, v), (m, _)) in notetable]
    elif channel == 3:
        return [(n, d, v, m) for (_, _, (n, d, _), (m, v)) in notetable]

def _fx_reset(disp_c):
    if disp_c > 0:
        return [furnace.effects.porta_up(0)]
    elif disp_c < 0:
        return [furnace.effects.porta_down(0)]
    else:
        return None

def _fx_setdisp(disp, disp_c):
    if disp > 0:
        return [furnace.effects.porta_up(disp)]
    elif disp < 0:
        return [furnace.effects.porta_down(-disp)]
    else:
        return _fx_reset(disp_c)

def transform_psg(psglist, *, type='tonal'):
    note_c = furnace.notes.Off
    vol_c = 0
    disp_c = 0
    for psgentry in psglist:
        match type:
            case 'tonal':
                (note, disp, vol) = psgentry
                silent = False
            case 'psg3':
                (note, disp, vol, mode) = psgentry
                silent = ((mode & 3) == 3)
            case 'noise':
                (note, disp, vol, mode) = psgentry
                silent = ((mode & 3) != 3)

        if silent:
            note = furnace.notes.Off
            disp = 0
            vol = 0
        else:
            vol = 15 - vol
            if vol == 0:
                note = furnace.notes.Off
                disp = 0
            disp = -disp

        if note != note_c or disp != disp_c:
            if note == furnace.notes.Off:
                yield furnace.Entry(note=note, fx=_fx_reset(disp_c))
                disp_c = 0
            else:
                yield furnace.Entry(note=note, vol=vol, ins=0, fx=_fx_setdisp(disp, disp_c))
                disp_c = disp
            note_c = note
            vol_c = vol
        elif vol != vol_c:
            yield furnace.Entry(vol=vol, fx=_fx_reset(disp_c))
            vol_c = vol
            disp_c = 0
        else:
            yield furnace.Entry(fx=_fx_reset(disp_c))
            disp_c = 0

def test_sequence_psg():
    yield furnace.Entry(note=furnace.notes.C2, ins=0, vol=15)
    yield from [furnace.Entry()] * 7
    yield furnace.Entry(note=furnace.notes.E2, ins=0, vol=15)
    yield from [furnace.Entry()] * 7
    yield furnace.Entry(note=furnace.notes.G2, ins=0, vol=15)
    yield from [furnace.Entry()] * 7
    yield furnace.Entry(note=furnace.notes.As2, ins=0, vol=15)
    yield from [furnace.Entry()] * 7
    yield furnace.Entry(note=furnace.notes.Off)

# example for testing

song = vgm.Song('songs/bof_p.vgz')
print('Constructing state table...')
table = tabulate_genesis(song.events('sn76489'))
print('Decimating state table...')
table = decimate_table(table, 735)
print('Translating state table to tracker events...')
table = map(find_notes, table)
fur = furnace.Module()
table = list(table)
psg1 = get_psg_channel(table, 0)
psg2 = get_psg_channel(table, 1)
psg3 = get_psg_channel(table, 2)
noise = get_psg_channel(table, 3)
fur.add_instrument(furnace.PSG_BLANK)
fur.add_patterns(transform_psg(psg1), 'psg1')
fur.add_patterns(transform_psg(psg2), 'psg2')
fur.add_patterns(transform_psg(psg3, type='psg3'), 'psg3')
fur.add_patterns(transform_psg(noise, type='noise'), 'noise')
print('Generating Furnace module...')
result = fur.build()
print('Writing results...')
with open('songs/output.fur', 'wb') as f:
    f.write(result)
print('Done.')
