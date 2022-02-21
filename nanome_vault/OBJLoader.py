import os
import shutil
import tempfile
from dataclasses import dataclass
from functools import partial
from math import inf

import nanome
from nanome import ui
from nanome.api.shapes import Mesh
from nanome.api.structure import Atom, Chain, Complex, Molecule, Residue
from nanome.util import async_callback, Vector3
from nanome.util.enums import ShapeAnchorType

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
MENU_PATH = os.path.join(BASE_DIR, 'menus', 'json', 'obj_menu.json')

def flatten(iterable):
    for item in iterable:
        try:
            yield from flatten(item)
        except TypeError:
            yield item

@dataclass
class OBJ:
    complex: Complex
    mesh: Mesh
    vertices: "list[Vector3]"
    texture: tempfile.NamedTemporaryFile
    min_bounds: Vector3
    max_bounds: Vector3
    scale: float = 1.0

class OBJLoader:
    def __init__(self, plugin: nanome.PluginInstance):
        self.plugin = plugin
        self.objs: list[OBJ] = []
        self.selected_obj: OBJ = None
        self.create_menu()

    def create_menu(self):
        self.menu = ui.Menu.io.from_json(MENU_PATH)
        self.menu.index = 1
        root: ui.LayoutNode = self.menu.root

        self.ln_list: ui.LayoutNode = root.find_node('OBJ List')
        self.ln_obj: ui.LayoutNode = root.find_node('OBJ Details')

        self.lst_objs: ui.UIList = self.ln_list.get_content()
        self.lbl_obj: ui.Label = self.ln_obj.find_node('Name').get_content()
        self.inp_scale: ui.TextInput = self.ln_obj.find_node('Scale Input').get_content()

        btn_scale_down: ui.Button = self.ln_obj.find_node('Scale Down').get_content()
        btn_scale_down.register_pressed_callback(partial(self.increment_scale, -1))

        btn_scale_up: ui.Button = self.ln_obj.find_node('Scale Up').get_content()
        btn_scale_up.register_pressed_callback(partial(self.increment_scale, 1))

        btn_back: ui.Button = self.ln_obj.find_node('Back').get_content()
        btn_back.register_pressed_callback(self.show_list)

        btn_delete: ui.Button = self.ln_obj.find_node('Delete').get_content()
        btn_delete.register_pressed_callback(self.delete_obj)
        btn_delete.disable_on_press = True

        btn_apply: ui.Button = self.ln_obj.find_node('Apply').get_content()
        btn_apply.register_pressed_callback(self.apply_scale)
        btn_apply.disable_on_press = True

    def show_list(self, btn=None):
        self.selected_obj = None
        self.ln_list.enabled = True
        self.ln_obj.enabled = False

        self.lst_objs.items.clear()
        for obj in self.objs:
            ln = ui.LayoutNode()
            btn = ln.add_new_button(obj.complex.name)
            btn.obj = obj
            btn.register_pressed_callback(self.show_obj)
            self.lst_objs.items.append(ln)

        self.menu.enabled = True
        self.plugin.update_menu(self.menu)

    def show_obj(self, btn):
        self.selected_obj = btn.obj
        self.ln_list.enabled = False
        self.ln_obj.enabled = True
        self.lbl_obj.text_value = btn.obj.complex.name
        self.inp_scale.input_text = btn.obj.scale
        self.plugin.update_menu(self.menu)

    def increment_scale(self, delta, btn):
        scale = float(self.inp_scale.input_text)
        self.inp_scale.input_text = f'{scale + delta:.1f}'
        self.plugin.update_content(self.inp_scale)

    @async_callback
    async def delete_obj(self, btn):
        obj = self.selected_obj
        self.objs.remove(obj)
        await obj.mesh.destroy()
        await self.plugin.remove_from_workspace([obj.complex])
        if obj.texture:
            obj.texture.close()
        self.show_list()

    @async_callback
    async def apply_scale(self, btn):
        obj: OBJ = self.selected_obj
        scale = float(self.inp_scale.input_text)
        self.scale_obj(obj, scale)

        complexes = await self.plugin.request_complexes([obj.complex.index])
        obj.complex.position = complexes[0].position
        obj.complex.rotation = complexes[0].rotation

        await obj.mesh.upload()
        await self.plugin.update_structures_deep([obj.complex])
        self.plugin.update_content(btn)

    async def load(self, name, obj_path, tex_path=None):
        mesh = Mesh()

        with open(obj_path, 'r') as f:
            lines = f.readlines()

        num_vertices = len(list(filter(lambda l: l.startswith('v '), lines)))
        def vertex_index(i):
            if isinstance(i, str):
                if i == '':
                    return -1
                i = int(i)
            return i - 1 if i > 0 else num_vertices + i

        colors = []
        normals = []
        triangles = []
        uvs = []
        vertices = []

        for line in lines:
            items = line.split()
            if not items:
                continue

            type, *args = items
            if type == 'v':
                x, y, z, *c = map(float, args)
                v = Vector3(x, y, z)
                vertices.append(v)

                if len(c) == 3:
                    colors.append((*c, 1))

            elif type == 'vn':
                x, y, z = map(float, args)
                normals.append((x, y, z))

            elif type == 'vt':
                u, v = map(float, args)
                uvs.append((u, v))

            elif type == 'f':
                # args like "1/2/3 4/5/6 7/8/9"
                verts = [tuple(map(vertex_index, v.split('/'))) for v in args]
                a = verts[0]
                for b, c in zip(verts[1:], verts[2:]):
                    triangles.append((a, b, c))

        # get bounds
        min_bounds = Vector3(inf, inf, inf)
        max_bounds = Vector3(-inf, -inf, -inf)
        for vertex in vertices:
            min_bounds.set(*map(min, zip(vertex, min_bounds)))
            max_bounds.set(*map(max, zip(vertex, max_bounds)))

        # scale to fit
        center = (min_bounds + max_bounds) / 2
        dimensions = max_bounds - min_bounds
        scale = 10 / max(dimensions)

        for i, v in enumerate(vertices):
            vertices[i] = (v - center) * scale

        # generate mesh lists
        for a, b, c in triangles:
            va, vb, vc = a[0], b[0], c[0]
            mesh.vertices.extend(vertices[v] for v in (va, vb, vc))
            if colors:
                mesh.colors.extend(colors[v] for v in (va, vb, vc))
            if len(a) >= 2 and a[1] != -1:
                mesh.uv.extend(uvs[i] for i in (a[1], b[1], c[1]))
            if len(a) >= 3 and a[2] != -1:
                mesh.normals.extend(normals[i] for i in (a[2], b[2], c[2]))

        texture = None
        if not mesh.uv:
            mesh.uv = [0, 0] * len(triangles)
        elif tex_path is not None:
            mesh.uv = list(flatten(mesh.uv))
            ext = '.' + tex_path.split('.')[-1]
            texture = tempfile.NamedTemporaryFile(suffix=ext)
            mesh.texture_path = texture.name
            shutil.copy(tex_path, texture.name)

        if not mesh.colors:
            mesh.colors = [1, 1, 1, 1] * len(mesh.vertices)

        obj_vertices = mesh.vertices
        mesh.triangles = list(range(len(obj_vertices)))
        mesh.normals = list(flatten(mesh.normals))
        mesh.vertices = list(flatten(mesh.vertices))

        # create empty complex to anchor
        complex = Complex()
        complex.name = name

        obj = OBJ(complex, mesh, obj_vertices, texture, min_bounds, max_bounds)
        self.objs.append(obj)
        self.scale_obj(obj, 10.0)

        res = await self.plugin.add_to_workspace([complex])
        obj.complex.index = res[0].index

        # anchor mesh to complex
        anchor = mesh.anchors[0]
        anchor.anchor_type = ShapeAnchorType.Complex
        anchor.target = obj.complex.index

        await mesh.upload()
        self.show_list()

    def scale_obj(self, obj: OBJ, scale: float):
        complex = obj.complex
        mesh = obj.mesh
        obj.scale = scale

        vertices = [v * scale for v in obj.vertices]
        mesh.vertices = list(flatten(vertices))

        min_bounds = Vector3(inf, inf, inf)
        max_bounds = Vector3(-inf, -inf, -inf)
        for vertex in vertices:
            min_bounds.set(*map(min, zip(vertex, min_bounds)))
            max_bounds.set(*map(max, zip(vertex, max_bounds)))

        for molecule in complex.molecules:
            complex.remove_molecule(molecule)

        molecule = Molecule()
        chain = Chain()
        residue = Residue()

        complex.add_molecule(molecule)
        molecule.add_chain(chain)
        chain.add_residue(residue)

        # add atoms to bounding box to make grabbable
        for x in range(2):
            for y in range(2):
                for z in range(2):
                    atom = Atom()
                    atom.set_visible(False)
                    atom.position.x = [min_bounds, max_bounds][x].x
                    atom.position.y = [min_bounds, max_bounds][y].y
                    atom.position.z = [min_bounds, max_bounds][z].z
                    residue.add_atom(atom)
