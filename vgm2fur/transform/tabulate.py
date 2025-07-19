from vgm2fur import chips
from typing import NamedTuple

class TableState(NamedTuple):
    t: int
    fm: chips.YM2612
    psg: chips.SN76489
    dac: chips.Sampler

    def is_same_as(self, fm, psg, dac):
        return self.fm == fm and self.psg == psg and self.dac == dac


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
                if len(table) == 0 or not table[-1].is_same_as(fm, psg, dac):
                    table.append(TableState(t, fm.copy(), psg.copy(), dac.copy()))
                t += delta_t
            case PlaySample():
                dac.play()
            case SetSamplePointer(ptr):
                dac.set(ptr)
    return table

def _decimate(table, t_end, period, start):
    assert period > 0
    dectable_fm = []
    dectable_psg = []
    dectable_dac = []
    t = start
    i = 0
    while t < t_end:
        while i < len(table) - 1 and not (table[i].t <= t and t < table[i+1].t):
            i += 1
        dectable_fm.append(table[i].fm)
        dectable_psg.append(table[i].psg)
        dectable_dac.append(table[i].dac)
        t += period
    return dectable_fm, dectable_psg, dectable_dac

def tabulate_unsampled(events, /, *, chips):
    events = events(*chips)
    table = _tabulate(events)
    ts = []
    fms = []
    psgs = []
    dacs = []
    for (t, fm, psg, dac) in table:
        ts.append(t)
        fms.append(fm)
        psgs.append(psg)
        dacs.append(dac)
    return (ts, fms, psgs, dacs)

def tabulate(events, /, *, length, period, chips, skip):
    events = events(*chips)
    fm, psg, dac = _decimate(_tabulate(events), length, period, skip)
    res = []
    for chip in chips:
        match chip.lower():
            case 'ym2612': res.append(fm)
            case 'sn76489': res.append(psg)
            case 'dac': res.append(dac)
    return tuple(res)

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
