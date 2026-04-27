# vgm2fur

A Python CLI application that allows to convert VGM files to Furnace modules.

> [!WARNING] 
> As of April 2026, this version is abandoned. Please do not expect support. Sorry.

## Installation

**Prerequisites**:
- Python 3.10 or later

**Installation steps**:
- Download wheel file from the latest release;
- Install the wheel file with `pip` or `pipx`.

Wheel file is installed by running a command in OS shell:
```
pip install <path-to-wheel-file>
```
or 
```
pipx install <path-to-wheel-file>
```

After installation you'll be able to call `vgm2fur` from your OS shell.

To uninstall, run a command:
```
pip uninstall vgm2fur
```
or 
```
pipx uninstall vgm2fur
```
depending on which was used to install.

## Usage

Suppose you have a VGM file `input.vgm` and you want to convert it to `output.fur` file.
Said conversion is performed by running a command:
```
vgm2fur input.vgm -o output.fur
```

Alternatively, command
```
vgm2fur file.vgm
```
will convert `file.vgm` to `file.fur`.

Input VGM file can be either compressed (`.vgz`) or uncompressed (`.vgm`).

You can append to the command one or more following options. `iii` means integer value, `fff` means floating point value.
- `--pattern-length=iii` - sets Furnace pattern length, in rows (default is 128).
- `--row-duration=fff` - sets duration of a single Furnace row, in samples (1 sample = 1/44100 sec)
- `--playback-rate=fff` - sets playback rate in Hz (how many rows will get played per second).
- `--skip-samples=iii` - skips initial `iii` samples before starting conversion. Can be useful to get rid of silence at start.
- `--ym2612-volume=fff`, `--sn76489-volume=fff` - sets corresponding chip volume, default is 1
- `--no-latch` disables YM2612 frequency latching; may be necessary if some FM notes disappear in output Furnace module

## Limitations

At the moment only SEGA Genesis (YM2612 + SN76489) VGM modules are supported, with following limitations:
- DAC/PCM is partially supported
- CSM is not supported, program will exit with an error

## Further development

I'm currently privately working on a new version of vgm2fur that is expected to be more sustainable and extensible in the long run, so that it can at last support YM2612 DAC completely and bug-free; and then probably more chips. Unfortunately, by the looks of things, it's probably going to take one me or two more years to bring it to the level of capabilities that this version has.

This project was developed in a rapid succession while I was on a big vacation. I don't think I can afford as much free time to properly develop this project anymore, without sacrificing the development of other interesting and inspiring projects that I also want to pursue.

If someone manages to create their own version of vgm2fur that is better than mine, I'll be glad to be relieved from this responsibility - hell, I'll probably even contribute to it, because I like this project. But until then, I can promise I'll keep investing at least an hour of my time a week to vgm2fur ❤️
