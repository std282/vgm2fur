from vgm2fur import chips
from typing import NamedTuple, Any

class TableEntry(NamedTuple):
    t: int
    chip: Any

def _tabulate(events):
    fm = chips.YM2612()
    psg = chips.SN76489()
    dac = chips.Sampler()
    t = 0
    table_fm = []
    table_psg = []
    table_dac = []
    empty = True
    for action in _events_to_actions(events):
        match action:
            case FmWrite(port, addr, data):
                fm.update(port, addr, data)
            case PsgWrite(data):
                psg.update(data)
            case SetSamplePointer(ptr):
                dac.set(ptr)
            case PlaySample():
                dac.play()
            case Wait(delta_t) if empty:
                empty = False
                table_fm.append(TableEntry(t, fm.copy()))
                table_psg.append(TableEntry(t, psg.copy()))
                table_dac.append(TableEntry(t, dac.copy()))
                t += delta_t
            case Wait(delta_t):
                if table_fm[-1].chip != fm:
                    table_fm.append(TableEntry(t, fm.copy()))
                if table_psg[-1].chip != psg:
                    table_psg.append(TableEntry(t, psg.copy()))
                if table_dac[-1].chip != dac:
                    table_dac.append(TableEntry(t, dac.copy()))
                t += delta_t
    return table_fm, table_psg, table_dac

def _find_index(t, i, table):
    while i < len(table) - 1 and not (table[i].t <= t and t < table[i+1].t):
        i += 1
    return i

class TableInterp:
    def __init__(self, table):
        self.table = table
        self.i = 0
    @property
    def _curr(self):
        return self.table[self.i]
    @property
    def _next(self):
        return self.table[self.i + 1]
    def _contains(self, t):
        return self._curr.t <= t and t < self._next.t
    def interpolate(self, t):
        while self.i < len(self.table) - 1 and not self._contains(t):
            self.i += 1
        return self._curr.chip

def _decimate(tables, t_end, period, start):
    assert period > 0
    tablecount = len(tables)
    dectables = tuple([] for _ in range(tablecount))
    interps = tuple(TableInterp(table) for table in tables) 
    t = start
    while t < t_end:
        for i in range(tablecount):
            dectables[i].append(interps[i].interpolate(t))
        t += period
    return dectables

def tabulate_unsampled(events, /, *, chips):
    events = events(*chips)
    fm, psg, dac = _tabulate(events)
    res = []
    for chip in chips:
        match chip:
            case 'ym2612': res.append(fm)
            case 'sn76489': res.append(psg)
            case 'dac': res.append(dac)
    return tuple(res)

class Cursor:
    def __init__(self, table, key):
        self.table = table
        self.index = 0
        self._key = key
    @property
    def value(self):
        if self.end:
            return self.table[-1]
        return self.table[self.index]
    @property
    def end(self):
        return self.index >= len(self.table)
    def key(self):
        if self.end:
            return Infinity()
        return self._key(self)

class Infinity:
    def __lt__(self, other):
        return False

def merge_unsampled(*tables):
    mtable = tuple([] for _ in range(len(tables)))
    cursors = (Cursor(table, key=lambda cur: cur.value.t) for i, table in enumerate(tables))
    while any(not cursor.end for cursor in cursor):
        t = min(cursors, key=Cursor.key).value.t
        mtable[0].append(t)
        for i, cursor in enumerate(cursor):
            mtable[i+1].append(cursor.value)
            if cursor.value.t == t:
                cursor.index += 1
    return mtable

def tabulate(events, /, *, length, period, chips, skip):
    fm, psg, dac = _tabulate(events(*chips))
    tables = []
    for chip in chips:
        match chip.lower():
            case 'ym2612': tables.append(fm)
            case 'sn76489': tables.append(psg)
            case 'dac': tables.append(dac)
    return _decimate(tables, length, period, skip)

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
