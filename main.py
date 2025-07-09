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
        0x3F9, 0x3C0, 0x38A, 0x357, 0x327, 0x2FA, 0x2CF, 0x2A7, 0x281, 0x25D, 
        0x23B, 0x21B, 0x1FC, 0x1E0, 0x1C5, 0x1AC, 0x194, 0x17D, 0x168, 0x153, 
        0x140, 0x12E, 0x11D, 0x10D, 0x0FE, 0x0F0, 0x0E2, 0x0D6, 0x0CA, 0x0BE, 
        0x0B4, 0x0AA, 0x0A0, 0x097, 0x08F, 0x087, 0x07F, 0x078, 0x071, 0x06B, 
        0x065, 0x05F, 0x05A, 0x055, 0x050, 0x04C, 0x047, 0x043, 0x040, 0x03C, 
        0x039, 0x035, 0x032, 0x030, 0x02D, 0x02A, 0x028, 0x026, 0x024, 0x022, 
        0x020, 0x01E, 0x01C, 0x01B, 0x019, 0x018, 0x016, 0x015, 0x014, 0x013, 
        0x012, 0x011, 0x010, 0x00F, 0x00E, 0x00D, 0x00C, 0x00B, 0x00A, 0x009, 
        0x008, 0x007, 0x006, 0x005, 0x004, 0x003, 0x002, 0x001, 0x000
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

def find_notes(entry):
    t = entry.t
    n1, d1 = find_psg_best_note(entry.psg.tonal[0].freq)
    v1 = entry.psg.tonal[0].vol
    n2, d2 = find_psg_best_note(entry.psg.tonal[1].freq)
    v2 = entry.psg.tonal[1].vol
    n3, d3 = find_psg_best_note(entry.psg.tonal[2].freq)
    v3 = entry.psg.tonal[2].vol
    mn = entry.psg.noise.mode
    vn = entry.psg.noise.vol
    return (t, (n1, d1, v1), (n2, d2, v2), (n3, v3, d3), (mn, vn))

def to_sequencer_commands(entries, channel):
    assert (0 <= channel and channel < 3)
    curnote = furnace.notes.Off
    curvol = 15
    curins = -1
    resetporta = 0
    for entry in entries:
        note, disp, vol = entry[1 + channel]
        porta = None
        if resetporta > 0:
            porta = furnace.effects.porta_up(0)
        elif resetporta < 0:
            porta = furnace.effects.porta_down(0)
        resetporta = 0
        if vol == 15:
            note = furnace.notes.Off
            vol = None
        elif vol != curvol:
            curvol = vol
        else:
            vol = None
        ins = None
        if note != curnote:
            curnote = note
            ins = 0
            if disp > 0:
                porta = furnace.effects.porta_up(disp)
                resetporta = 1
            elif disp < 0:
                porta = furnace.effects.porta_down(-disp)
                resetporta = -1
        else:
            note = None
        if porta is not None:
            fx = [porta]
        else:
            fx = None
        vol = 15 - vol if vol is not None else None
        yield furnace.Entry(note, ins, vol, fx)

# example for testing

song = vgm.Song('songs/cc_zlfa.vgz')
print('Constructing state table...')
table = tabulate_genesis(song.events('sn76489'))
print('Decimating state table...')
table = decimate_table(table, 735)
table = map(find_notes, table)
print('Generating Furnace module...')
fur = furnace.Module()
table = list(table)
fur.add_instrument(furnace.PSG_BLANK)
fur.add_patterns(to_sequencer_commands(table, 0), 'psg1')
fur.add_patterns(to_sequencer_commands(table, 1), 'psg2')
fur.add_patterns(to_sequencer_commands(table, 2), 'psg3')
result = fur.build()
print('Writing results...')
with open('table.fur', 'wb') as f:
    f.write(result)
print('Done.')
