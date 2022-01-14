import numpy as np
import open3d as o3d

import nanome
from nanome.api.shapes import Mesh
from nanome.api.structure import Complex
from nanome.util.enums import ShapeAnchorType


class OBJLoader:
    def __init__(self, plugin):
        self.plugin = plugin

    async def load(self, name, obj_path, tex_path=None):
        mesh = Mesh()

        o3dmesh = o3d.io.read_triangle_mesh(obj_path)
        o3dmesh = o3dmesh.remove_duplicated_triangles()
        o3dmesh = o3dmesh.remove_degenerate_triangles()
        o3dmesh = o3dmesh.remove_unreferenced_vertices()

        if len(o3dmesh.vertices) == 0:
            raise Exception('file is empty or invalid, only triangle meshes supported')

        # center mesh
        o3dmesh.translate(-o3dmesh.get_center())

        # compute normals if needed
        if not o3dmesh.has_vertex_normals():
            o3dmesh.compute_vertex_normals()

        # use vertex colors if any
        if o3dmesh.has_vertex_colors():
            for c in o3dmesh.vertex_colors:
                mesh.colors += [*c, 1.0]

        if o3dmesh.has_triangle_uvs():
            mesh.uv = np.asarray(o3dmesh.triangle_uvs).flatten()
            if tex_path is not None:
                mesh.texture_path = tex_path

        # get max dimension to normalize scale
        min_bounds = o3dmesh.get_min_bound()
        max_bounds = o3dmesh.get_max_bound()

        # # TODO: figure out what to do about scaling
        # dim = max_bounds - min_bounds
        # scale = 10 / max(dim)
        # o3dmesh.scale(scale, o3dmesh.get_center())

        mesh.vertices = np.asarray(o3dmesh.vertices).flatten()
        mesh.normals = np.asarray(o3dmesh.vertex_normals).flatten()
        mesh.triangles = np.asarray(o3dmesh.triangles).flatten()

        # fill missing or invalid uv/color data
        num_triangles = len(mesh.vertices) // 3
        if len(mesh.uv) / 2 < num_triangles:
            mesh.uv = np.repeat([0.0, 0.0], num_triangles)
        if len(mesh.colors) / 4 < num_triangles:
            mesh.colors = np.repeat([1.0, 1.0, 1.0, 1.0], num_triangles)

        # create empty complex to anchor
        complex = Complex()
        complex.name = name

        molecule = nanome.structure.Molecule()
        chain = nanome.structure.Chain()
        residue = nanome.structure.Residue()

        complex.add_molecule(molecule)
        molecule.add_chain(chain)
        chain.add_residue(residue)

        # add atoms to bounding box to make grabbable
        for x in range(2):
            for y in range(2):
                for z in range(2):
                    atom = nanome.structure.Atom()
                    atom.set_visible(False)
                    atom.position.x = [min_bounds, max_bounds][x][0]
                    atom.position.y = [min_bounds, max_bounds][y][1]
                    atom.position.z = [min_bounds, max_bounds][z][2]
                    residue.add_atom(atom)

        res = await self.plugin.add_to_workspace([complex])

        # anchor mesh to complex
        anchor = mesh.anchors[0]
        anchor.anchor_type = ShapeAnchorType.Complex
        anchor.target = res[0].index

        # upload mesh
        await mesh.upload()
