# Pages

Is it possible to define different sets of assignments for the footswitches,
subdivided in different **pages**. 

Each page will have:
* a name
* a distinctive color 
* a set of button configurations

The color and name will be reflected in the top
bar of the display.

Navigating between pages is fully customizable.

![Alt text](pages.png)

Each page has a **configuration file** under  `/ultrasetup/` starting from
 `/ultrasetup/page0.txt`, and then `page1.txt` and so on.  
Page 0  will hold also global configurations. 

Simply add, remove or modify the `pageX.txt` files to add, remove or
modify pages.

> See comments in `page-template.txt` for a complete spec.

### Page navigation

Contrary to the original firmware, **page navigation is completely 
assignable**. 
* the advantage is that we can freely choose which actions will 
trigger page changes for each page and also delegate the function to
external controllers.
* the compromise is that without any explicit configuration, other pages
than 0 are unreachable and navigation must be explicitly implemented on
any page.

#### Example configuration

Alternate between page 0 and 1 using key5's long press:

`page0.txt`:

```
[key5]
key1dn = [PAGE][1]
```

`page1.txt`:

```
[key5]
key1dn = [PAGE][0]
```

### Use cases