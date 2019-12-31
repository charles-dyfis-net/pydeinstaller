#!/usr/bin/env python

'''
Not the first tool of its kind, but the first one to actually try to reuse 3rd-party effort.

Don't reimplement PyInstaller archive parsing (and badly, failing to parse non-PE binaries) when PyInstaller ships its own tools.

Don't assume a specific interpreter release; use xdis to parse whatever we find, or, if there's no .pyc header, make the magic we use configurable (future: try to scan for .pyc files to get a smarter default)
'''

import argparse
import collections
import sys
import tempfile

from pprint import pprint
from future.utils import iteritems

from io import BytesIO

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

from PyInstaller.utils.cliutils.archive_viewer import ZlibArchive
import PyInstaller.archive.readers as pyi_readers
import PyInstaller.utils.cliutils.archive_viewer as pyi_archive_viewer
import PyInstaller.building.api as pyi_build_api
import xdis.unmarshal
import xdis.magics
import xdis.std
from uncompyle6.main import decompile

TocTuple = collections.namedtuple('TocTuple', ['name', 'pos', 'length', 'uncompressed_len', 'iscompressed', 'item_type'])

str_type = type('')
byte_type = type(''.encode('utf-8'))
def as_string(s):
    if isinstance(s, byte_type):
        return s.decode('utf-8')
    return s

def as_bytes(s):
    if isinstance(s, str_type):
        return s.encode('utf-8')
    return s

def reverse_dict(d):
    result = { }
    for k, v in iteritems(d):
        result[v] = k
    return result

ITEM_TYPES = reverse_dict(pyi_build_api.PKG.xformdict)

class ArchiveReader(object):

    def __init__(self, *args, **kwargs):
        self.__tempfiles = {}
        self.__nested_archives = {}

    @staticmethod
    def open_archive(filename):
        if filename.lower().endswith('.pyz'):
            retval = ZlibArchiveReader(filename)
        else:
            retval = CArchiveReader(filename)
        ArchiveReader.__init__(retval)
        return retval

    def get_nested_archive(self, name):
        if name in self.__nested_archives:
            return self.__nested_archives[name]
        archive_data = self.get_data(name)
        tf = tempfile.NamedTemporaryFile(prefix='pydins_', suffix=('_%s' % (name,)))
        tf.write(archive_data)
        tf.flush()
        self.__tempfiles[name] = tf
        self.__nested_archives[name] = self.open_archive(tf.name)
        return self.__nested_archives[name]

    def get_data(self, item_name):
        if not '//' in item_name:
            return pyi_archive_viewer.get_data(item_name, self)
        (nested_archive_name, inner_item) = item_name.split('//', 1)
        return self.get_nested_archive(nested_archive_name).get_data(inner_item)

    def recursive_toc(self, inherited_prefix=None):
        for item in self.toc_tuples():
            if inherited_prefix:
                yield item._replace(name='%s//%s' % (inherited_prefix, as_string(item.name)))
            else:
                yield item
            if item.item_type == 'PYZ':
                for inner_item in self.get_nested_archive(item.name).recursive_toc(item.name):
                    yield inner_item


class CArchiveReader(pyi_readers.CArchiveReader, ArchiveReader):
    def toc_tuples(self):
        for (pos, length, uncompressed_len, iscompressed, type_char, name) in self.toc.data:
            yield TocTuple(
                name=name,
                pos=pos,
                length=length,
                uncompressed_len=uncompressed_len,
                iscompressed=bool(iscompressed),
                item_type=ITEM_TYPES[type_char])

class ZlibArchiveReader(pyi_archive_viewer.ZlibArchive, ArchiveReader):
    def toc_tuples(self):
        for (item_name, (item_ispkg, item_pos, item_len)) in iteritems(self.toc):
            yield TocTuple(
                name=item_name,
                pos=item_pos,
                length=item_len,
                uncompressed_len=item_len,
                iscompressed=False,
                item_type=None)

def version2magic(version_str):
    while version_str and '.' in version_str:
        for magic_int, version_str_candidate in iteritems(xdis.magics.magicint2version):
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
        data_in_f = BytesIO(data_in)
        version, timestamp, magic_int, code_obj, is_pypy, source_size = xdis.load.load_module_from_file_object(data_in_f, filename = orig_filename)
        data_pyc = data_in
    except ImportError:
        # Parsing as a .pyc file failed
        # However, that doesn't mean we aren't bytecode; we could be a marshalled code object without a header -- which is how pyinstaller stores scripts.
        data_in_f = BytesIO(data_in) # if we were closed by xdis.load earlier, recreate
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
    data_bytes = as_bytes(data)
    is_binary = as_bytes('\x00') in data_bytes
    if output_str is None:
        if is_binary and sys.stdout.isatty():
            raise Exception("Refusing to write binary data to a TTY")
        output = sys.stdout
    else:
        output = open(output_str, 'w')
    if hasattr(output, 'buffer'):
        output.buffer.write(data_bytes)
        output.buffer.flush()
    else:
        output.write(data)
    output.flush()

def _do_list(args):
    reader = ArchiveReader.open_archive(args.archive.name)
    if args.long:
        pprint(list(reader.recursive_toc()))
        return 0
    for item in reader.recursive_toc():
        sys.stdout.write(as_string(item.name))
        sys.stdout.write(args.sep)
    return 0

def _do_extract(args):
    reader = ArchiveReader.open_archive(args.archive.name)
    data = reader.get_data(args.item)
    if data is None:
        print >>sys.stderr, "Requested item not found in archive"
        return 1
    new_data = coerce_to_format(data, args.format, args.item, args.pyver)
    write_to_output(new_data, args.dest)

def main():
    ap = argparse.ArgumentParser(description='Extract content from a PyInstaller archive')
    subparsers = ap.add_subparsers()
    list = subparsers.add_parser('list', help='list archive contents to stdout')
    list.set_defaults(action=_do_list, sep='\n')
    list.add_argument('-l', dest='long', action='store_true', help='Human-readable listing; more details, not in a format intended for scripted consumption')
    list.add_argument('-z', '--null', action='store_const', const='\0', dest='sep', help='Use NULs rather than newlines to separate entries')
    list.add_argument('archive', type=argparse.FileType('r'), help='PyInstaller-generated archive to read')

    extract = subparsers.add_parser('extract', help='extract a specific file')
    extract.set_defaults(action=_do_extract)
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
