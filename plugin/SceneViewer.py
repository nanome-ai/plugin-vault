import asyncio
import os
from functools import partial

import nanome
from nanome import ui
from nanome.api.structure import Complex, Workspace
from nanome.util import async_callback
from nanome.util.enums import NotificationTypes

from . import WorkspaceSerializer
from .WorkspaceSerializer import Scene

BASE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'menus')
MENU_PATH = os.path.join(BASE_DIR, 'json/scenes_menu.json')
SCENE_INFO_PATH = os.path.join(BASE_DIR, 'json/scene_info.json')
SCENE_ITEM_PATH = os.path.join(BASE_DIR, 'json/scene_item.json')
ICON_ADD = os.path.join(BASE_DIR, 'icons/add.png')
ICON_COPY = os.path.join(BASE_DIR, 'icons/copy.png')
ICON_DELETE = os.path.join(BASE_DIR, 'icons/delete.png')
ICON_DOWN = os.path.join(BASE_DIR, 'icons/down.png')
ICON_EDIT = os.path.join(BASE_DIR, 'icons/edit.png')
ICON_FIRST = os.path.join(BASE_DIR, 'icons/first.png')
ICON_LAST = os.path.join(BASE_DIR, 'icons/last.png')
ICON_NEW = os.path.join(BASE_DIR, 'icons/new.png')
ICON_NEXT = os.path.join(BASE_DIR, 'icons/next.png')
ICON_PASTE = os.path.join(BASE_DIR, 'icons/paste.png')
ICON_PREV = os.path.join(BASE_DIR, 'icons/prev.png')
ICON_SAVE = os.path.join(BASE_DIR, 'icons/save.png')
ICON_UP = os.path.join(BASE_DIR, 'icons/up.png')
ICON_UPDATE = os.path.join(BASE_DIR, 'icons/update.png')
ICON_VIEW = os.path.join(BASE_DIR, 'icons/view.png')

CONFIRM_CHANGE_SCENE = 'Change active scene?\nUnsaved scene changes will be lost.'
CONFIRM_DELETE_SCENE = 'Delete this scene?'
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
        self.scene_changes = False

        self.create_menu()
        self.create_scene_menu()
        self.update_scenes()
        self.toggle_edit_mode(True)

    def create_menu(self):
        self.menu = ui.Menu.io.from_json(MENU_PATH)
        self.menu.index = 2
        root: ui.LayoutNode = self.menu.root

        self.pfb_scene_item = ui.LayoutNode.io.from_json(SCENE_ITEM_PATH)

        self.ln_scenes: ui.LayoutNode = root.find_node('Scenes')
        self.ln_save: ui.LayoutNode = root.find_node('Save')

        self.ln_confirm: ui.LayoutNode = root.find_node('Confirm Prompt')
        self.lbl_confirm: ui.Label = root.find_node('Label Confirm').get_content()

        self.btn_confirm_cancel: ui.Button = root.find_node('Button Confirm Cancel').get_content()
        self.btn_confirm_cancel.register_pressed_callback(self.confirm_cancel)

        self.btn_confirm_continue: ui.Button = root.find_node('Button Confirm Continue').get_content()
        self.btn_confirm_continue.register_pressed_callback(self.confirm_continue)

        ln_list: ui.LayoutNode = root.find_node('Scene List')
        self.lst_scenes: ui.UIList = ln_list.get_content()

        self.ln_btns_edit: ui.LayoutNode = root.find_node('Buttons Edit')

        self.ln_btn_edit: ui.LayoutNode = root.find_node('Button Edit')
        btn_edit: ui.Button = self.ln_btn_edit.get_content()
        btn_edit.register_pressed_callback(partial(self.toggle_edit_mode, True))
        btn_edit.icon.value.set_all(ICON_EDIT)

        self.ln_btn_view: ui.LayoutNode = root.find_node('Button View')
        btn_view: ui.Button = self.ln_btn_view.get_content()
        btn_view.register_pressed_callback(partial(self.toggle_edit_mode, False))
        btn_view.icon.value.set_all(ICON_VIEW)

        btn_first: ui.Button = root.find_node('Button First').get_content()
        btn_first.register_pressed_callback(partial(self.select_scene, 0))
        btn_first.icon.value.set_all(ICON_FIRST)

        btn_prev: ui.Button = root.find_node('Button Previous').get_content()
        btn_prev.register_pressed_callback(partial(self.select_adjacent_scene, -1))
        btn_prev.icon.value.set_all(ICON_PREV)

        btn_next: ui.Button = root.find_node('Button Next').get_content()
        btn_next.register_pressed_callback(partial(self.select_adjacent_scene, 1))
        btn_next.icon.value.set_all(ICON_NEXT)

        btn_last: ui.Button = root.find_node('Button Last').get_content()
        btn_last.register_pressed_callback(partial(self.select_scene, -1))
        btn_last.icon.value.set_all(ICON_LAST)

        btn_add: ui.Button = root.find_node('Button Add').get_content()
        btn_add.register_pressed_callback(self.add_scene)
        btn_add.icon.value.set_all(ICON_ADD)
        btn_add.disable_on_press = True

        btn_delete: ui.Button = root.find_node('Button Delete').get_content()
        btn_delete.register_pressed_callback(self.delete_scene)
        btn_delete.icon.value.set_all(ICON_DELETE)
        btn_delete.disable_on_press = True

        btn_copy: ui.Button = root.find_node('Button Copy').get_content()
        btn_copy.register_pressed_callback(self.copy_selection)
        btn_copy.icon.value.set_each(default=ICON_COPY, selected=ICON_PASTE)
        btn_copy.disable_on_press = True
        btn_copy.toggle_on_press = True

        btn_update: ui.Button = root.find_node('Button Update').get_content()
        btn_update.register_pressed_callback(self.update_scene)
        btn_update.icon.value.set_all(ICON_UPDATE)
        btn_update.disable_on_press = True

        btn_save: ui.Button = root.find_node('Button Save').get_content()
        btn_save.register_pressed_callback(partial(self.toggle_save, True))
        btn_save.icon.value.set_all(ICON_SAVE)

        btn_new: ui.Button = root.find_node('Button New').get_content()
        btn_new.register_pressed_callback(self.reset)
        btn_new.icon.value.set_all(ICON_NEW)

        inp_scenes_name: ui.TextInput = root.find_node('Input Scenes Name').get_content()

        btn_save_cancel: ui.Button = root.find_node('Button Save Cancel').get_content()
        btn_save_cancel.register_pressed_callback(partial(self.toggle_save, False))
        btn_save_cancel.disable_on_press = True

        btn_save_continue: ui.Button = root.find_node('Button Save Continue').get_content()
        btn_save_continue.register_pressed_callback(self.save)
        btn_save_continue.disable_on_press = True

        self.btn_delete = btn_delete
        self.btn_update = btn_update
        self.inp_scenes_name = inp_scenes_name
        self.btn_save_cancel = btn_save_cancel
        self.btn_save_continue = btn_save_continue

    def create_scene_menu(self):
        self.menu_scene = ui.Menu.io.from_json(SCENE_INFO_PATH)
        self.menu_scene.index = 3
        root: ui.LayoutNode = self.menu_scene.root

        self.ln_info_view: ui.LayoutNode = root.find_node('Info View')
        self.ln_info_edit: ui.LayoutNode = root.find_node('Info Edit')

        self.lbl_scene_name: ui.Label = root.find_node('Label Name').get_content()
        self.lbl_scene_description: ui.Label = root.find_node('Label Description').get_content()

        self.inp_scene_name: ui.TextInput = root.find_node('Input Name').get_content()
        self.inp_scene_name.register_changed_callback(self.update_scene_name)
        self.inp_scene_description: ui.TextInput = root.find_node('Input Description').get_content()
        self.inp_scene_description.register_changed_callback(self.update_scene_description)

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
        self.lst_scenes.display_rows = 5 if self.edit_mode else 6
        self.lst_scenes.items.clear()

        for i, scene in enumerate(self.scenes):
            ln_item: ui.LayoutNode = self.pfb_scene_item.clone()

            btn: ui.Button = ln_item.get_content()
            btn.register_pressed_callback(partial(self.select_scene, i))

            lbl: ui.Label = ln_item.find_node('Label').get_content()
            lbl.text_value = scene.name or f'Scene {i + 1}'

            btn_up: ui.Button = ln_item.find_node('Button Move Up').get_content()
            btn_up.register_pressed_callback(partial(self.move_scene, i, -1))
            btn_up.icon.value.set_all(ICON_UP)
            btn_up.disable_on_press = True
            btn_up.unusable = i == 0

            btn_down: ui.Button = ln_item.find_node('Button Move Down').get_content()
            btn_down.register_pressed_callback(partial(self.move_scene, i, 1))
            btn_down.icon.value.set_all(ICON_DOWN)
            btn_down.disable_on_press = True
            btn_down.unusable = i == len(self.scenes) - 1

            ln_btns_move: ui.LayoutNode = ln_item.find_node('Buttons Move')
            ln_btns_move.enabled = self.edit_mode

            self.lst_scenes.items.append(ln_item)

        if not self.lst_scenes.items:
            ln_item: ui.LayoutNode = ui.LayoutNode()
            lbl: ui.Label = ln_item.add_new_label('No scenes yet')
            lbl.text_horizontal_align = lbl.HorizAlignOptions.Middle
            lbl.text_vertical_align = lbl.VertAlignOptions.Middle
            lbl.text_auto_size = False
            lbl.text_size = 0.5
            self.lst_scenes.items.append(ln_item)

        if self.scenes:
            self.lst_scenes.items[self.selected_index].get_content().selected = True

        self.plugin.update_content(self.lst_scenes)

    @async_callback
    async def add_scene(self, btn=None):
        workspace = await self.plugin.request_workspace()
        scene = Scene(workspace)
        index = self.selected_index + 1
        self.scenes.insert(index, scene)
        self.update_scenes()
        self.select_scene(min(index, len(self.scenes) - 1))

        self.plugin.update_content(btn)
        self.set_saved(False)
        self.update_controls()

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

        self.update_scenes()
        self.plugin.update_content(btn)
        self.set_saved(False)
        self.update_controls()

    def load(self, filename, scenes: 'list[Scene]'):
        self.scenes = scenes
        self.selected_index = 0
        name = filename.replace('.nanoscenes', '')
        self.inp_scenes_name.input_text = name
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
        if not self.edit_mode:
            return
        self.scene_changes = True
        self.set_saved(False)

    def reset(self, btn=None):
        if not self.pending_action:
            self.confirm(CONFIRM_RESET, self.reset)
            return

        self.scenes.clear()
        self.selected_index = 0
        self.inp_scenes_name.input_text = ''
        self.menu.title = 'Scene Viewer'
        self.set_saved(True)
        self.update_scenes()
        self.update_controls()
        self.open_menu()

        self.menu_scene.enabled = False
        self.plugin.update_menu(self.menu_scene)

    @async_callback
    async def save(self, btn=None):
        name = self.inp_scenes_name.input_text

        if not name:
            self.plugin.send_notification(NotificationTypes.error, 'Please enter a name')
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

        self.lst_scenes.items[self.selected_index].get_content().selected = False
        self.selected_index = index
        self.lst_scenes.items[index].get_content().selected = True
        self.plugin.update_content(self.lst_scenes)

        # clear workspace first to fix a bug where structure color doesn't update
        scene = self.scenes[index]
        self.plugin.update_workspace(Workspace())
        self.plugin.update_workspace(scene.workspace)

        self.lbl_scene_name.text_value = scene.name or f'Scene {index + 1}'
        self.lbl_scene_description.text_value = scene.description or 'No description'
        self.inp_scene_name.input_text = scene.name
        self.inp_scene_description.input_text = scene.description
        self.plugin.update_menu(self.menu_scene)

        complexes = await self.plugin.request_complex_list()
        for complex in complexes:
            complex.register_complex_updated_callback(self.on_scene_changed)
            complex.register_selection_changed_callback(self.on_scene_changed)

        self.scene_changes = False
        self.open_scene_menu()

    def set_saved(self, saved):
        self.saved = saved
        shows_unsaved = self.menu.title[-1] == '*'

        if saved and shows_unsaved:
            self.menu.title = self.menu.title[:-1]
        elif not saved and not shows_unsaved:
            self.menu.title += '*'
        if saved == shows_unsaved and self.menu.enabled:
            self.plugin.update_menu(self.menu)

    def toggle_edit_mode(self, edit_mode, btn=None):
        self.edit_mode = edit_mode

        self.ln_btn_edit.enabled = not edit_mode
        self.ln_btn_view.enabled = edit_mode
        self.ln_btns_edit.enabled = edit_mode
        self.plugin.update_node(self.ln_btn_edit, self.ln_btn_view, self.ln_btns_edit)

        self.ln_info_view.enabled = not edit_mode
        self.ln_info_edit.enabled = edit_mode

        if self.scenes:
            scene = self.scenes[self.selected_index]
            self.lbl_scene_name.text_value = scene.name or f'Scene {self.selected_index + 1}'
            self.lbl_scene_description.text_value = scene.description or 'No description'

        self.plugin.update_node(self.ln_info_view, self.ln_info_edit)

        self.update_scenes()
        self.update_controls()

    def toggle_save(self, value, btn=None):
        self.ln_scenes.enabled = not value
        self.ln_save.enabled = value
        self.plugin.update_node(self.ln_scenes, self.ln_save)

    def update_controls(self):
        no_scenes = not self.scenes
        should_update = self.btn_delete.unusable != no_scenes

        if not should_update:
            return

        self.btn_delete.unusable = no_scenes
        self.btn_update.unusable = no_scenes
        self.plugin.update_content(self.btn_delete, self.btn_update)

    @async_callback
    async def update_scene(self, btn=None):
        workspace = await self.plugin.request_workspace()
        self.scenes[self.selected_index].workspace = workspace
        self.plugin.update_content(btn)
        self.set_saved(False)
        self.scene_changes = False

    def update_scene_name(self, inp=None):
        self.scenes[self.selected_index].name = inp.input_text
        self.update_scenes()
        self.set_saved(False)

    def update_scene_description(self, inp=None):
        self.scenes[self.selected_index].description = inp.input_text
        self.set_saved(False)
