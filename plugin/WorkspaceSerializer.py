import zlib
from dataclasses import dataclass

from nanome.api.structure import Workspace
from nanome.api.structure.serializers import WorkspaceSerializer, AtomSerializer
from nanome._internal.network.context import ContextSerialization, ContextDeserialization
from nanome._internal.serializer_fields import ArrayField, DictionaryField, StringField, ByteField, TypeSerializer, LongField

# This package uses undocumented network code, in order to reuse already available serialization code

workspace_serializer = WorkspaceSerializer()
string_serializer = StringField()
dictionary_serializer = DictionaryField()
dictionary_serializer.set_types(StringField(), ByteField())
atom_dictionary_serializer = DictionaryField()
atom_dictionary_serializer.set_types(LongField(), AtomSerializer())


@dataclass
class Scene:
    workspace: Workspace
    name: str = ""
    description: str = ""


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


class SceneSerializer:
    def serialize(self, version, value, context):
        context.write_using_serializer(string_serializer, value.name)
        context.write_using_serializer(string_serializer, value.description)
        context.write_using_serializer(vault_workspace_serializer, value.workspace)

    def deserialize(self, version, context):
        name = context.read_using_serializer(string_serializer)
        description = context.read_using_serializer(string_serializer)
        workspace = context.read_using_serializer(vault_workspace_serializer)
        return Scene(workspace, name, description)


scene_serializer = SceneSerializer()
scene_list_serializer = ArrayField()
scene_list_serializer.set_type(scene_serializer)


def _write_using_serializer(serializer, data):
    context = ContextSerialization(0, TypeSerializer.get_version_table())
    context.write_uint(0)  # Version
    context.write_using_serializer(dictionary_serializer, TypeSerializer.get_version_table())
    context.write_using_serializer(serializer, data)
    return zlib.compress(context.to_array())


def _read_using_serializer(serializer, data):
    data = zlib.decompress(data)
    context = ContextDeserialization(data, TypeSerializer.get_version_table())
    context.read_uint()
    file_version_table = context.read_using_serializer(dictionary_serializer)
    version_table = TypeSerializer.get_best_version_table(file_version_table)
    context = ContextDeserialization(data, version_table)
    context.read_uint()
    context.read_using_serializer(dictionary_serializer)
    return context.read_using_serializer(serializer)


def workspace_to_data(workspace):
    return _write_using_serializer(vault_workspace_serializer, workspace)


def workspace_from_data(data):
    return _read_using_serializer(vault_workspace_serializer, data)


def scenes_to_data(scenes):
    return _write_using_serializer(scene_list_serializer, scenes)


def scenes_from_data(data):
    return _read_using_serializer(scene_list_serializer, data)
