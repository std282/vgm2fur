import vgm
import chips
from collections import namedtuple
import bisect

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

PSG_NOTE_MAP = [
    ('A-0', 0x3F9), ('A#0', 0x3C0), ('B-0', 0x38A),
    ('C-1', 0x357), ('C#1', 0x327), ('D-1', 0x2FA), ('D#1', 0x2CF), ('E-1', 0x2A7), ('F-1', 0x281), 
    ('F#1', 0x25D), ('G-1', 0x23B), ('G#1', 0x21B), ('A-1', 0x1FC), ('A#1', 0x1E0), ('B-1', 0x1C5), 
    ('C-2', 0x1AC), ('C#2', 0x194), ('D-2', 0x17D), ('D#2', 0x168), ('E-2', 0x153), ('F-2', 0x140), 
    ('F#2', 0x12E), ('G-2', 0x11D), ('G#2', 0x10D), ('A-2', 0x0FE), ('A#2', 0x0F0), ('B-2', 0x0E2),
    ('C-3', 0x0D6), ('C#3', 0x0CA), ('D-3', 0x0BE), ('D#3', 0x0B4), ('E-3', 0x0AA), ('F-3', 0x0A0),
    ('F#3', 0x097), ('G-3', 0x08F), ('G#3', 0x087), ('A-3', 0x07F), ('A#3', 0x078), ('B-3', 0x071),
    ('C-4', 0x06B), ('C#4', 0x065), ('D-4', 0x05F), ('D#4', 0x05A), ('E-4', 0x055), ('F-4', 0x050),
    ('F#4', 0x04C), ('G-4', 0x047), ('G#4', 0x043), ('A-4', 0x040), ('A#4', 0x03C), ('B-4', 0x039),
    ('C-5', 0x035), ('C#5', 0x032), ('D-5', 0x030), ('D#5', 0x02D), ('E-5', 0x02A), ('F-5', 0x028),
    ('F#5', 0x026), ('G-5', 0x024), ('G#5', 0x022), ('A-5', 0x020), ('A#5', 0x01E), ('B-5', 0x01C),
    ('C-6', 0x01B), ('C#6', 0x019), ('D-6', 0x018), ('D#6', 0x016), ('E-6', 0x015), ('F-6', 0x014),
    ('F#6', 0x013), ('G-6', 0x012), ('G#6', 0x011), ('A-6', 0x010), ('A#6', 0x00F), ('B-6', 0x00E),
    ('C-7', 0x00D), ('C#7', 0x00C), ('D-7', 0x00B), ('D#7', 0x00A), ('E-7', 0x009), ('F-7', 0x008),
    ('F#7', 0x007), ('G-7', 0x006), ('G#7', 0x005), ('A-7', 0x004), ('A#7', 0x003), ('B-7', 0x002),
    ('C-8', 0x001), ('C#8', 0x000),
]
PSG_NOTE_MAP = PSG_NOTE_MAP[::-1]

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

def transform(entry):
    t = entry.t
    n1, d1 = find_psg_best_note(entry.psg.tonal[0].freq)
    v1 = entry.psg.tonal[0].vol
    n2, d2 = find_psg_best_note(entry.psg.tonal[1].freq)
    v2 = entry.psg.tonal[1].vol
    n3, d3 = find_psg_best_note(entry.psg.tonal[2].freq)
    v3 = entry.psg.tonal[2].vol
    mn = entry.psg.noise.mode
    vn = entry.psg.noise.vol
    return (t, n1, d1, v1, n2, d2, v2, n3, v3, d3, mn, vn)

def entry_to_str(entry):
    (t, n1, d1, v1, n2, d2, v2, n3, v3, d3, mn, vn) = entry
    elements = [f'{t: 8d} | ']
    for (n, d, v) in [(n1, d1, v1), (n2, d2, v2), (n3, d3, v3)]:
        if v == 15:
            elements += ['... ... . | ']
        else:
            elements += [f'{n} {d:+03d} {v:X} | ']
    if vn == 15:
        elements += ['. .']
    else:
        elements += [f'{mn:X} {vn:X}']
    return ''.join(elements)

# example for testing

song = vgm.Song('songs/cc_zlfa.vgz')
print('Constructing state table...')
table = tabulate_genesis(song.events('sn76489'))
print('Decimating state table...')
table = decimate_table(table, 735)
table = map(transform, table)
print('Writing results...')
with open('table.txt', 'w') as f:
    for entry in table:
        print(entry_to_str(entry), file=f)
print('Done.')
