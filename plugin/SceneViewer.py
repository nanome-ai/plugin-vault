import asyncio
import os
from functools import partial

import nanome
from nanome import ui
from nanome.api.structure import Complex, Workspace
from nanome.util import async_callback
from nanome.util.enums import NotificationTypes

from . import WorkspaceSerializer

BASE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'menus')
MENU_PATH = os.path.join(BASE_DIR, 'json/scenes_menu.json')
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


class SaveRequest:
    def __init__(self, name, scenes: 'list[Workspace]'):
        self.name = name
        self.data = WorkspaceSerializer.list_to_data(scenes)
        loop = asyncio.get_event_loop()
        self.future = loop.create_future()

    def get_args(self):
        return ('Browse', self.name, self.data)

    def send_response(self, response):
        self.future.set_result(response)


class SceneViewer:
    def __init__(self, plugin: nanome.PluginInstance):
        self.plugin = plugin
        self.scenes: list[Workspace] = []
        self.clipboard: list[Complex] = []
        self.selected_index = 0
        self.saved = True
        self.create_menu()

    def create_menu(self):
        self.menu = ui.Menu.io.from_json(MENU_PATH)
        self.menu.index = 2
        root: ui.LayoutNode = self.menu.root

        self.pfb_scene_item = nanome.ui.LayoutNode.io.from_json(SCENE_ITEM_PATH)

        self.ln_scenes: ui.LayoutNode = root.find_node('Scenes')
        self.ln_save: ui.LayoutNode = root.find_node('Save')

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

        btn_save_continue: ui.Button = root.find_node('Button Save Continue').get_content()
        btn_save_continue.register_pressed_callback(self.save)

        self.btn_delete = btn_delete
        self.btn_update = btn_update
        self.inp_scenes_name = inp_scenes_name
        self.btn_save_cancel = btn_save_cancel
        self.btn_save_continue = btn_save_continue

        self.update_scenes()
        self.toggle_edit_mode(True)

    def open_menu(self):
        self.menu.enabled = True
        self.plugin.update_menu(self.menu)

    def update_scenes(self):
        self.lst_scenes.items.clear()
        for i in range(len(self.scenes)):
            ln_item: ui.LayoutNode = self.pfb_scene_item.clone()

            btn: ui.Button = ln_item.get_content()
            btn.register_pressed_callback(partial(self.select_scene, i))

            lbl: ui.Label = ln_item.find_node('Label').get_content()
            lbl.text_value = f'Scene {i + 1}'

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
        self.scenes.append(workspace)
        self.update_scenes()
        self.select_scene(-1)

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

        self.plugin.update_content(btn)

    def delete_scene(self, btn=None):
        del self.scenes[self.selected_index]
        self.selected_index = max(0, self.selected_index - 1)
        self.select_scene(self.selected_index)

        self.update_scenes()
        self.plugin.update_content(btn)
        self.set_saved(False)
        self.update_controls()

    def load(self, filename, scenes: 'list[Workspace]'):
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
        self.selected_index = index + offset
        self.select_scene(self.selected_index)
        self.update_scenes()
        self.set_saved(False)

    def reset(self, btn=None):
        self.scenes.clear()
        self.selected_index = 0
        self.inp_scenes_name.input_text = ''
        self.menu.title = 'Scene Viewer'
        self.set_saved(True)
        self.update_scenes()
        self.update_controls()
        self.open_menu()

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

        index = (self.selected_index + offset) % len(self.scenes)
        self.select_scene(index)

    def select_scene(self, index, btn=None):
        if not self.scenes:
            return

        if index < 0:
            index = len(self.scenes) + index

        self.lst_scenes.items[self.selected_index].get_content().selected = False
        self.selected_index = index
        self.lst_scenes.items[index].get_content().selected = True
        self.plugin.update_content(self.lst_scenes)

        # clear workspace first to fix a bug where structure color doesn't update
        self.plugin.update_workspace(Workspace())
        self.plugin.update_workspace(self.scenes[index])

    def set_saved(self, saved):
        self.saved = saved
        shows_unsaved = self.menu.title[-1] == '*'

        if saved and shows_unsaved:
            self.menu.title = self.menu.title[:-1]
        elif not saved and not shows_unsaved:
            self.menu.title += '*'
        if saved == shows_unsaved:
            self.plugin.update_menu(self.menu)

    def toggle_edit_mode(self, edit_mode, btn=None):
        self.ln_btn_edit.enabled = not edit_mode
        self.ln_btn_view.enabled = edit_mode
        self.ln_btns_edit.enabled = edit_mode
        self.plugin.update_node(self.ln_btn_edit, self.ln_btn_view, self.ln_btns_edit)
        self.plugin.update_content(self.lst_scenes)
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
        self.scenes[self.selected_index] = workspace
        self.plugin.update_content(btn)
        self.set_saved(False)
