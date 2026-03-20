# Device configuration

Configuration is done **via editing of text files**. 
A companion editor will be available  in the future.

### Connect device in edit mode

* Make sure the MIDI Captain Midi 6 is turned of
* Connect the MIDI Captain Mini 6 to your computer via USB 
* Turn the device on **while keeping key 0 (the first, upper 
  left corner) pressed**.
* You should now see the device listed as **external
  USB drive** labeled MIDICAPTAIN

![Alt text](files.png)

### How to edit

The configuration text files are under `/ultrasetup` and can
be edited with any text editor.

They are called `page0.txt`, `page1.txt`, ... and contain 
the configuration for each page and in case of page 0, also
some global configurations. 

![Alt text](pagefiles.png)

#### File format

Values are grouped in **sections**, defined as `[sectionName]`.

Assignments are done with this format:

```
config_param1 = [val1]
config_param2 = [val1][val2]
config_param3 = [val1][val2][val3] [val4][val5][val6]
```

* you can assign a single value when suitable, string or numeric
* you can assign a **tuple**
* you can assign an **array of tuples**

>You can find a complete breakdown of the file format specs
> in [the page template file](../ultrasetup/page-template.txt).

#### Caveat

> **Warning:** When creating, deleting or updating the file, 
> it's not advisable to disconnect the device, **as filesystem
> corruption can occur during the firmware update**, making
> the device unusable. This is especially important because
> the I/O operatons **are slow** on this board.
>
> Always use **soft boot** to reboot instead of turning off
> and on; if you need to turn off and on, wait some seconds
> after any save, copy or delete operations.


  
