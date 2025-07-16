from typing import NamedTuple

from . import builder
from .module import TARGET_FURNACE_VERSION
from vgm2fur import bitfield

class FMOp(NamedTuple):
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
    ssg: int
    ssg_en: int

class FMVoice(NamedTuple):
    alg: int
    fb: int
    ams: int
    pms: int
    op: tuple[FMOp, FMOp, FMOp, FMOp]

def fm_opn(voice, name=''):
    ins = [
        b'INS2',
        builder.pack('L', 0),
        builder.pack('H', TARGET_FURNACE_VERSION),
        builder.pack('H', 1), # instrument type
        _ins_feature_name(name),
        _ins_feature_fm(voice),
        _ins_feature_end()
    ]
    length = builder.bl_length(ins[2:])
    ins[1] = builder.pack('L', length)
    return b''.join(ins)

def psg_blank(name=''):
    ins = [
        b'INS2',
        builder.pack('L', 0),
        builder.pack('H', TARGET_FURNACE_VERSION),
        builder.pack('H', 0), # instrument type
        _ins_feature_name(name),
        _ins_feature_end()
    ]
    length = builder.bl_length(ins[2:])
    ins[1] = builder.pack('L', length)
    return b''.join(ins)

def _ins_feature_name(name):
    feature = [
        b'NA',
        builder.short(0),
        builder.string(name)
    ]
    length = builder.bl_length(feature[2:])
    feature[1] = builder.short(length)
    return b''.join(feature)

def _ins_feature_end():
    return b'EN'

def _ins_feature_fm(voice):
    flags = bitfield.Bitfield()
    flags[3:0] = 4   # no. of operators
    flags[7:4] = 15  # operator mask (=always active)

    alg_fb = bitfield.Bitfield()
    alg_fb[2:0] = voice.fb
    alg_fb[6:4] = voice.alg
    ams_fms = bitfield.Bitfield()
    ams_fms[2:0] = voice.pms
    ams_fms[5:3] = voice.ams

    feature = [
        b'FM',
        builder.short(0), # length
        builder.byte(flags.all),
        builder.byte(alg_fb.all),
        builder.byte(ams_fms.all),
        builder.byte(0),
        builder.byte(0),
    ]

    for i in [0, 2, 1, 3]:
        op = voice.op[i]
        dt_mult = bitfield.Bitfield()
        dt_mult[3:0] = op.mult
        dt_mult[6:4] = 3 + op.dt
        tl = bitfield.Bitfield()
        tl[6:0] = op.tl
        rs_ar = bitfield.Bitfield()
        rs_ar[4:0] = op.ar
        rs_ar[7:6] = op.rs
        am_dr = bitfield.Bitfield()
        am_dr[4:0] = op.dr
        am_dr[7] = op.am
        kvs_sr = bitfield.Bitfield()
        kvs_sr[4:0] = op.sr
        kvs_sr[6:5] = 2  # KVS
        '''KVS shouldn't be here. It's not a parameter of YM2612, but for some
        obscure reason it has an effect, which makes Furnace ignore note
        volume parameters.'''
        sl_rr = bitfield.Bitfield()
        sl_rr[3:0] = op.rr
        sl_rr[7:4] = op.sl
        ssg = bitfield.Bitfield()
        ssg[2:0] = op.ssg
        ssg[3] = op.ssg_en
        feature += [
            builder.byte(dt_mult.all),
            builder.byte(tl.all),
            builder.byte(rs_ar.all),
            builder.byte(am_dr.all),
            builder.byte(kvs_sr.all),
            builder.byte(sl_rr.all),
            builder.byte(ssg.all),
            builder.byte(0),
        ]
    feature[1] = builder.short(builder.bl_length(feature[2:]))
    return b''.join(feature)
