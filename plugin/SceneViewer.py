import asyncio
import itertools
import nanome
import os
from functools import partial
from nanome import ui
from nanome.api.interactions import Interaction
from nanome.api.structure import Complex, Workspace
from nanome.util import async_callback, Logs
from nanome.util.enums import NotificationTypes

from . import WorkspaceSerializer
from .WorkspaceSerializer import Scene

BASE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'menus')
MENU_PATH = os.path.join(BASE_DIR, 'json/scenes_menu.json')
SCENE_INFO_PATH = os.path.join(BASE_DIR, 'json/scene_info.json')
SCENE_ITEM_PATH = os.path.join(BASE_DIR, 'json/scene_item.json')
ICON_ADD = os.path.join(BASE_DIR, 'icons/add.png')
ICON_COPY = os.path.join(BASE_DIR, 'icons/copy.png')
ICON_DECK = os.path.join(BASE_DIR, 'icons/deck.png')
ICON_DELETE = os.path.join(BASE_DIR, 'icons/delete.png')
ICON_FIRST = os.path.join(BASE_DIR, 'icons/first.png')
ICON_INFO = os.path.join(BASE_DIR, 'icons/info.png')
ICON_LAST = os.path.join(BASE_DIR, 'icons/last.png')
ICON_NEXT = os.path.join(BASE_DIR, 'icons/next.png')
ICON_PREV = os.path.join(BASE_DIR, 'icons/prev.png')
ICON_SAVE = os.path.join(BASE_DIR, 'icons/save.png')
ICON_UP = os.path.join(BASE_DIR, 'icons/up.png')
ICON_UPDATE = os.path.join(BASE_DIR, 'icons/update.png')

CONFIRM_CHANGE_SCENE = 'Change active scene?\nUnsaved scene changes will be lost.'
CONFIRM_DELETE_SCENE = 'Delete this scene?\nThis action cannot be undone.'
CONFIRM_RESET = 'Create new scene deck?\nUnsaved deck changes will be lost.'


class SaveRequest:
    def __init__(self, name, scenes: 'list[Scene]'):
        self.name = name
        self.data = WorkspaceSerializer.scenes_to_data(scenes)
        loop = asyncio.get_event_loop()
        self.future = loop.create_future()

    def get_args(self):
        return ('Browse', self.name, self.data)

    def send_response(self, response):
        self.future.set_result(response)


class SceneViewer:
    def __init__(self, plugin: nanome.PluginInstance):
        self.plugin = plugin
        self.scenes: list[Scene] = []
        self.clipboard: list[Complex] = []

        self.pending_action = None
        self.edit_mode = False
        self.selected_index = 0
        self.saved = True
        self.ignore_changes = 0
        self.scene_changes = False

        self.create_menu()
        self.create_scene_menu()
        self.update_scenes()
        self.toggle_edit_mode(True)

    def create_menu(self):
        self.menu = ui.Menu.io.from_json(MENU_PATH)
        self.menu.index = 2
        self.menu.enabled = False
        root: ui.LayoutNode = self.menu.root

        self.pfb_scene_item = ui.LayoutNode.io.from_json(SCENE_ITEM_PATH)

        # No Scenes
        self.ln_no_scenes: ui.LayoutNode = root.find_node('No Scenes')
        btn_create_new: ui.Button = self.ln_no_scenes.find_node('Button Create New').get_content()
        btn_create_new.register_pressed_callback(self.add_scene)
        btn_create_new.icon.value.set_all(ICON_ADD)

        img_note: ui.Image = self.ln_no_scenes.find_node('Icon Note').get_content()
        img_note.file_path = ICON_INFO
        img_no_scenes: ui.Image = self.ln_no_scenes.find_node('Icon No Scenes').get_content()
        img_no_scenes.file_path = ICON_DECK

        # Scenes
        self.ln_scenes: ui.LayoutNode = root.find_node('Scenes')

        self.ln_list: ui.LayoutNode = self.ln_scenes.find_node('Scene List')
        self.lst_scenes: ui.UIList = self.ln_list.get_content()

        self.ln_top_bar: ui.LayoutNode = self.ln_scenes.find_node('Top Bar')
        self.ln_bottom_bar: ui.LayoutNode = self.ln_scenes.find_node('Bottom Bar')
        self.ln_btns_edit: ui.LayoutNode = self.ln_scenes.find_node('Buttons Edit')
        self.ln_btns_view: ui.LayoutNode = self.ln_scenes.find_node('Buttons View')

        ln_btn_edit: ui.LayoutNode = self.ln_scenes.find_node('Button Toggle Edit')
        ln_btn_edit.set_padding(top=0.03, down=0.03, left=0.01, right=0.01)
        self.btn_edit: ui.Button = ln_btn_edit.add_new_toggle_switch('Edit Mode')
        self.btn_edit.register_pressed_callback(partial(self.toggle_edit_mode, None))

        btn_copy: ui.Button = self.ln_btns_edit.find_node('Button Copy').get_content()
        btn_copy.register_pressed_callback(self.copy_selection)
        btn_copy.icon.value.set_all(ICON_COPY)
        btn_copy.disable_on_press = True
        btn_copy.toggle_on_press = True

        btn_add: ui.Button = self.ln_btns_edit.find_node('Button Add').get_content()
        btn_add.register_pressed_callback(self.add_scene)
        btn_add.icon.value.set_all(ICON_ADD)
        btn_add.disable_on_press = True

        btn_new: ui.Button = self.ln_btns_edit.find_node('Button New').get_content()
        btn_new.register_pressed_callback(self.reset)
        btn_new.icon.value.set_all(ICON_ADD)

        self.ln_btn_save: ui.LayoutNode = self.ln_bottom_bar.find_node('Button Save')
        btn_save: ui.Button = self.ln_btn_save.get_content()
        btn_save.register_pressed_callback(partial(self.toggle_save, True))
        btn_save.icon.value.set_all(ICON_SAVE)

        btn_info: ui.Button = self.ln_btns_view.find_node('Button Info').get_content()
        btn_info.register_pressed_callback(self.toggle_scene_info)
        btn_info.icon.value.set_all(ICON_INFO)

        self.ln_btns_controls: ui.LayoutNode = self.ln_scenes.find_node('Buttons Controls')

        btn_first: ui.Button = self.ln_scenes.find_node('Button First').get_content()
        btn_first.register_pressed_callback(partial(self.select_scene, 0))
        btn_first.icon.value.set_all(ICON_FIRST)

        btn_prev: ui.Button = self.ln_scenes.find_node('Button Previous').get_content()
        btn_prev.register_pressed_callback(partial(self.select_adjacent_scene, -1))
        btn_prev.icon.value.set_all(ICON_PREV)

        btn_next: ui.Button = self.ln_scenes.find_node('Button Next').get_content()
        btn_next.register_pressed_callback(partial(self.select_adjacent_scene, 1))
        btn_next.icon.value.set_all(ICON_NEXT)

        btn_last: ui.Button = self.ln_scenes.find_node('Button Last').get_content()
        btn_last.register_pressed_callback(partial(self.select_scene, -1))
        btn_last.icon.value.set_all(ICON_LAST)

        # Confirm Prompt
        self.ln_confirm: ui.LayoutNode = root.find_node('Confirm Prompt')
        self.ln_confirm.forward_dist = 0.01
        self.lbl_confirm: ui.Label = self.ln_confirm.find_node('Text').get_content()

        btn_confirm_cancel: ui.Button = self.ln_confirm.find_node('Button Cancel').get_content()
        btn_confirm_cancel.register_pressed_callback(self.confirm_cancel)

        btn_confirm_continue: ui.Button = self.ln_confirm.find_node('Button Continue').get_content()
        btn_confirm_continue.register_pressed_callback(self.confirm_continue)

        # Save Prompt
        self.ln_save: ui.LayoutNode = root.find_node('Save Deck')

        self.inp_deck_name: ui.TextInput = self.ln_save.find_node('Input Name').get_content()

        btn_save_cancel: ui.Button = self.ln_save.find_node('Button Cancel').get_content()
        btn_save_cancel.register_pressed_callback(partial(self.toggle_save, False))
        btn_save_cancel.disable_on_press = True

        btn_save_continue: ui.Button = self.ln_save.find_node('Button Save').get_content()
        btn_save_continue.register_pressed_callback(self.save)
        btn_save_continue.disable_on_press = True

        # Scene Info
        self.ln_info: ui.LayoutNode = root.find_node('Scene Info')

        self.inp_scene_name: ui.TextInput = self.ln_info.find_node('Input Name').get_content()
        self.inp_scene_desc: ui.TextInput = self.ln_info.find_node('Input Description').get_content()
        self.inp_scene_desc.register_changed_callback(self.update_scene_desc_len)
        self.lbl_scene_desc_len: ui.Label = self.ln_info.find_node('Label Description Length').get_content()

        btn_info_cancel: ui.Button = self.ln_info.find_node('Button Cancel').get_content()
        btn_info_cancel.register_pressed_callback(self.toggle_scene_info)

        btn_info_update: ui.Button = self.ln_info.find_node('Button Update').get_content()
        btn_info_update.register_pressed_callback(self.save_scene_info)

    def create_scene_menu(self):
        self.menu_scene = ui.Menu.io.from_json(SCENE_INFO_PATH)
        self.menu_scene.index = 3
        self.menu_scene.enabled = False
        root: ui.LayoutNode = self.menu_scene.root

        self.ln_info_view: ui.LayoutNode = root.find_node('Info View')
        self.ln_info_edit: ui.LayoutNode = root.find_node('Info Edit')

        self.lbl_scene_name: ui.Label = root.find_node('Label Name').get_content()
        self.lbl_scene_desc: ui.Label = root.find_node('Label Description').get_content()

    def open_menu(self):
        self.menu.enabled = True
        self.plugin.update_menu(self.menu)

    def open_scene_menu(self):
        self.menu_scene.enabled = True
        self.plugin.update_menu(self.menu_scene)

    def confirm(self, msg, action):
        self.ln_confirm.enabled = True
        self.lbl_confirm.text_value = msg
        self.pending_action = action
        self.plugin.update_node(self.ln_confirm)

    def confirm_cancel(self, btn):
        self.ln_confirm.enabled = False
        self.pending_action = None
        self.plugin.update_node(self.ln_confirm)

    def confirm_continue(self, btn):
        self.ln_confirm.enabled = False
        self.pending_action()
        self.pending_action = None
        self.plugin.update_node(self.ln_confirm)

    def update_scenes(self):
        if not self.scenes:
            self.ln_no_scenes.enabled = True
            self.ln_scenes.enabled = False
            self.plugin.update_node(self.ln_no_scenes, self.ln_scenes)
            return

        self.lst_scenes.items.clear()

        for i, scene in enumerate(self.scenes):
            is_selected = i == self.selected_index
            ln_item: ui.LayoutNode = self.pfb_scene_item.clone()

            btn: ui.Button = ln_item.find_node('Button Scene').get_content()
            btn.register_pressed_callback(partial(self.select_scene, i))
            btn.text.value.set_all(scene.name or f'Scene {i + 1}')
            btn.selected = is_selected

            ln_btns_edit: ui.LayoutNode = ln_item.find_node('Buttons Edit')
            ln_btns_edit.enabled = self.edit_mode and is_selected

            ln_btns_move: ui.LayoutNode = ln_item.find_node('Buttons Move')
            ln_btns_move.enabled = self.edit_mode and is_selected

            btn_update: ui.Button = ln_btns_edit.find_node('Button Update').get_content()
            btn_update.register_pressed_callback(self.update_scene)
            btn_update.icon.value.set_all(ICON_UPDATE)
            btn_update.disable_on_press = True

            btn_notes: ui.Button = ln_btns_edit.find_node('Button Notes').get_content()
            btn_notes.register_pressed_callback(self.toggle_scene_info)
            btn_notes.icon.value.set_all(ICON_INFO)

            btn_delete: ui.Button = ln_btns_edit.find_node('Button Delete').get_content()
            btn_delete.register_pressed_callback(self.delete_scene)
            btn_delete.icon.value.set_all(ICON_DELETE)

            btn_up: ui.Button = ln_btns_move.find_node('Button Move Up').get_content()
            btn_up.register_pressed_callback(partial(self.move_scene, i, -1))
            btn_up.icon.value.set_all(ICON_UP)
            btn_up.disable_on_press = True
            btn_up.unusable = i == 0

            btn_down: ui.Button = ln_btns_move.find_node('Button Move Down').get_content()
            btn_down.register_pressed_callback(partial(self.move_scene, i, 1))
            btn_down.icon.value.set_all(ICON_UP)
            btn_down.disable_on_press = True
            btn_down.unusable = i == len(self.scenes) - 1

            self.lst_scenes.items.append(ln_item)

        if self.ln_no_scenes.enabled:
            self.ln_no_scenes.enabled = False
            self.ln_scenes.enabled = True
            self.plugin.update_node(self.ln_no_scenes, self.ln_scenes)
        else:
            self.plugin.update_content(self.lst_scenes)

    @async_callback
    async def add_scene(self, btn=None):
        workspace = await self.plugin.request_workspace()
        interactions = await Interaction.get()
        scene = Scene(workspace, interactions=interactions)
        index = self.selected_index + 1
        self.scenes.insert(index, scene)
        # self.update_scenes()
        self.select_scene(min(index, len(self.scenes) - 1))

        self.plugin.update_content(btn)
        self.set_saved(False)

    @async_callback
    async def copy_selection(self, btn: ui.Button):
        workspace = await self.plugin.request_workspace()

        if btn.selected:
            self.clipboard = [c for c in workspace.complexes if c.get_selected()]

            if not self.clipboard:
                btn.selected = False
                self.plugin.update_content(btn)
                return

            btn.tooltip.title = 'paste selection'

        else:
            for c in self.clipboard:
                workspace.add_complex(c)

            self.plugin.update_workspace(Workspace())
            self.plugin.update_workspace(workspace)
            btn.tooltip.title = 'copy selection'
            btn.selected = False
            self.on_scene_changed()

        self.plugin.update_content(btn)

    def delete_scene(self, btn=None):
        if not self.pending_action:
            action = partial(self.delete_scene, btn)
            self.confirm(CONFIRM_DELETE_SCENE, action)
            return

        del self.scenes[self.selected_index]
        self.selected_index = max(0, self.selected_index - 1)
        self.select_scene(self.selected_index)

        # self.update_scenes()
        self.plugin.update_content(btn)
        self.set_saved(False)

    def load(self, filename, scenes: 'list[Scene]'):
        self.scenes = scenes
        self.selected_index = 0

        name = filename.replace('.nanoscenes', '')
        self.inp_deck_name.input_text = name
        self.menu.title = f'Scene Viewer - {name}'

        self.set_saved(True)
        self.toggle_edit_mode(False)
        self.update_scenes()
        self.open_menu()

    def move_scene(self, index, offset, btn=None):
        self.scenes.insert(index + offset, self.scenes.pop(index))
        new_index = index + offset

        if self.selected_index != index:
            self.select_scene(new_index)

        self.selected_index = new_index
        self.update_scenes()
        self.set_saved(False)

    def on_scene_changed(self, *_):
        if not self.edit_mode or self.ignore_changes:
            return
        self.scene_changes = True
        self.set_saved(False)

    def reset(self, btn=None):
        if not self.pending_action:
            self.confirm(CONFIRM_RESET, self.reset)
            return

        self.scenes.clear()
        self.selected_index = 0
        self.inp_deck_name.input_text = ''
        self.menu.title = 'Scene Viewer'
        self.set_saved(True)
        self.update_scenes()
        self.update_scene_info()
        self.open_menu()

    @async_callback
    async def save(self, btn=None):
        name = self.inp_deck_name.input_text

        if not name:
            self.plugin.send_notification(NotificationTypes.error, 'Please enter a name')
            self.plugin.update_content(btn)
            return

        filename = f'{name}.nanoscenes'
        request = SaveRequest(filename, self.scenes)
        self.plugin.on_export_integration(request)
        response = await request.future

        if response:
            self.plugin.send_notification(NotificationTypes.success, f'"{filename}" saved')
            self.menu.title = f'Scene Viewer - {name}*'
            self.set_saved(True)
            self.toggle_save(False)

    def save_scene_info(self, btn=None):
        scene = self.scenes[self.selected_index]
        scene.name = self.inp_scene_name.input_text
        scene.description = self.inp_scene_desc.input_text

        self.ln_info.enabled = False
        self.plugin.update_node(self.ln_info)

        self.update_scenes()
        self.update_scene_info()
        self.set_saved(False)

    def select_adjacent_scene(self, offset, btn=None):
        if not self.scenes:
            return

        if btn is not None and self.edit_mode and self.scene_changes:
            action = partial(self.select_adjacent_scene, offset)
            self.confirm(CONFIRM_CHANGE_SCENE, action)
            return

        index = (self.selected_index + offset) % len(self.scenes)
        self.select_scene(index)

    @async_callback
    async def select_scene(self, index, btn=None):
        if not self.scenes:
            return

        if btn is not None and self.edit_mode and self.scene_changes:
            action = partial(self.select_scene, index)
            self.confirm(CONFIRM_CHANGE_SCENE, action)
            return

        if index < 0:
            index = len(self.scenes) + index

        self.selected_index = index
        self.update_scenes()
        self.update_scene_info()

        # clear workspace first to fix a bug where structure color doesn't update
        scene = self.scenes[index]
        self.ignore_changes += 1
        self.plugin.update_workspace(Workspace())
        current_interactions = await Interaction.get()
        if current_interactions:
            Interaction.destroy_multiple(current_interactions)
        self.plugin.update_workspace(scene.workspace)
        await asyncio.sleep(1)
        shallow_comps = await self.plugin.request_complex_list()
        updated_complexes = await self.plugin.request_complexes([cmp.index for cmp in shallow_comps])
        if scene.interactions:
            updated_interactions = self.update_interaction_lines(scene.interactions, scene.workspace.complexes, updated_complexes)
            await Interaction.upload_multiple(updated_interactions)
            # Update scene with new interactions and complexes.
            scene.interactions = updated_interactions
            scene.workspace.complexes = updated_complexes

        for complex in updated_complexes:
            complex.register_complex_updated_callback(self.on_scene_changed)
            complex.register_selection_changed_callback(self.on_scene_changed)

        # ignore updates 2 seconds after scene change
        await asyncio.sleep(2)
        self.ignore_changes -= 1

    def set_saved(self, saved):
        self.saved = saved
        shows_unsaved = self.menu.title[-1] == '*'

        if saved and shows_unsaved:
            self.menu.title = self.menu.title[:-1]
        elif not saved and not shows_unsaved:
            self.menu.title += '*'
        if saved == shows_unsaved and self.menu.enabled:
            self.plugin.update_menu(self.menu)

    def toggle_edit_mode(self, edit_mode=None, btn=None):
        self.edit_mode = edit_mode if btn is None else btn.selected

        self.btn_edit.selected = self.edit_mode
        self.ln_btns_view.enabled = not self.edit_mode
        self.ln_btns_controls.enabled = not self.edit_mode
        self.ln_btns_edit.enabled = self.edit_mode
        self.ln_btn_save.enabled = self.edit_mode
        self.plugin.update_node(self.ln_top_bar, self.ln_bottom_bar)

        self.update_scenes()

    def toggle_scene_info(self, btn=None):
        if self.edit_mode:
            self.ln_info.enabled = not self.ln_info.enabled
            self.plugin.update_node(self.ln_info)
        else:
            self.menu_scene.enabled = True
            self.plugin.update_menu(self.menu_scene)

    def toggle_save(self, value, btn=None):
        # self.ln_scenes.enabled = not value
        self.ln_save.enabled = value
        self.plugin.update_node(self.ln_scenes, self.ln_save)

    @async_callback
    async def update_scene(self, btn=None):
        workspace = await self.plugin.request_workspace()
        self.scenes[self.selected_index].workspace = workspace
        self.plugin.update_content(btn)
        self.set_saved(False)
        self.scene_changes = False

    def update_scene_desc_len(self, inp=None):
        self.lbl_scene_desc_len.text_value = f'{len(self.inp_scene_desc.input_text)}/500'
        self.plugin.update_content(self.lbl_scene_desc_len)

    def update_scene_info(self):
        name = 'No scenes'
        desc = 'Add a new scene or load a Scene Deck to get started'

        if self.scenes:
            scene = self.scenes[self.selected_index]
            name = scene.name
            desc = scene.description

        self.inp_scene_name.input_text = name
        self.inp_scene_desc.input_text = desc
        self.lbl_scene_name.text_value = name or f'Scene {self.selected_index + 1}'
        self.lbl_scene_desc.text_value = desc or 'No description'

        self.plugin.update_content(self.inp_scene_name, self.inp_scene_desc)
        self.plugin.update_content(self.lbl_scene_name, self.lbl_scene_desc)
        self.update_scene_desc_len()

    @staticmethod
    def update_interaction_lines(interaction_list, original_complexes, updated_complexes):
        """Update atom indices in interactions to reflect the updated complexes.

        This is a workaround for the fact that atom indices change every time a workspace
        is reloaded into the room.
        """
        updated_interactions = []
        atom_index_map = {}
        og_atoms = itertools.chain(*[cmp.atoms for cmp in original_complexes])
        updated_atoms = itertools.chain(*[cmp.atoms for cmp in updated_complexes])
        # We are making the assumption that the og complex and updated complex
        # are the same, so we can just zip the atoms together and they align.
        for og_atom, updated_atom in zip(og_atoms, updated_atoms):
            atom_index_map[og_atom.index] = updated_atom.index
        for interaction in interaction_list:
            try:
                interaction.atom1_idx_arr = tuple(map(lambda x: atom_index_map[x], interaction.atom1_idx_arr))
                interaction.atom2_idx_arr = tuple(map(lambda x: atom_index_map[x], interaction.atom2_idx_arr))
            except Exception:
                Logs.errror("Updating interaction lines failed =(.")
                return
            interaction.index = -1
            updated_interactions.append(interaction)
        return updated_interactions
