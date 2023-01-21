import zlib

from nanome._internal.network.context import ContextSerialization, ContextDeserialization
from nanome._internal.structure.serializers import _WorkspaceSerializer, _AtomSerializer
from nanome._internal.util.type_serializers import DictionarySerializer, StringSerializer, ByteSerializer, TypeSerializer, LongSerializer

# This package uses undocumented network code, in order to reuse already available serialization code

workspace_serializer = _WorkspaceSerializer()
dictionary_serializer = DictionarySerializer()
dictionary_serializer.set_types(StringSerializer(), ByteSerializer())
atom_dictionary_serializer = DictionarySerializer()
atom_dictionary_serializer.set_types(LongSerializer(), _AtomSerializer())

def to_data(workspace):
    context = ContextSerialization(0, TypeSerializer.get_version_table())
    context.write_uint(0) # Version
    context.write_using_serializer(dictionary_serializer, TypeSerializer.get_version_table())

    subcontext = context.create_sub_context()
    subcontext.payload["Atom"] = {}
    subcontext.write_using_serializer(workspace_serializer, workspace)
    context.write_using_serializer(atom_dictionary_serializer, subcontext.payload["Atom"])
    context.write_bytes(subcontext.to_array())

    return zlib.compress(context.to_array())

def from_data(data):
    data = zlib.decompress(data)
    context = ContextDeserialization(data, TypeSerializer.get_version_table())
    context.read_uint()
    file_version_table = context.read_using_serializer(dictionary_serializer)
    version_table = TypeSerializer.get_best_version_table(file_version_table)

    context = ContextDeserialization(data, version_table)
    context.read_uint()
    context.read_using_serializer(dictionary_serializer)
    context.payload["Atom"] = context.read_using_serializer(atom_dictionary_serializer)

    return context.read_using_serializer(workspace_serializer)
