#!/usr/bin/env python

'''
Not the first tool of its kind, but the first one to actually try to reuse 3rd-party effort.

Don't reimplement PyInstaller archive parsing (and badly, failing to parse non-PE binaries) when PyInstaller ships its own tools.

Don't assume a specific interpreter release; use xdis to parse whatever we find, or, if there's no .pyc header, make the magic we use configurable (future: try to scan for .pyc files to get a smarter default)
'''

import argparse
import sys
import tempfile
from cStringIO import StringIO

from PyInstaller.archive.readers import CArchiveReader, NotAnArchiveError
import PyInstaller.utils.cliutils.archive_viewer as archive_viewer
import xdis.unmarshal
import xdis.magics
import xdis.std
from uncompyle6.main import decompile

def version2magic(version_str):
    while version_str and '.' in version_str:
        for magic_int, version_str_candidate in xdis.magics.magicint2version.iteritems():
            if version_str_candidate == version_str:
                return magic_int
        version_str = version_str.rsplit('.', 1)[0]
    return None

FMT_UNCHANGED = 'unchanged'
FMT_PYTHON_SOURCE = 'py'
FMT_PYTHON_MODULE = 'pyc'

def coerce_to_format(data_in, desired_format, orig_filename=None, pyver=None):
    '''
    Given:
    - A chunk of data
    - A desired format (one of FMT_UNCHANGED, FMT_PYTHON_SOURCE or FMT_PYTHON_MODULE)
    - An original filename
    - A default Python version to be used if decompilation is needed and no header is present

    ...return a version of that data coerced to that format if possible.
    '''
    data_pyc = None; magic_int = version2magic(pyver); is_pypy = None
    if desired_format == FMT_UNCHANGED:
        return data_in
    ### We may already be a Python module
    try:
        data_in_f = StringIO(data_in)
        version, timestamp, magic_int, code_obj, is_pypy, source_size = xdis.load.load_module_from_file_object(data_in_f, filename = orig_filename)
        data_pyc = data_in
    except ImportError:
        # Parsing as a .pyc file failed
        # However, that doesn't mean we aren't bytecode; we could be a marshalled code object without a header -- which is how pyinstaller stores scripts.
        data_in_f = StringIO(data_in) # if we were closed by xdis.load earlier, recreate
        code_obj = xdis.unmarshal.load_code(data_in_f, magic_int)
    if desired_format == FMT_PYTHON_MODULE:
        if data_pyc is None:
            with tempfile.NamedTemporaryFile() as tf:
                # ...why does this insist on opening the file itself? *hrmph*
                xdis.load.write_bytecode_file(tf.name, code_obj, magic_int)
                data_pyc = tf.read()
        return data_pyc
    # if this point is reached, we have a code_obj and we want Python source
    out = StringIO()
    decompile(xdis.magics.magic_int2float(magic_int), code_obj, out=out, magic_int=magic_int)
    return out.getvalue()

def write_to_output(data, output_str):
    '''Given a chunk of data, and a string representing an output file, write the data to the sink.'''
    is_binary = '\x00' in data
    if output_str is None:
        if is_binary and sys.stdout.isatty():
            raise Exception("Refusing to write binary data to a TTY")
        output = sys.stdout
    else:
        output = open(output_str, 'w')
    output.write(data)
    output.flush()

def _do_list(args):
    reader = CArchiveReader(args.archive.name)
    archive_viewer.show('', reader)

def _do_extract(args):
    reader = CArchiveReader(args.archive.name)
    data = archive_viewer.get_data(args.item, reader)
    if data is None:
        print >>sys.stderr, "Requested item not found in archive"
        return 1
    new_data = coerce_to_format(data, args.format, args.item, args.pyver)
    write_to_output(new_data, args.dest)

def main():
    ap = argparse.ArgumentParser(description='Extract content from a PyInstaller archive')
    subparsers = ap.add_subparsers()
    list = subparsers.add_parser('list', help='list archive contents to stdout')
    list.set_defaults(action=_do_list)
    list.add_argument('archive', type=argparse.FileType('r'), help='PyInstaller-generated archive to read')

    extract = subparsers.add_parser('extract', help='extract a specific file')
    extract.set_defaults(action=_do_list)
    extract.add_argument('--py-version', '-P', dest='pyver', default='2.7.14.final.0', help='If no pyc header is found, which magic do we assume?')
    extract.add_argument('--format', '-F', choices=[FMT_PYTHON_SOURCE, FMT_PYTHON_MODULE, FMT_UNCHANGED], default=FMT_UNCHANGED, help='Desired output format')
    extract.add_argument('archive', type=argparse.FileType('r'), help='PyInstaller-generated archive to read')
    extract.add_argument('item', help='Name of item to retrieve from that archive')
    extract.add_argument('dest', nargs='?')

    args = ap.parse_args()
    sys.exit(args.action(args) or 0)

if __name__ == '__main__':
    sys.exit(main())

# vim: ai et sts=4 sw=4 ts=4
