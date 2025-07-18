from vgm2fur import chips
from typing import NamedTuple

class TableState(NamedTuple):
    t: int
    fm: chips.YM2612
    psg: chips.SN76489

def _tabulate(events):
    fm = chips.YM2612()
    psg = chips.SN76489()
    dac = chips.Sampler()
    t = 0
    table = []
    for action in _events_to_actions(events):
        match action:
            case FmWrite(port, addr, data):
                fm.update(port, addr, data)
            case PsgWrite(data):
                psg.update(data)
            case Wait(delta_t):
                if len(table) == 0 or table[-1].fm != fm or table[-1].psg != psg:
                    table.append(TableState(t, fm.copy(), psg.copy()))
                t += delta_t
            case PlaySample():
                dac.ptr += 1
            case SetSamplePointer(ptr):
                dac.ptr = ptr
                dac.keyid += 1
    return table

def _decimate(table, t_end, period, start):
    assert period > 0
    dectable_fm = []
    dectable_psg = []
    t = start
    i = 0
    while t < t_end:
        while i < len(table) - 1 and not (table[i].t <= t and t < table[i+1].t):
            i += 1
        dectable_fm.append(table[i].fm)
        dectable_psg.append(table[i].psg)
        t += period
    return dectable_fm, dectable_psg

def tabulate_unsampled(events, /, *, chips):
    events = events(*chips)
    table = _tabulate(events)
    ts = []
    fms = []
    psgs = []
    for (t, fm, psg) in table:
        ts.append(t)
        fms.append(fm)
        psgs.append(psg)
    return (ts, fms, psgs)

def tabulate(events, /, *, length, period, chips, skip):
    events = events(*chips)
    fm, psg = _decimate(_tabulate(events), length, period, skip)
    return_mask = 0
    for chip in chips:
        match chip.lower():
            case 'ym2612': return_mask += 1
            case 'sn76489': return_mask += 2
    match return_mask:
        case 1: return fm
        case 2: return psg
        case 3: return (fm, psg)

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

class PlaySample:
    pass

class SetSamplePointer:
    __match_args__ = ('ptr', )
    def __init__(self, ptr):
        self.ptr = ptr

class Unknown:
    __match_args__ = ('event', )
    def __init__(self, event):
        self.event = event

def _events_to_actions(events):
    for event in events:
        match event:
            case (0x52, addr, data):
                yield FmWrite(0, addr, data)
            case (0x53, addr, data):
                yield FmWrite(1, addr, data)
            case (0x50, data):
                yield PsgWrite(data)
            case (0x61, wait_l, wait_h):
                wait = wait_l + wait_h * 256
                yield Wait(wait)
            case (0x62, ):
                yield Wait(735)
            case (0x63, ):
                yield Wait(882)
            case _ if 0x70 <= event[0] and event[0] <= 0x7F:
                yield Wait(event[0] - 0x70 + 1)
            case 0x80:
                yield PlaySample()
            case _ if 0x81 <= event[0] and event[0] <= 0x8F:
                yield PlaySample()
                yield Wait(event[0] - 0x80)
            case (0xE0, a0, a1, a2, a3):
                addr = a0 + (a1 << 8) + (a2 << 16) + (a3 << 24)
                yield SetSamplePointer(addr)
            case _:
                yield Unknown(event)
