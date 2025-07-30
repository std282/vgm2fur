from .sn76489 import Chip as SN76489
from .ym2612_fm import Chip as YM2612FM
from .ym2612_dac import Chip as YM2612DAC
from vgmtools.vgm import Command as VGMCommand
from typing import Protocol

class Chip(Protocol):
    """Chip trait."""
    supported_commands: frozenset[int]
    """Set of commands that can be handled by this chip."""
    id: str
    """Identification string of this chip."""
    def play(self, cmd: VGMCommand, /): ...
    """Handles given VGM command."""

class UnknownChip(Exception) -> SomeChip:
    def __init__(self, name: str, /):
        super().__init__(name)
        self.name = name
    def __str__(self):
        return 'unknown chip: ' + self.name

def chip(name: str) -> Chip:
    match name.lower():
        case 'ym2612/fm':
            return YM2612FM()
        case 'ym2612/dac':
            return YM2612DAC()
        case 'sn76489':
            return SN76489()
        case _:
            raise UnknownChip(name)

System = tuple[Chip, ...]
def system(name: str) -> System:
    cs: Chipset
    match name.lower():
        case 'genesis':
            return tuple(map(chip, ('ym2612/fm', 'ym2612/dac', 'sn76489')))
        case 'ym2612/fm' | 'sn76489' | 'ym2612/dac':
            return (chip(name),)
        case _:
            raise UnknownChip(name)
    return cs
