# Capture

The **capture function** allows the device **to be controlled
externally**. The best way to do it is with **virtual keys**, where you
can "extend" the device, integrating external switches
into the device's functionalities.

## Setting up  capture

You set up capture in the **global configuration**, by assigning an incoming MIDI channel and a CC# to listen to.

```
ext_capture_cc = [1][30]
```

The device will now capture any CC#30 and perform
actions depending on the value.

> The captured CC# are echoed in any case
> via MIDI Thru.-

## Controlling Keys and Virtual keys

Once capture CC# is specified, the device
will listen for incoming values.

The firmware **always addresses** 32 keys (0-15, hexadecimal 0x00-0x1F), no matter how many physical buttons are there on the device.

The first slots are reserved to the physical keys (in case of the MIDI Captain which has 6 keys, from 0 to 5).

Subsequent keys are treated as virtual. 

They can be **referenced to** in configurations, commands and macros as a shortcut.

> Clearly, virtual buttons have no possibility of
> a LED feedback.

### Using key events correctly

**Important: The device has no knowledge of the actual 
state of an external switch** and therefore can't distinguish between a
click, a long click, key up ... It just handles the incoming
MIDI from it. 

In order to integrate functionalities like up, down, long press, etc. 
correctly, the external device must be programmed to fire the
appropriate CC# values.

For example, if the external device has support for key up and
long press, and I assign it to key 10 (0x0A), I will have to 
program that device to emit 0x4A (74) on key up and 0x2A (42)
on long press in order for the virtual key configuration to
react properly.

Be also mindful of the difference between key down and key up. 
ideally the second shouldn't fire if there is a long press. 
Again, make sure the external device is configured correctly.

## Incoming CC# values

| value hex | value dec | action                       |
|-----------|-----------|------------------------------|
| 0x00-0x1F | 0-31      | press key 0..1F (0..31).     |
| 0x20-0x3F | 32-63     | long press key 0..1F (0..31) |
| 0x40-0x5F | 64-95     | key up key 0..1F (0..31)     |
| 0x60-0x7F | 96-127    | long press up 0..1F (0..31)  |

### Quick reference

For a given key number K (0-31):

| action        | formula  | example (key 8) |
|---------------|----------|------------------|
| press         | K        | 8  (0x08)        |
| long press    | K + 32   | 40 (0x28)        |
| key up        | K + 64   | 72 (0x48)        |
| long press up | K + 96   | 104 (0x68)       |

### Worked example

Goal: use an external two-button footswitch to control
virtual key 8 (toggle delay) via channel 1, CC#30.

**Global config:**
```
ext_capture_cc = [1][30]
```

**Page config:**
```
[key8]
cycle = [2]
label1 = [DLY ON]
label2 = [DLY OF]
key1dn = [1][CC][2][127]
key2dn = [1][CC][2][0]
```

**External device must send on ch1, CC#30:**
- Press: value 8
- Release: value 72
- Long press: value 40
- Long press release: value 104
