from .sn76489 import Chip as SN76489
from .ym2612 import Chip as YM2612
from vgmtools.vgm import Command as VGMCommand
from typing import Protocol

class Chip(Protocol):
    def name(self, /) -> str: ...
    def play(self, cmd: VGMCommand, /): ...

class UnknownChip(Exception) -> SomeChip:
    def __init__(self, name: str, /):
        super().__init__(name)
        self.name = name
    def __str__(self):
        return 'unknown chip: ' + self.name

def chip(name: str) -> Chip:
    match name.lower():
        case 'ym2612':
            return YM2612()
        case 'sn76489':
            return SN76489()
        case _:
            raise UnknownChip(name)
