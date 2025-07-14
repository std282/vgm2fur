# vgm2fur

A Python CLI application that allows to convert VGM files to Furnace modules.

## Installation

**Prerequisites**:
- Python 3.13 or later

**Installation steps**:
- Download wheel file from the latest release;
- Install the wheel file with ``pip`` or ``pipx``.

Wheel file is installed by running a command in OS shell:
```
pip install <path-to-wheel-file>
```
or 
```
pipx install <path-to-wheel-file>
```

After installation you'll be able to call ``vgm2fur`` from your OS shell.

## Usage

Suppose you have a VGM file ``input.vgm`` and you want to convert it to ``output.fur`` file.
Said conversion is performed by running a command:
```
vgm2fur -c input.vgm -o output.fur
```

Input VGM file can be either compressed or uncompressed.

## Limitations

At the moment only SEGA Genesis (YM2612 + SN76489) VGM modules are supported, with following limitations:
- DAC/PCM is not supported, program will ignore it
- FM3 special mode is not supported, program will exit with an error
- CSM is not supported, program will exit with an error
