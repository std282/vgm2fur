from vgmtools.chips import ym2612
import copy
from typing import NamedTuple, TypeVar

T = TypeVar('T')
Tuple3 = tuple[T, T, T]
Tuple6 = tuple[T, T, T, T, T, T]

class TrackEntry(NamedTuple):
    t: int
    t0: int
    lfo: int | None
    ch3mode: int
    dac: bool
    fm: Tuple6[FMState]
    ch3op: Tuple3[Ch3OpState]

class TrackTables(NamedTuple):
    t: list[int] = []
    t0: list[int] = []
    lfo: list[int | None] = []
    mode: list[int] = []
    dac: list[bool] = []
    fm: Tuple6[list[FMState]] = ([], [], [], [], [], [])
    ch3op: Tuple3[list[Ch3OpState]] = ([], [], [])

class Resources(NamedTuple):
    voices: dict[Voice, int]

def tables(entries: list[TrackEntry]) -> TrackTables:
    tables = TrackTables()
    for entry in entries:
        tables.t.append(entry.t)
        tables.t0.append(entry.t0)
        tables.lfo.append(entry.lfo)
        tables.mode.append(entry.mode)
        tables.dac.append(entry.dac)
        for i in range(6):
            tables.fm[i].append(entry.fm[i])
        for i in range(3):
            tables.ch3op[i].append(entry.ch3op[i])
    return tables

def resources(entries: TrackTables, vgm: VGM, /):
    voices = {}
    counter = 0
    for ch in entries.fm:
        for fm in ch:
            if fm.voice not in voices:
                voices[fm.voice] = counter
                counter += 1


def write(t: int, t0: int, chip: ym2612.Chip, /) -> TrackEntry:
    return TrackEntry(t=t, t0=t0, 
        lfo=chip.lfo,
        ch3mode=int(chip.ch3mode),
        dac=chip.dac,
        fm=(write_fm(chip.fm[0]),
            write_fm(chip.fm[1]),
            write_fm(chip.fm[2], ch3mode=chip.ch3mode),
            write_fm(chip.fm[3]),
            write_fm(chip.fm[4]),
            write_fm(chip.fm[5])),
        ch3op=tuple(write_ch3op(op) for op in chip.ch3op))

def write_fm(fm: ym2612.FM, /, ch3mode: int = 0):
    voice, vol = write_voice(fm)
    return FMState(
        freq=fm.freq.all, block=fm.block, opmask=fm.opmask,
        trig=fm.trig, voice=voice, vol=vol, pan=int(fm.pan))

def write_voice(fm: ym2612.FM, ch3mode: int, /):
    tl = tuple(op.tl for op in fm.op)
    voice = Voice(
        op=(write_op(op) for op in fm.op),
        fb=fm.fb, alg=fm.alg, ams=fm.ams, pms=fm.pms)
    match fm.alg:
        case _ if ch3mode == 1:
            vol = 0x7F - tl[3]
            voice = copy.replace(voice, 
                op=(copy.replace(voice.op[0], tl=0), 
                    copy.replace(voice.op[1], tl=0),
                    copy.replace(voice.op[2], tl=0),
                    copy.replace(voice.op[3], tl=0)))
        case 0 | 1 | 2 | 3:
            vol = 0x7F - tl[3]
            voice = copy.replace(voice, 
                op=(voice.op[0], 
                    voice.op[1], 
                    voice.op[2], 
                    copy.replace(voice.op[3], tl=0)))
        case 4:
            mtl = min(tl[2:])
            tl = tl[:2] + tuple(x - mtl for x in tl[2:])
            vol = 0x7F - mtl
            voice = copy.replace(voice, 
                op=(voice.op[0], 
                    voice.op[1], 
                    copy.replace(voice.op[2], tl=tl[2]),
                    copy.replace(voice.op[3], tl=tl[3])))
        case 5 | 6:
            mtl = min(tl[1:])
            tl = tl[:1] + tuple(x - mtl for x in tl[1:])
            vol = 0x7F - mtl
            voice = copy.replace(voice, 
                op=(voice.op[0], 
                    copy.replace(voice.op[1], tl=tl[1]),
                    copy.replace(voice.op[2], tl=tl[2]),
                    copy.replace(voice.op[3], tl=tl[3])))
        case 7:
            mtl = min(tl)
            tl = tuple(x - mtl for x in tl)
            vol = 0x7F - mtl
            voice = copy.replace(voice, 
                op=(copy.replace(voice.op[0], tl=tl[0]), 
                    copy.replace(voice.op[1], tl=tl[1]),
                    copy.replace(voice.op[2], tl=tl[2]),
                    copy.replace(voice.op[3], tl=tl[3])))
    return vol, voice


def write_op(op: ym2612.Operator, /):
    return OpState(
        mult=op.mult, dt=op.dt, tl=op.tl, ar=op.ar, rs=op.rs,
        dr=op.dr, am=op.am, sr=op.sr, rr=op.rr, sl=op.sl, ssg=op.ssg)

def write_ch3op(opsp: ym2612.Ch3Op, op: ym2612.Operator  /):
    return Ch3OpState(freq=opsp.freq.all, block=opsp.block, vol=0x7F-op.tl)

class FMState(NamedTuple):
    freq: int
    block: int
    opmask: int
    trig: int
    voice: Voice | int | None
    vol: int
    pan: int

class Voice(NamedTuple):
    op: tuple[OpState, OpState, OpState, OpState]
    fb: int
    alg: int
    ams: int
    pms: int

class OpState(NamedTuple):
    mult: int
    dt: int
    tl: int
    ar: int
    rs: int
    dr: int
    am: int
    sr: int
    rr: int
    sl: int
    ssg: int | None

class Ch3OpState(NamedTuple):
    freq: int
    block: int
    vol: int
