import vgm
import chips
from collections import namedtuple

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

# example for testing

song = vgm.Song('songs/cc_zlfa.vgz')
table = tabulate_genesis(song.events('ym2612', 'sn76489'))
table = decimate_table(table, 735)
with open('table.txt', 'w') as f:
    for entry in table:
        print(f'{entry[0]: 8d} | {entry[1]} | {entry[2]}', file=f)
