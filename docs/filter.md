# MIDI Filter

The machine has the possibility to **filter incoming
MIDI messages, altering how they are echoed through
the MIDI Thru**.

midi_thru_filters = [DEDUPE] 

## Available filters

Here is a list of available filters.

#### DEDUPE

Usage: `[DEDUPE]`

It blocks out **consecutive identical messages**.

[DEDUPE] will work differently depending
   on the filter order. If two distinct messages
   end up to be identical after filtering operations,
   [DEDUPE] should go after to catch the second.

#### RESCALE

Usage `[RESCALE][cc][min][max]`

#### CLAMP

Usage `[CLAMP][cc][min][max]`

#### 