## Commands

Commands are the actions you want the buttons
to perform.
A command is defined by up to four parameters included in
square brackets:

```
[a][b][c][d]
```

The parameters can be string or numerical depending on the
circumstance. 

### MIDI Commands

When [a] is a number, it's assumed to be a MIDI command.
Format is:

```
[channel][PC|CC|N|NO][value1][value2]
```

`channel` is the MIDI channel and is always 1-based (from 1 to 16). 

### Program change (PC)

Send PC to program `value1` on channel `channel`.

`value1` can also be `inc` or `dec` for next/previous PC
function by a step of `value2`. 
If `value2`=1, they will emulate "previous/next page"
functionality, while if >1, it can be used to skip "banks"
in the devices where the presets are organized in fixed size
banks. If the value is absent, 1 is taken as default.

(As many devices don't offer feedback nor it's
implemented, it will be based on the last PC sent by the 
machine).

```
[channel][PC][value1][value2]

ex.: [1][PC][47]
     [12][PC][dec]
     [7][PC][inc][4]
```

### Control change (CC)

Sent CC to control `value1` of value `value2`. Example sets
CC#33 to value 26 via channel 1:

```
[channel][CC][value1][value2] 

ex.: [1][CC][33][26]
```

### Page change (PAGE)

Go to page `n`:

```
[PAGE][n]
```

> **Warning:** Commands after a `[PAGE]` command 
> are ignored, as the page change implies changing
> all the button's mappings.

### Key press (KEY)

Simulates a footswitch press (we use the term "key" as the
original firmware):

```
[KEY][n][c][lc]
```

`n` is the key number (from 0 to 31). Keys 0-5 are physical;
keys 6-31 are virtual (see CAPTURE.md).
`c` is optional - will activate cycle step c of that key
`lc` is optional - will activate long cycle step lc of that key

> Many times one wants a specific key to be activated when
> loading a page, for example to select a starting Program.
> In this case you can use `[KEY]...` in the `init_commands`
> page variable.

### Macros (CMD)

Executes macro `x`. Macros are defined as `cmd1..cmd9` and can
be declared both at global and at page level.
The page assignments will override the global.

Macros are a convenient way to perform a series of commands. For
example, if you need some parameters to be reset every time you
press any key, you can use `[CMD][x]` instead of repeating the same
commands over and over.

```
[CMD][x]
```

## Use case

The typical use case is **when you have to configure
over and over the same set of operations** on 
different buttons and/or pages.

For example, you might want at each page to reset
certain parameters with CCs; you can define a 
global command:

```
cmd1 = [1][CC][30][0] [1][CC][31][0] [1][CC][32][0] 
```

and then for each page:

```
init_commands: [CMD][1]
```