What Is This?
=============

Yet another tool for unpacking PyInstaller bundles.

There's enough already, right? Except that they all (AFAIK) implement their own parsing of PyInstaller's archive format (when PyInstaller itself incorporates a perfectly good parser), and they all (AFAIK) only support decompiling `.pyc` content, whereas PyInstaller 3.0 ships the main script as a directly marshalled code object with no header. (Slapping a header on can work with no other changes, but only if you correctly detected or anticipated the specific bytecode version targeted!)

In theory, this one should be easy to extend to support parsing Python 3.x bytecode on Python 2.x hosts and the inverse -- or may even have that support already, untested though it is.

---

How Do I Use It?
================

Here's the easy part! Note that while the examples use the filename `some.exe`, the archive used is **not** required to be a Windows PE executable.

Let's say `somescript.py` was built into `somescript.exe`. Getting it back out might look like:

```
# First, we're going to list the contents of somescript.exe
# This output is for human consumption only; no guarantees about its stability are made.
pydeinstaller list /path/to/somescript.exe

# Having reviewed that list, we know what we want is named 'somescript'
pydeinstaller extract -Fpy /path/to/somescript.exe somescript somescript.py

# ...it also contained a PYZ-00.pyz//somelib, and perhaps we want that too, but don't need it decompiled.
pydeinstaller extract -Fpyc /path/to/somescript.exe PYZ-00.pyz//somelib somelib.pyc
```
---

Any Future Plans?
=================

Maybe. Sorta. Kinda. If anyone cares. :)

- Support for scanning for .pyc files to autodetect bytecode version is likely.
- An `extract-all` is likely to happen, probably with support for filtering out uninteresting content.
- A test suite is a thing that needs to happen to enable safe future extensions.

---

What Are Its License Terms?
===========================

GPLv3. I'm amenable to releasing the parts that I own under a more permissive BSD or MIT license, but the latest release of `uncompyle` is under GPLv3 terms, and current `xdis` under GPLv2; one would need to analyze whether the interface points date back to the non-copyleft versions of those libraries to determine whether the code can be argued to be derivative of GPL-only content, and at the moment, that effort is difficult to justify.
