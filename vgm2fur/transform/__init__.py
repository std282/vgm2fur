from .tabulate import tabulate, interpolate, merge
from . import to_patterns_fm as fm
from . import to_patterns_psg as psg
from . import to_patterns_dac as dac

def to_patterns_fm6_dac(ym2612_ch6, ym2612_dac, /, voices, mapping, *, rowdur):
    ym2612_ch6_kv = []
    ym2612_select = []
    for k, v, d in ym2612_ch6:
        ym2612_ch6_kv.append((k, v))
        ym2612_select.append(d)
    ym2612_ch6 = ym2612_ch6_kv; del ym2612_ch6_kv
    sel_fm6_dac = zip(ym2612_select, 
        fm.to_patterns(ym2612_ch6, voices), 
        dac.to_patterns(ym2612_dac, mapping=mapping, rowdur=rowdur))
    for sel, fm6_row, dac_row in sel_fm6_dac:
        yield dac_row if sel else fm6_row
