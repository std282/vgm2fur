from . import builder
from .module import TARGET_FURNACE_VERSION

def _make_psg_blank_ins():
    ins = [
        b'INS2',
        builder.pack('L', 0),
        builder.pack('H', TARGET_FURNACE_VERSION),
        builder.pack('H', 0), # instrument type
        _ins_feature_name("PSG_BLANK"),
        b'EN'
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

PSG_BLANK = _make_psg_blank_ins()
