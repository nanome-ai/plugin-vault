import os
import traceback
import zlib

from nanome.util import Logs
from nanome._internal._network._serialization import _ContextSerialization, _ContextDeserialization
from nanome._internal._structure._serialization import _WorkspaceSerializer, _AtomSerializer
from nanome._internal._util._serializers import _DictionarySerializer, _StringSerializer, _ByteSerializer, _TypeSerializer, _LongSerializer

# This package uses undocumented network code, in order to reuse already available serialization code

workspace_serializer = _WorkspaceSerializer()
dictionary_serializer = _DictionarySerializer()
dictionary_serializer.set_types(_StringSerializer(), _ByteSerializer())
atom_dictionary_serializer = _DictionarySerializer()
atom_dictionary_serializer.set_types(_LongSerializer(), _AtomSerializer())

def to_data(workspace):
    context = _ContextSerialization(0, _TypeSerializer.get_version_table())
    context.write_uint(0) # Version
    context.write_using_serializer(dictionary_serializer, _TypeSerializer.get_version_table())

    subcontext = context.create_sub_context()
    subcontext.payload["Atom"] = {}
    subcontext.write_using_serializer(workspace_serializer, workspace)
    context.write_using_serializer(atom_dictionary_serializer, subcontext.payload["Atom"])
    context.write_bytes(subcontext.to_array())

    return zlib.compress(context.to_array())

def from_data(data):
    data = zlib.decompress(data)
    context = _ContextDeserialization(data, _TypeSerializer.get_version_table())
    context.read_uint()
    file_version_table = context.read_using_serializer(dictionary_serializer)
    version_table = _TypeSerializer.get_best_version_table(file_version_table)

    context = _ContextDeserialization(data, version_table)
    context.read_uint()
    context.read_using_serializer(dictionary_serializer)
    context.payload["Atom"] = context.read_using_serializer(atom_dictionary_serializer)

    return context.read_using_serializer(workspace_serializer)
