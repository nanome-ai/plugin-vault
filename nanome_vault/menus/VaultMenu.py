import os
import sys
from functools import partial

import nanome
from nanome.util import Color
from nanome.util.enums import ExportFormats

from .. import VaultManager

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
MENU_PATH = os.path.join(BASE_DIR, 'json', 'menu.json')
LIST_ITEM_PATH = os.path.join(BASE_DIR, 'json', 'list_item.json')
UP_ICON_PATH = os.path.join(BASE_DIR, 'icons', 'up.png')
LOCK_ICON_PATH = os.path.join(BASE_DIR, 'icons', 'lock.png')

class VaultMenu:
    def __init__(self, plugin, address):
        self.plugin = plugin
        self.address = address
        self.path = '.'
        self.showing_upload = False
        self.create_menu()

    def create_menu(self):
        self.menu = nanome.ui.Menu.io.from_json(MENU_PATH)
        root = self.menu.root

        self.pfb_list_item = nanome.ui.LayoutNode.io.from_json(LIST_ITEM_PATH)
        btn = self.pfb_list_item.find_node('ButtonNode').get_content()
        btn.outline.active = False
        btn.mesh.active = True
        btn.mesh.enabled.idle = False
        btn.mesh.color.highlighted = Color(whole_num=0x2fdbbfff)

        # outer wrapper components
        def open_url(button):
            self.plugin.open_url(self.address)
        url_button = root.find_node('URLButton').get_content()
        url_button.register_pressed_callback(open_url)

        def go_up(button):
            self.open_folder('..')
            self.toggle_upload(show=False)
        self.btn_up = root.find_node('GoUpButton').get_content()
        self.btn_up.register_pressed_callback(go_up)

        self.btn_up.unusable = True
        self.btn_up.icon.active = True
        self.btn_up.icon.value.set_all(UP_ICON_PATH)
        self.btn_up.icon.size = 0.5
        self.btn_up.icon.color.unusable = Color.Grey()

        self.btn_upload = root.find_node('UploadButton').get_content()
        self.btn_upload.register_pressed_callback(self.toggle_upload)

        lbl_instr = root.find_node('InstructionLabel').get_content()
        lbl_instr.text_value = f'Visit {self.address} in browser to add files'
        self.lbl_crumbs = root.find_node('Breadcrumbs').get_content()

        # file explorer components
        self.ln_explorer = root.find_node('FileExplorer')

        ln_file_list = root.find_node('FileList')
        self.lst_files = ln_file_list.get_content()
        self.lst_files.parent = ln_file_list

        ln_file_loading = root.find_node('FileLoading')
        self.lbl_loading = ln_file_loading.get_content()
        self.lbl_loading.parent = ln_file_loading

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

        self.locked_folders = []
        self.locked_path = None
        self.folder_key = None
        self.folder_to_unlock = None

        # upload components
        self.ln_upload = root.find_node('FileUpload')

        self.btn_upload_selected = None
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

        self.upload_item = None
        self.upload_name = None
        self.upload_ext = None

    def show_menu(self):
        self.menu.enabled = True
        self.plugin.update_menu(self.menu)
        self.update()

    def update(self):
        items = VaultManager.list_path(self.path)
        at_root = self.path == '.'

        if at_root:
            account = self.plugin.account
            items['folders'].append(account)

        if self.btn_upload.unusable != at_root:
            self.btn_upload.unusable = at_root
            self.plugin.update_content(self.btn_upload)

        self.update_crumbs()
        self.update_explorer(items)

    def update_crumbs(self):
        at_root = self.path == '.'
        subpath = '' if at_root else self.path

        parts = subpath.split('/')
        if len(parts) > 5:
            del parts[2:-2]
            parts.insert(2, '...')
        subpath = '/'.join(parts)

        subpath = subpath.replace(self.plugin.account, 'account')
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

        folders = items['folders']
        files = items['files']

        old_items = set(map(lambda item: item.name, self.lst_files.items))
        new_items = folders + files

        add_set = set(new_items)
        remove_items = old_items - add_set
        add_items = add_set - old_items
        changed = False

        for item in remove_items:
            self.remove_item(item)
            changed = True

        # iterate list to preserve ordering
        for index, item in enumerate(new_items):
            if item not in add_items:
                continue
            self.add_item(item, item in folders, index)
            changed = True

        if changed or not len(old_items):
            self.plugin.update_content(self.lst_files)

    def add_item(self, name, is_folder, index=None):
        new_item = self.pfb_list_item.clone()
        new_item.name = name
        ln_btn = new_item.find_node('ButtonNode')
        btn = ln_btn.get_content()
        btn.item_name = name

        display_name = name.replace(self.plugin.account, 'account')
        lbl = new_item.find_node('LabelNode').get_content()
        lbl.text_value = display_name

        if is_folder:
            lbl.text_value += '/'

        if is_folder and name in self.locked_folders:
            btn.icon.active = True
            btn.icon.value.set_all(LOCK_ICON_PATH)
            btn.icon.size = 0.5
            btn.icon.position.x = 0.9

        def on_load():
            self.lst_files.parent.enabled = True
            self.lbl_loading.parent.enabled = False
            self.plugin.update_menu(self.menu)

        def on_file_pressed(button):
            self.lst_files.parent.enabled = False
            self.lbl_loading.parent.enabled = True
            self.lbl_loading.text_value = 'loading...\n' + button.item_name
            self.plugin.update_menu(self.menu)
            self.plugin.load_file(button.item_name, on_load)

        def on_folder_pressed(button):
            self.open_folder(button.item_name)

        cb = on_folder_pressed if is_folder else on_file_pressed
        btn.register_pressed_callback(cb)

        if index is None:
            self.lst_files.items.append(new_item)
        else:
            self.lst_files.items.insert(index, new_item)

    def remove_item(self, name):
        items = self.lst_files.items
        for child in items:
            if child.name == name:
                items.remove(child)
                break

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
        if not VaultManager.is_safe_path(self.path):
            self.path = '.'

        self.update()

    def open_locked_folder(self, button=None):
        key = self.inp_unlock.input_text
        path = os.path.join(self.path, self.folder_to_unlock)

        if VaultManager.is_key_valid(path, key):
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

    def toggle_upload(self, button=None, show=None):
        show = not self.showing_upload if show is None else show
        self.showing_upload = show
        self.ln_upload.enabled = show
        self.ln_upload_confirm.enabled = False
        self.ln_upload_message.enabled = show
        self.ln_explorer.enabled = not show
        self.btn_upload.text.value.set_all('Cancel' if show else 'Upload Here')

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

    def upload_workspace(self, button=None):
        name = self.inp_workspace_name.input_text
        if not name:
            return

        def on_export(results):
            self.upload_item = results[0]
            self.upload_name = name
            self.upload_ext = 'nanome'
            self.ln_upload_workspace.enabled = False
            self.show_upload_confirm()

        self.plugin.request_export(ExportFormats.Nanome, on_export)

    def show_upload_macro(self):
        def select_macro(button):
            self.upload_item = button.macro.logic
            self.upload_name = button.macro.title
            self.upload_ext = 'lua'
            self.lst_upload.parent.enabled = False
            self.show_upload_confirm()

        def on_macro_list(macros):
            self.lst_upload.items = []
            for macro in macros:
                item = self.pfb_list_item.clone()
                lbl = item.find_node('LabelNode').get_content()
                lbl.text_value = macro.title
                btn = item.find_node('ButtonNode').get_content()
                btn.macro = macro
                btn.register_pressed_callback(select_macro)
                self.lst_upload.items.append(item)

            if not macros:
                self.lst_upload.parent.enabled = False
                self.show_upload_message('no macros found')
            else:
                self.plugin.update_content(self.lst_upload)

        nanome.api.macro.Macro.get_live(on_macro_list)

    def show_upload_complex(self):
        def select_complex(button):
            self.upload_item = button.complex
            self.lst_upload.parent.enabled = False
            self.ln_upload_complex_type.enabled = True
            self.plugin.update_menu(self.menu)

        def on_complex_list(complexes):
            self.lst_upload.items = []
            for complex in complexes:
                item = self.pfb_list_item.clone()
                lbl = item.find_node('LabelNode').get_content()
                lbl.text_value = complex.full_name
                btn = item.find_node('ButtonNode').get_content()
                btn.complex = complex
                btn.register_pressed_callback(select_complex)
                self.lst_upload.items.append(item)

            if not complexes:
                self.lst_upload.parent.enabled = False
                self.show_upload_message('no structures found')
            else:
                self.plugin.update_content(self.lst_upload)

        self.plugin.request_complex_list(on_complex_list)

    def upload_complex(self, extension, format, button):
        def on_export(results):
            self.upload_name = self.upload_item.name
            self.upload_item = results[0]
            self.upload_ext = extension
            self.ln_upload_complex_type.enabled = False
            self.show_upload_confirm()

        self.plugin.request_export(format, on_export, [self.upload_item.index])

    def show_upload_message(self, message=None):
        self.ln_upload_message.enabled = True

        if message is None:
            self.lbl_upload_message.text_value = 'select an item to upload'
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
