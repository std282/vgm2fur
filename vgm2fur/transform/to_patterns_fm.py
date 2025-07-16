from typing import NamedTuple
import bisect
from vgm2fur import furnace
from vgm2fur import AppError as Vgm2FurError

def prepare_fm(chip):
    fm1, fm2, fm3, fm4, fm5, fm6 = _split_fm(chip)
    fm1 = list(map(_to_key_voice, fm1))
    fm2 = list(map(_to_key_voice, fm2))
    fm3 = list(map(_to_key_voice_mode, fm3))
    fm4 = list(map(_to_key_voice, fm4))
    fm5 = list(map(_to_key_voice, fm5))
    fm6 = list(map(_to_key_voice_dac, fm6))
    return fm1, fm2, fm3, fm4, fm5, fm6

def collect_fm_voices(*channels, voice_start):
    return _collect_voices(channels, voice_start)

def to_patterns_fm(channel, voices):
    return _transform(channel, voices, 0)

def to_patterns_fm3(channel, voices):
    return _transform(channel, voices, 1)

def to_patterns_fm6(channel, voices):
    return _transform(channel, voices, 2)

class FmFreqClass:
    def __init__(self):
        freq_map = _make_fm_freq_map()
        dist_min = (freq_map[1][1] - freq_map[0][1]) // 2
        dist_max = (freq_map[-1][1] - freq_map[-2][1]) // 2
        self.freq_map = freq_map[1:-1]
        self.freq_min = self.freq_map[0][1] - dist_min
        self.freq_max = self.freq_map[-1][1] + dist_max
        self.overfreq_map = _make_fm_overfreq_map(self.freq_map)
        self.underfreq_map = _make_fm_underfreq_map(self.freq_map)

def _make_fm_freq_map():
    freqs = [
    #     B-
        0x260,
    #     C      C#     D      D#     E      F
        0x284, 0x2AA, 0x2D2, 0x2FD, 0x32B, 0x35B,
    #     F#     G      G#     A      A#     B
        0x38E, 0x3C4, 0x3FE, 0x43B, 0x47B, 0x4C0,
    #     C+
        0x508,
    ]
    return [(furnace.notes.b_1 + i, freq) for (i, freq) in enumerate(freqs)]

def _make_fm_overfreq_map(freq_map):
    overfreq_map = []
    note = furnace.notes.C8
    shift = 1
    i = 0
    freq = freq_map[i][1] << shift
    while freq < 0x800:
        overfreq_map.append((note, freq))
        note += 1
        shift += 0 if i < 12 else 1
        i = (i + 1) if i < 12 else 0
        freq = freq_map[i][1] << shift
    return overfreq_map

def _make_fm_underfreq_map(freq_map):
    underfreq_map = []
    note = furnace.notes.b_1
    shift = 1
    i = 11
    freq = freq_map[i][1] >> shift
    while note >= 0:
        underfreq_map.append((note, freq))
        note -= 1
        shift += 0 if i > 0 else 1
        i = (i - 1) if i > 0 else 11
        freq = freq_map[i][1] >> shift
    return underfreq_map[::-1]

FmFreq = FmFreqClass()

def _find_best_note(freq, block):
    if freq < FmFreq.freq_min:
        if block > 0:
            freq *= 2
            block -= 1
        else:
            return _find_best_note_bisect(freq, FmFreq.underfreq_map)
    elif freq > FmFreq.freq_max:
        if block < 7:
            freq //= 2
            block += 1
        else:
            return _find_best_note_bisect(freq, FmFreq.overfreq_map)
    note, disp = _find_best_note_bisect(freq, FmFreq.freq_map)
    note += block * 12
    return note, disp

def _find_best_note_bisect(freq, freq_map):
    i = bisect.bisect(freq_map, freq, key=lambda x: x[1])
    if i < 1:
        (note_l, freq_l) = freq_map[0]
        (note_r, freq_r) = freq_map[1]
        diff_l = freq - freq_l
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_r, diff_r)]
    elif i > len(freq_map) - 2:
        (note_l, freq_l) = freq_map[-2]
        (note_r, freq_r) = freq_map[-1]
        diff_l = freq - freq_l
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_r, diff_r)]
    else:
        (note_l, freq_l) = freq_map[i-1]
        (note_c, freq_c) = freq_map[i]
        (note_r, freq_r) = freq_map[i+1]
        diff_l = freq - freq_l
        diff_c = freq - freq_c
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_c, diff_c), (note_r, diff_r)]
    return min(candidates, key=lambda x: abs(x[1]))

def _split_fm(fmtable):
    chs = tuple(list() for _ in range(6))
    for fm in fmtable:
        for i in range(6):
            chs[i].append(fm.channels[i])
    return chs

class Key(NamedTuple):
    note: int
    disp: int
    vol: int
    id: int
    opmask: int
    pan: int

class Key3Op(NamedTuple):
    note: int
    disp: int
    vol: int

class Key3(NamedTuple):
    op: tuple[Key3Op, Key3Op, Key3Op, Key3Op]
    id: int
    opmask: int
    pan: int

def _to_key_voice(ch):
    if ch.opmask != 0:
        note, disp = _find_best_note(ch.freq, ch.block)
        voice = _extract_voice(ch)
        voice, vol = _normalize_voice(voice)
        key = Key(note=note, disp=disp, vol=vol,
            id=ch.keyid, opmask=ch.opmask, pan=ch.pan)
    else:
        voice = None
        key = Key(note=furnace.notes.Off, disp=0, vol=0, id=ch.keyid, opmask=0, pan=ch.pan)
    return key, voice

class Ch3SpNotSupported(Vgm2FurError):
    def __init__(self):
        super().__init__()
    def __str__(self):
        return f'YM2612 FM3 special mode is not supported'

class CsmNotSupported(Vgm2FurError):
    def __init__(self):
        super().__init__()
    def __str__(self):
        return f'YM2612 CSM is not supported'

def _to_key_voice_mode(ch3):
    if ch3.mode == 0:
        key, voice = _to_key_voice(ch3)
        return key, voice, 0
    elif ch3.mode == 1:
        raise Ch3SpNotSupported()
    else:
        raise CsmNotSupported()
    # note = [0] * 4
    # disp = [0] * 4
    # for i in range(4):
    #     note[i], disp[i] = _find_best_note(
    #         ch3.operators[i].freq, ch3.operators[i].block)
    # voice = _extract_voice(ch3)
    # voice, vol = _normalize_voice3(voice)
    # key = Key3(
    #     op=(
    #         KeyBase(note=note[0], disp=disp[0], vol=vol[0]),
    #         KeyBase(note=note[1], disp=disp[1], vol=vol[1]),
    #         KeyBase(note=note[2], disp=disp[2], vol=vol[2]),
    #         KeyBase(note=note[3], disp=disp[3], vol=vol[3])),
    #     id=ch.keyid, opmask=ch.opmask, pan=ch.pan)
    # return key, voice, 1

def _to_key_voice_dac(ch6):
    key, voice = _to_key_voice(ch6)
    return key, voice, ch6.dac_en

def _extract_voice(ch):
    op1 = ch.op(1)
    op2 = ch.op(2)
    op3 = ch.op(3)
    op4 = ch.op(4)
    return furnace.instr.FMVoice(
        alg=ch.alg, fb=ch.fb, pms=ch.pms, ams=ch.ams, op=(
            furnace.instr.FMOp(mult=op1.mult, dt=op1.dt, tl=op1.tl, ar=op1.ar,
                rs=op1.rs, dr=op1.dr, am=op1.am, sr=op1.sr, rr=op1.rr, sl=op1.sl,
                ssg=op1.ssg, ssg_en=op1.ssg_en),
            furnace.instr.FMOp(mult=op2.mult, dt=op2.dt, tl=op2.tl, ar=op2.ar,
                rs=op2.rs, dr=op2.dr, am=op2.am, sr=op2.sr, rr=op2.rr, sl=op2.sl,
                ssg=op2.ssg, ssg_en=op2.ssg_en),
            furnace.instr.FMOp(mult=op3.mult, dt=op3.dt, tl=op3.tl, ar=op3.ar,
                rs=op3.rs, dr=op3.dr, am=op3.am, sr=op3.sr, rr=op3.rr, sl=op3.sl,
                ssg=op3.ssg, ssg_en=op3.ssg_en),
            furnace.instr.FMOp(mult=op4.mult, dt=op4.dt, tl=op4.tl, ar=op4.ar,
                rs=op4.rs, dr=op4.dr, am=op4.am, sr=op4.sr, rr=op4.rr, sl=op4.sl,
                ssg=op4.ssg, ssg_en=op4.ssg_en)))

def _normalize_voice(voice):
    match voice.alg:
        case 0 | 1 | 2 | 3:
            vol = voice.op[3].tl
            voice = voice._replace(op=(
                voice.op[0], voice.op[1],
                voice.op[2], voice.op[3]._replace(tl=0)))
        case 4:
            tl = (voice.op[1].tl, voice.op[3].tl)
            vol = min(tl)
            tl = (tl[0] - vol, tl[1] - vol)
            voice = voice._replace(op=(
                voice.op[0], voice.op[1]._replace(tl=tl[0]),
                voice.op[2], voice.op[3]._replace(tl=tl[1])))
        case 5 | 6:
            tl = (voice.op[1].tl, voice.op[2].tl, voice.op[3].tl)
            vol = min(tl)
            tl = (tl[0] - vol, tl[1] - vol, tl[2] - vol)
            voice = voice._replace(op=(
                voice.op[0],
                voice.op[1]._replace(tl=tl[0]),
                voice.op[2]._replace(tl=tl[1]),
                voice.op[3]._replace(tl=tl[2])))
        case 7:
            tl = (voice.op[0].tl, voice.op[1].tl, voice.op[2].tl, voice.op[3].tl)
            vol = min(tl)
            tl = (tl[0] - vol, tl[1] - vol, tl[2] - vol, tl[3] - vol)
            voice = voice._replace(op=(
                voice.op[0]._replace(tl=tl[0]),
                voice.op[1]._replace(tl=tl[1]),
                voice.op[2]._replace(tl=tl[2]),
                voice.op[3]._replace(tl=tl[3])))
    return voice, 0x7F - vol

def _normalize_voice3(voice):
    vol = (voice.op[0].tl, voice.op[1].tl, voice.op[2], voice.op[3].tl)
    vol = min(tl)
    voice = voice._replace(op=(
        voice.op[0]._replace(tl=0),
        voice.op[1]._replace(tl=0),
        voice.op[2]._replace(tl=0),
        voice.op[3]._replace(tl=0)))

def _collect_voices(chlist, init=0):
    voices = dict()
    index = init
    for i, ch in enumerate(chlist):
        for state in ch:
            if i == 2 or i == 5:
                (_, voice, _) = state
            else:
                (_, voice) = state
            if voice is not None and voice not in voices:
                voices[voice] = index
                index += 1
    return voices

def _fx_pitch(delta):
    if delta > 0:
        return furnace.effects.pitch_up(delta)
    elif delta < 0:
        return furnace.effects.pitch_down(-delta)
    else:
        return None

def _fx_pan(pan):
    match pan:
        case 0: return furnace.effects.pan(0x00)
        case 1: return furnace.effects.pan(0x01)
        case 2: return furnace.effects.pan(0x10)
        case 3: return furnace.effects.pan(0x11)

def _fx_legato(on):
    if on:
        return furnace.effects.legato(0x01)
    else:
        return furnace.effects.legato(0x00)

def _transform(ch, voices, type):
    note_c = furnace.notes.Off
    disp_c = 0
    vol_c = 0
    keyid_c = -1
    ins_c = -1
    pan_c = 0
    legato = False
    for state in ch:
        match type:
            case 1:
                key, voice, mode = state
                silent = (mode != 0)
            case 2:
                key, voice, dac = state
                silent = (dac != 0)
            case _:
                key, voice = state
                silent = False
        if silent:
            note = furnace.notes.Off
        else:
            note, disp, vol, keyid, _, pan = key
        fx = []

        if note == furnace.notes.Off:
            if legato: fx.append(_fx_legato(0))
            if note == note_c:
                note = None
            yield furnace.Entry(note=note, fx=fx)
            note_c = furnace.notes.Off
            disp_c = 0
            vol_c = 0
            legato = False
            continue

        ins = voices[voice]
        if keyid != keyid_c:
            if disp != 0: fx.append(_fx_pitch(disp))
            if legato: fx.append(_fx_legato(0))
            if pan != pan_c: fx.append(_fx_pan(pan))
            yield furnace.Entry(note=note, ins=ins, vol=vol, fx=fx)
            note_c = note
            disp_c = disp
            vol_c = vol
            keyid_c = keyid
            ins_c = ins
            pan_c = pan
            legato = False
        elif note != note_c or ins != ins_c:
            if disp != 0: fx.append(_fx_pitch(disp))
            if not legato: fx.append(_fx_legato(1))
            if pan != pan_c: fx.append(_fx_pan(pan))
            ins = voices[voice]
            yield furnace.Entry(note=note, ins=ins, vol=vol, fx=fx)
            note_c = note
            disp_c = disp
            vol_c = vol
            ins_c = ins
            pan_c = pan
            legato = True
        else:
            if disp != disp_c: fx.append(_fx_pitch(disp - disp_c))
            if legato: fx.append(_fx_legato(0))
            if pan != pan_c: fx.append(_fx_pan(pan))
            vol_o = vol if vol != vol_c else None
            yield furnace.Entry(vol=vol_o, fx=fx)
            disp_c = disp
            vol_c = vol
            pan_c = pan
            legato = False
