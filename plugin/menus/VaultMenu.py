import asyncio
import os
import urllib.parse
import sys
from functools import partial

import nanome
from nanome.util import async_callback, Color
from nanome.util.enums import ExportFormats

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
MENU_PATH = os.path.join(BASE_DIR, 'json/menu.json')
LIST_ITEM_PATH = os.path.join(BASE_DIR, 'json/list_item.json')
ICON_LOCK = os.path.join(BASE_DIR, 'icons/lock.png')
ICON_SORT = os.path.join(BASE_DIR, 'icons/sort.png')
ICON_UP = os.path.join(BASE_DIR, 'icons/up.png')

ACCOUNT_FOLDER = 'account'
ORG_FOLDER = 'my org'


class VaultMenu:
    def __init__(self, plugin: nanome.PluginInstance, address):
        self.plugin = plugin
        self.address = address
        self.path = '.'

        self.selected_items = []
        self.showing_upload = False

        self.pending_action = None
        self.pending_integration = None

        self.sort_btn = None
        self.sort_by = 'name'
        self.sort_order = 1

        self.locked_folders = []
        self.locked_path = None
        self.folder_key = None
        self.folder_to_unlock = None

        self.btn_upload_selected = None
        self.upload_item = None
        self.upload_name = None
        self.upload_ext = None

        self.create_menu()

    def create_menu(self):
        self.menu = nanome.ui.Menu.io.from_json(MENU_PATH)
        root = self.menu.root

        self.pfb_list_item = nanome.ui.LayoutNode.io.from_json(LIST_ITEM_PATH)

        # outer wrapper components
        def go_up(button):
            self.open_folder('..')
            self.toggle_upload(show=False)
        self.btn_up = root.find_node('GoUpButton').get_content()
        self.btn_up.register_pressed_callback(go_up)

        self.btn_up.unusable = True
        self.btn_up.icon.active = True
        self.btn_up.icon.value.set_all(ICON_UP)
        self.btn_up.icon.size = 0.5
        self.btn_up.icon.color.unusable = Color.Grey()

        self.ln_controls = root.find_node('Controls')
        self.ln_main_controls = root.find_node('MainControls')
        self.ln_integration_controls = root.find_node('IntegrationControls')

        self.btn_actions = self.ln_main_controls.find_node('Actions').get_content()
        self.btn_actions.register_pressed_callback(self.toggle_actions)

        self.btn_select = self.ln_main_controls.find_node('Select').get_content()
        self.btn_select.register_pressed_callback(self.select_all)

        self.btn_load = self.ln_main_controls.find_node('Load').get_content()
        self.btn_load.register_pressed_callback(self.load_files)
        self.btn_load.disable_on_press = True

        btn_integration_cancel = self.ln_integration_controls.find_node('Cancel').get_content()
        btn_integration_cancel.register_pressed_callback(self.integration_cancel)

        self.btn_integration_save = self.ln_integration_controls.find_node('Save').get_content()
        self.btn_integration_save.register_pressed_callback(self.integration_save)
        self.btn_integration_save.disable_on_press = True

        self.lbl_instr = root.find_node('InstructionLabel').get_content()
        self.lbl_crumbs = root.find_node('Breadcrumbs').get_content()

        # file explorer components
        self.ln_explorer = root.find_node('FileExplorer')

        ln_file_list = root.find_node('FileList')
        self.lst_files = ln_file_list.get_content()
        self.lst_files.parent = ln_file_list

        ln_file_loading = root.find_node('FileLoading')
        self.lbl_loading = ln_file_loading.get_content()
        self.lbl_loading.parent = ln_file_loading

        # actions components
        self.ln_actions_panel = root.find_node('ActionsPanel')
        self.ln_actions_panel.get_content().register_pressed_callback(self.toggle_actions)

        self.ln_actions_list = self.ln_actions_panel.find_node('Actions')
        self.ln_actions_dialog = self.ln_actions_panel.find_node('ConfirmDialog')

        self.lst_actions = root.find_node('ActionsList').get_content()

        inp_dialog_action = self.ln_actions_dialog.find_node('Input').get_content()
        inp_dialog_action.register_submitted_callback(self.on_action_confirm)
        btn_action_cancel = self.ln_actions_dialog.find_node('Cancel').get_content()
        btn_action_cancel.register_pressed_callback(self.on_action_cancel)
        btn_action_confirm = self.ln_actions_dialog.find_node('Confirm').get_content()
        btn_action_confirm.register_pressed_callback(self.on_action_confirm)

        # sort order
        for sort in ['Name', 'Size', 'Date Added']:
            btn = self.ln_actions_panel.find_node(sort).get_content()
            btn.register_pressed_callback(self.change_sort)
            btn.icon.value.set_all(ICON_SORT)
            btn.icon.rotation.z = 180

        btn = self.ln_actions_panel.find_node('Name').get_content()
        self.sort_btn = btn
        btn.selected = True
        btn.icon.active = True

        # unlock components
        self.ln_unlock = root.find_node('UnlockFolder')
        self.ln_unlock_error = root.find_node('UnlockError')

        self.inp_unlock = root.find_node('UnlockInput').get_content()
        self.inp_unlock.password = True
        self.inp_unlock.register_submitted_callback(self.open_locked_folder)

        self.btn_unlock_cancel = root.find_node('UnlockCancel').get_content()
        self.btn_unlock_cancel.register_pressed_callback(self.cancel_open_locked)
        self.btn_unlock_continue = root.find_node('UnlockContinue').get_content()
        self.btn_unlock_continue.register_pressed_callback(self.open_locked_folder)

        # upload components
        self.ln_upload = root.find_node('FileUpload')

        btn_workspace = root.find_node('UploadTypeWorkspace').get_content()
        btn_workspace.name = 'workspace'
        btn_workspace.register_pressed_callback(self.select_upload_type)
        btn_structure = root.find_node('UploadTypeStructure').get_content()
        btn_structure.name = 'structure'
        btn_structure.register_pressed_callback(self.select_upload_type)
        btn_macro = root.find_node('UploadTypeMacro').get_content()
        btn_macro.name = 'macro'
        btn_macro.register_pressed_callback(self.select_upload_type)

        self.ln_upload_message = root.find_node('UploadMessage')
        self.lbl_upload_message = self.ln_upload_message.get_content()

        ln_upload_list = root.find_node('UploadList')
        self.lst_upload = ln_upload_list.get_content()
        self.lst_upload.parent = ln_upload_list

        self.ln_upload_workspace = root.find_node('UploadWorkspace')
        self.inp_workspace_name = root.find_node('UploadWorkspaceName').get_content()
        self.inp_workspace_name.register_submitted_callback(self.upload_workspace)
        btn_workspace_continue = root.find_node('UploadWorkspaceContinue').get_content()
        btn_workspace_continue.register_pressed_callback(self.upload_workspace)

        self.ln_upload_complex_type = root.find_node('UploadComplexType')
        btn_pdb = root.find_node('PDB').get_content()
        btn_pdb.register_pressed_callback(partial(self.upload_complex, 'pdb', ExportFormats.PDB))
        btn_sdf = root.find_node('SDF').get_content()
        btn_sdf.register_pressed_callback(partial(self.upload_complex, 'sdf', ExportFormats.SDF))
        btn_mmcif = root.find_node('MMCIF').get_content()
        btn_mmcif.register_pressed_callback(partial(self.upload_complex, 'cif', ExportFormats.MMCIF))

        self.ln_upload_confirm = root.find_node('UploadConfirm')
        self.lbl_upload_confirm = root.find_node('UploadConfirmLabel').get_content()
        btn_confirm = root.find_node('UploadConfirmButton').get_content()
        btn_confirm.register_pressed_callback(self.confirm_upload)

    def open_for_integration(self, request):
        self.pending_integration = request
        self.ln_main_controls.enabled = False
        self.ln_integration_controls.enabled = True
        self.show_menu()

    def show_menu(self):
        if self.pending_integration:
            self.lbl_instr.text_value = 'Choose where to save your file'
        else:
            self.lbl_instr.text_value = f'Visit {self.address} in browser to add files'

        self.update()
        self.menu.enabled = True
        self.plugin.update_menu(self.menu)

    def integration_cancel(self, button=None):
        self.pending_integration.send_response(False)
        self.integration_complete()

    def integration_save(self, button=None):
        (_, filename, data) = self.pending_integration.get_args()
        r = self.plugin.vault.add_file(self.path, filename, data, self.folder_key)
        self.pending_integration.send_response(r.ok)
        self.integration_complete()

    def integration_complete(self):
        self.pending_integration = None
        self.ln_main_controls.enabled = True
        self.ln_integration_controls.enabled = False
        self.show_menu()

    def replace_path(self, path, is_url=False):
        path = path.replace(self.plugin.account, ACCOUNT_FOLDER)
        if self.plugin.org is not None:
            org_folder = ORG_FOLDER.replace(' ', '-') if is_url else ORG_FOLDER
            path = path.replace(self.plugin.org, org_folder)
        return path

    def update(self):
        self.selected_items.clear()
        items = self.plugin.vault.list_path(self.path + '/', self.folder_key)
        at_root = self.path == '.'

        if at_root:
            org = self.plugin.org
            if org is not None:
                items['folders'].append({
                    'name': org,
                    'size': '',
                    'size_text': '',
                    'created': '',
                    'created_text': '',
                })

            account = self.plugin.account
            items['folders'].append({
                'name': account,
                'size': '',
                'size_text': '',
                'created': '',
                'created_text': '',
            })

        self.update_crumbs()
        self.update_explorer(items)
        self.update_controls()

    def update_crumbs(self):
        at_root = self.path == '.'
        subpath = '' if at_root else self.path

        parts = subpath.split('/')
        if len(parts) > 5:
            del parts[2:-2]
            parts.insert(2, '...')
        subpath = '/'.join(parts)

        subpath = self.replace_path(subpath)
        path = '/ ' + subpath.replace('/', ' / ')

        self.lbl_crumbs.text_value = path
        self.plugin.update_content(self.lbl_crumbs)
        self.btn_up.unusable = at_root
        self.plugin.update_content(self.btn_up)

    def update_explorer(self, items):
        self.locked_folders = items['locked']
        self.locked_path = items['locked_path']
        if self.locked_path is None:
            self.folder_key = None

        self.lst_files.items.clear()

        # sort desc for 1 unless sorting by name
        if self.sort_by == 'name':
            reverse = self.sort_order == -1
            def key_fn(x): return x[self.sort_by].lower()
        else:
            reverse = self.sort_order == 1
            def key_fn(x): return x[self.sort_by]

        folders = sorted(items['folders'], key=key_fn, reverse=reverse)
        files = sorted(items['files'], key=key_fn, reverse=reverse)

        for folder in folders:
            self.add_item(folder, True)

        ignore_ext = self.plugin.extensions['external']
        for file in files:
            if any(file['name'].endswith('.' + ext) for ext in ignore_ext):
                continue
            self.add_item(file, False)

        self.plugin.update_content(self.lst_files)

    def update_actions(self):
        def make_action(action):
            ln = nanome.ui.LayoutNode()
            btn = ln.add_new_button(action)
            btn.name = action
            btn.register_pressed_callback(self.on_action_pressed)
            return ln

        self.lst_actions.items.clear()
        self.lst_actions.items.append(make_action('Open Website'))
        self.lst_actions.items.append(make_action('Open Scene Viewer'))

        if self.plugin.obj_loader.objs:
            self.lst_actions.items.append(make_action('Manage OBJs'))

        if self.path != '.' and not self.selected_items:
            self.lst_actions.items.append(make_action('Upload Here'))
            self.lst_actions.items.append(make_action('New Folder'))

            if self.path not in [self.plugin.account, self.plugin.org, 'shared']:
                self.lst_actions.items.append(make_action('Rename Folder'))
                self.lst_actions.items.append(make_action('Delete Folder'))

        if len(self.selected_items) == 1:
            self.lst_actions.items.append(make_action('Rename'))

        if self.selected_items:
            self.lst_actions.items.append(make_action('Delete'))

        self.plugin.update_content(self.lst_actions)

    def update_controls(self):
        # update integration save button
        if self.pending_integration:
            self.btn_integration_save.unusable = self.path == '.'
            self.plugin.update_content(self.btn_integration_save)
            return

        self.update_actions()

        # update select/deselect all button
        num_files = sum(1 for i in self.lst_files.items if not i.is_folder)
        self.btn_select.unusable = num_files == 0

        btn_text = 'Deselect All' if self.selected_items else 'Select All'
        self.btn_select.text.value.set_all(btn_text)
        self.plugin.update_content(self.btn_select)

        # update load button
        n = len(self.selected_items)
        items_text = f' {n} item{"s" if n > 1 else ""}' if n > 0 else ''

        self.btn_load.unusable = n == 0
        self.btn_load.text.value.set_all('Load' + items_text)
        self.plugin.update_content(self.btn_load)

    def add_item(self, item, is_folder):
        name = item['name']
        new_item = self.pfb_list_item.clone()
        new_item.name = name
        new_item.is_folder = is_folder

        ln_btn = new_item.find_node('ButtonNode')
        btn = ln_btn.get_content()
        btn.item_name = name

        display_name = self.replace_path(name)
        if is_folder:
            display_name += '/'
        btn.text.value.set_all(display_name)

        if self.pending_integration and not is_folder:
            btn.unusable = True

        if self.sort_by != 'name':
            info = item['size_text' if self.sort_by == 'size' else 'created_text']
            lbl_info = new_item.find_node('InfoNode').get_content()
            lbl_info.text_value = info
        else:
            new_item.find_node('InfoNode').enabled = False

        if is_folder and name in self.locked_folders:
            btn.icon.active = True
            btn.icon.value.set_all(ICON_LOCK)
            btn.icon.size = 0.5
            btn.icon.position.x = 0.9

        cb = self.on_folder_pressed if is_folder else self.on_file_pressed
        btn.register_pressed_callback(cb)

        self.lst_files.items.append(new_item)

    def on_file_pressed(self, button):
        button.selected = not button.selected
        if button.selected:
            self.selected_items.append(button)
        else:
            self.selected_items.remove(button)

        self.update_controls()
        self.plugin.update_content(button)

    def on_folder_pressed(self, button):
        self.open_folder(button.item_name)

    def open_folder(self, folder):
        if folder in self.locked_folders and not self.folder_key:
            self.ln_explorer.enabled = False
            self.inp_unlock.input_text = ''
            self.ln_unlock.enabled = True
            self.ln_unlock_error.enabled = False
            self.folder_to_unlock = folder
            self.plugin.update_menu(self.menu)
            return

        self.ln_unlock.enabled = False
        self.lst_files.items.clear()

        self.path = os.path.normpath(os.path.join(self.path, folder))
        if sys.platform.startswith('win32'):
            self.path = self.path.replace('\\', '/')
        if self.path[:2] == '..':
            self.path = '.'

        self.update()

    def open_locked_folder(self, button=None):
        key = self.inp_unlock.input_text
        path = os.path.join(self.path, self.folder_to_unlock)

        if self.plugin.vault.is_key_valid(path, key):
            self.folder_key = key
            self.open_folder(self.folder_to_unlock)
            self.cancel_open_locked()
        else:
            self.ln_unlock_error.enabled = True
            self.plugin.update_node(self.ln_unlock_error)

    def cancel_open_locked(self, button=None):
        self.ln_explorer.enabled = True
        self.ln_unlock.enabled = False
        self.plugin.update_menu(self.menu)

    @async_callback
    async def load_files(self, button=None):
        if not self.selected_items:
            return

        n = len(self.selected_items)
        self.lst_files.parent.enabled = False
        self.lbl_loading.parent.enabled = True
        self.lbl_loading.text_value = f'loading...\n{n} item{"s" if n > 1 else ""}'
        self.plugin.update_node(self.ln_explorer)

        load_requests = []
        for btn in self.selected_items:
            load_requests.append(self.plugin.load_file(btn.item_name))
            btn.selected = False
        await asyncio.gather(*load_requests)

        self.selected_items = []
        self.lst_files.parent.enabled = True
        self.lbl_loading.parent.enabled = False
        self.update_controls()
        self.plugin.update_menu(self.menu)

    def on_action_pressed(self, button):
        if button.name == 'Open Website':
            path = urllib.parse.quote(self.replace_path(self.path, True))
            url = f'{self.address}/{path}'
            self.plugin.open_url(url)
            self.toggle_actions()
        elif button.name == 'Open Scene Viewer':
            self.plugin.scene_viewer.open_menu()
            self.toggle_actions()
        elif button.name == 'Manage OBJs':
            self.plugin.obj_loader.show_list()
            self.toggle_actions()
        elif button.name == 'Upload Here':
            self.toggle_upload()
            self.toggle_actions()
        elif button.name == 'New Folder':
            self.action_prompt('New Folder', 'Please provide a name:', True, 'new folder')
        elif button.name == 'Rename':
            name = self.selected_items[0].item_name
            desc = f'Rename "{name}" to:'
            self.action_prompt('Rename', desc, True, name.rsplit('.', 1)[0])
        elif button.name == 'Delete':
            n = len(self.selected_items)
            desc = f'Are you sure you want to delete {n} file{"s" if n > 1 else ""}?'
            self.action_prompt('Delete', desc)
        elif button.name == 'Rename Folder':
            folder = self.path.split('/')[-1]
            desc = f'Rename "{folder}" to:'
            self.action_prompt('Rename Folder', desc, True, folder)
        elif button.name == 'Delete Folder':
            self.action_prompt('Delete Folder', 'Are you sure you want to delete this folder?')

    def action_prompt(self, title, description, show_input=False, input_default=''):
        self.pending_action = title
        self.ln_actions_list.enabled = False
        self.ln_actions_dialog.enabled = True

        self.ln_actions_dialog.find_node('Title').get_content().text_value = title
        self.ln_actions_dialog.find_node('Description').get_content().text_value = description
        ln_inp = self.ln_actions_dialog.find_node('Input')
        ln_inp.enabled = show_input
        ln_inp.get_content().input_text = input_default

        self.plugin.update_node(self.ln_actions_panel)

    def on_action_cancel(self, button):
        self.ln_actions_list.enabled = True
        self.ln_actions_dialog.enabled = False
        self.plugin.update_node(self.ln_actions_panel)

    def on_action_confirm(self, button):
        inp_text = self.ln_actions_dialog.find_node('Input').get_content().input_text
        key = self.folder_key

        if self.pending_action == 'New Folder':
            self.plugin.vault.create_path(f'{self.path}/{inp_text}', key)

        elif self.pending_action == 'Rename':
            name = self.selected_items[0].item_name
            ext = name.split('.')[-1]
            new_name = inp_text + '.' + ext
            self.plugin.vault.rename_path(f'{self.path}/{name}', new_name, key)

        elif self.pending_action == 'Delete':
            for item in self.selected_items:
                self.plugin.vault.delete_path(f'{self.path}/{item.item_name}', key)

        elif self.pending_action == 'Rename Folder':
            self.plugin.vault.rename_path(self.path, inp_text, key)

        elif self.pending_action == 'Delete Folder':
            self.plugin.vault.delete_path(self.path, key)

        self.toggle_actions()

        if self.pending_action in ['Rename Folder', 'Delete Folder']:
            self.open_folder('..')
        else:
            self.update()

    def toggle_actions(self, button=None):
        enabled = not self.ln_actions_panel.enabled

        # hide upload if visible
        if self.showing_upload and enabled:
            self.toggle_upload()
            return

        if enabled:
            self.ln_actions_list.enabled = True
            self.ln_actions_dialog.enabled = False

        # update button
        btn_text = 'Cancel' if enabled or self.showing_upload else 'Actions'
        self.btn_actions.text.value.set_all(btn_text)
        self.plugin.update_content(self.btn_actions)

        self.ln_actions_panel.enabled = enabled
        self.plugin.update_node(self.ln_actions_panel)

    def change_sort(self, button):
        # reset state of old sort button
        if self.sort_btn is not None and button != self.sort_btn:
            self.sort_btn.selected = False
            self.sort_btn.icon.active = False
            self.plugin.update_content(self.sort_btn)

        if self.sort_btn == button:
            # toggle sort direction
            self.sort_order *= -1
            button.icon.rotation.z = 180 if self.sort_order == 1 else 0
        else:
            self.sort_btn = button
            self.sort_by = button.name
            self.sort_order = 1
            button.icon.rotation.z = 180
            button.selected = True
            button.icon.active = True

        self.plugin.update_content(self.sort_btn)
        self.update()

    def select_all(self, button):
        if self.selected_items:
            # deselect all
            for item in self.selected_items:
                item.selected = False
            self.selected_items.clear()
        else:
            # select all files
            self.selected_items.clear()
            for item in self.lst_files.items:
                if item.is_folder:
                    continue
                btn = item.find_node('ButtonNode').get_content()
                btn.selected = True
                self.selected_items.append(btn)

        self.update_controls()
        self.plugin.update_content(self.lst_files)

    def toggle_upload(self, button=None, show=None):
        show = not self.showing_upload if show is None else show
        self.showing_upload = show
        self.ln_upload.enabled = show
        self.ln_upload_confirm.enabled = False
        self.ln_upload_message.enabled = show
        self.ln_explorer.enabled = not show

        self.btn_actions.text.value.set_all('Cancel' if show else 'Actions')

        self.select_upload_type()
        self.plugin.update_menu(self.menu)

    def reset_upload(self):
        self.show_upload_message()

        self.upload_item = None
        self.upload_name = None
        self.upload_ext = None

        self.ln_upload_message.enabled = True
        self.ln_upload_workspace.enabled = False
        self.lst_upload.parent.enabled = False
        self.ln_upload_complex_type.enabled = False
        self.ln_upload_confirm.enabled = False

        self.lst_upload.items.clear()
        self.plugin.update_content(self.lst_upload)

    def select_upload_type(self, button=None):
        if self.btn_upload_selected:
            self.btn_upload_selected.selected = False
            self.plugin.update_content(self.btn_upload_selected)
            self.btn_upload_selected = None

        self.reset_upload()

        if not button:
            return

        self.btn_upload_selected = button
        self.btn_upload_selected.selected = True
        self.ln_upload_message.enabled = False

        if button.name == 'workspace':
            self.ln_upload_workspace.enabled = True
            self.inp_workspace_name.text_value = ''
        elif button.name == 'structure':
            self.lst_upload.parent.enabled = True
            self.show_upload_complex()
        elif button.name == 'macro':
            self.lst_upload.parent.enabled = True
            self.show_upload_macro()

        self.plugin.update_menu(self.menu)

    @async_callback
    async def upload_workspace(self, button=None):
        name = self.inp_workspace_name.input_text
        if not name:
            return

        results = await self.plugin.request_export(ExportFormats.Nanome)
        self.upload_item = results[0]
        self.upload_name = name
        self.upload_ext = 'nanome'
        self.ln_upload_workspace.enabled = False
        self.show_upload_confirm()

    @async_callback
    async def show_upload_macro(self):
        def select_macro(button):
            self.upload_item = button.macro.logic
            self.upload_name = button.macro.title
            self.upload_ext = 'lua'
            self.lst_upload.parent.enabled = False
            self.show_upload_confirm()

        macros = await nanome.api.macro.Macro.get_live()
        self.lst_upload.items = []
        for macro in macros:
            item = self.pfb_list_item.clone()
            btn = item.find_node('ButtonNode').get_content()
            btn.text.value.set_all(macro.title)
            btn.macro = macro
            btn.register_pressed_callback(select_macro)
            self.lst_upload.items.append(item)

        if not macros:
            self.lst_upload.parent.enabled = False
            self.show_upload_message('no macros found')
        else:
            self.plugin.update_content(self.lst_upload)

    @async_callback
    async def show_upload_complex(self):
        def select_complex(button):
            self.upload_item = button.complex
            self.lst_upload.parent.enabled = False
            self.ln_upload_complex_type.enabled = True
            self.plugin.update_menu(self.menu)

        complexes = await self.plugin.request_complex_list()
        self.lst_upload.items = []
        for complex in complexes:
            item = self.pfb_list_item.clone()
            btn = item.find_node('ButtonNode').get_content()
            btn.text.value.set_all(complex.full_name)
            btn.complex = complex
            btn.register_pressed_callback(select_complex)
            self.lst_upload.items.append(item)

        if not complexes:
            self.lst_upload.parent.enabled = False
            self.show_upload_message('no structures found')
        else:
            self.plugin.update_content(self.lst_upload)

    @async_callback
    async def upload_complex(self, extension, format, button):
        results = await self.plugin.request_export(format, entities=[self.upload_item.index])
        self.upload_name = self.upload_item.name
        self.upload_item = results[0]
        self.upload_ext = extension
        self.ln_upload_complex_type.enabled = False
        self.show_upload_confirm()

    def show_upload_message(self, message=None):
        self.ln_upload_message.enabled = True

        if message is None:
            self.lbl_upload_message.text_value = 'select an item above to upload'
            return

        self.lbl_upload_message.text_value = message
        self.plugin.update_menu(self.menu)

    def show_upload_confirm(self):
        self.ln_upload_confirm.enabled = True
        self.lbl_upload_confirm.text_value = f'upload {self.upload_name}.{self.upload_ext}?'
        self.plugin.update_menu(self.menu)

    def confirm_upload(self, button):
        self.plugin.save_file(self.upload_item, self.upload_name, self.upload_ext)
        self.toggle_upload(show=False)
        self.update()
