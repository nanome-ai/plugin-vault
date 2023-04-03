import zlib

from nanome.api.structure.serializers import WorkspaceSerializer, AtomSerializer
from nanome._internal.network.context import ContextSerialization, ContextDeserialization
from nanome._internal.serializer_fields import ArrayField, DictionaryField, StringField, ByteField, TypeSerializer, LongField

# This package uses undocumented network code, in order to reuse already available serialization code

workspace_serializer = WorkspaceSerializer()
dictionary_serializer = DictionaryField()
dictionary_serializer.set_types(StringField(), ByteField())
atom_dictionary_serializer = DictionaryField()
atom_dictionary_serializer.set_types(LongField(), AtomSerializer())


class VaultWorkspaceSerializer:
    def serialize(self, version, value, context):
        subcontext = context.create_sub_context()
        subcontext.payload["Atom"] = {}
        subcontext.write_using_serializer(workspace_serializer, value)
        context.write_using_serializer(atom_dictionary_serializer, subcontext.payload["Atom"])
        context.write_bytes(subcontext.to_array())

    def deserialize(self, version, context):
        context.payload["Atom"] = context.read_using_serializer(atom_dictionary_serializer)
        return context.read_using_serializer(workspace_serializer)


vault_workspace_serializer = VaultWorkspaceSerializer()
array_serializer = ArrayField()
array_serializer.set_type(vault_workspace_serializer)


def to_data(workspace):
    context = ContextSerialization(0, TypeSerializer.get_version_table())
    context.write_uint(0)  # Version
    context.write_using_serializer(dictionary_serializer, TypeSerializer.get_version_table())
    context.write_using_serializer(vault_workspace_serializer, workspace)
    return zlib.compress(context.to_array())


def list_to_data(workspaces):
    context = ContextSerialization(0, TypeSerializer.get_version_table())
    context.write_uint(0)  # Version
    context.write_using_serializer(dictionary_serializer, TypeSerializer.get_version_table())
    context.write_using_serializer(array_serializer, workspaces)
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

    return context.read_using_serializer(vault_workspace_serializer)


def list_from_data(data):
    data = zlib.decompress(data)
    context = ContextDeserialization(data, TypeSerializer.get_version_table())
    context.read_uint()
    file_version_table = context.read_using_serializer(dictionary_serializer)
    version_table = TypeSerializer.get_best_version_table(file_version_table)

    context = ContextDeserialization(data, version_table)
    context.read_uint()
    context.read_using_serializer(dictionary_serializer)

    return context.read_using_serializer(array_serializer)
