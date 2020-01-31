import os
import sys
from functools import partial

import nanome

from .. import VaultManager

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
MENU_PATH = os.path.join(BASE_DIR, "Menu.json")
PPT_TAB_PATH = os.path.join(BASE_DIR, "PPTTab.json")
IMAGE_TAB_PATH = os.path.join(BASE_DIR, "ImageTab.json")
LIST_ITEM_PATH = os.path.join(BASE_DIR, "ListItem.json")
UP_ICON_PATH = os.path.join(BASE_DIR, "UpIcon.png")
LOCK_ICON_PATH = os.path.join(BASE_DIR, "LockIcon.png")

class Prefabs(object):
    tab_prefab = None
    ppt_prefab = None
    image_prefab = None
    list_item_prefab = None

class PageTypes(nanome.util.IntEnum):
    Home = 1
    Image = 2
    PPT = 3

#Singleton class.
class MenuManager(object):
    def __init__(self, plugin, address):
        MenuManager.instance = self
        self.plugin = plugin
        self.ReadJsons()
        MenuManager.Page.tab_bar = self.plugin.menu.root.find_node("TabBar")
        MenuManager.Page.page_parent = self.plugin.menu.root.find_node("Pages")
        MenuManager.Page.menu_manager = self

        home = self.plugin.menu.root.find_node("FilesPage")
        home_tab = self.plugin.menu.root.find_node("HomeTab")
        self.home_page = MenuManager.HomePage(home_tab, home, address)
        self.selected_page = self.home_page

        self.uploaded = False
        self.Refresh()

    def ReadJsons(self):
        self.plugin.menu = nanome.ui.Menu.io.from_json(MENU_PATH)
        Prefabs.ppt_prefab = nanome.ui.LayoutNode.io.from_json(PPT_TAB_PATH).get_children()[0]
        Prefabs.image_prefab = nanome.ui.LayoutNode.io.from_json(IMAGE_TAB_PATH).get_children()[0]
        Prefabs.list_item_prefab = nanome.ui.LayoutNode.io.from_json(LIST_ITEM_PATH)
        Prefabs.tab_prefab = self.plugin.menu.root.find_node("TabPrefab")
        Prefabs.tab_prefab.parent.remove_child(Prefabs.tab_prefab)

    def SwitchTab(self, page=None):
        if page==None:
            page = self.home_page
        self.selected_page.deselect()
        self.selected_page = page
        self.selected_page.select()
        MenuManager.RefreshMenu()

    def OpenPage(self, type, data, name):
        if type == PageTypes.Image:
            MenuManager.ImagePage(data, name)
        if type == PageTypes.PPT:
            MenuManager.PPTPage(data, name)
        self.Refresh()

    @classmethod
    def RefreshMenu(cls, content = None):
        MenuManager.instance.Refresh(content)

    def Refresh(self, content = None):
        if content and self.uploaded:
            self.plugin.update_content(content)
        else:
            self.uploaded = True
            self.plugin.menu.enabled = True
            self.plugin.update_menu(self.plugin.menu)

    def GetFiles(self):
        return list(map(lambda item: item.name, self.home_page.file_list.items))

    def GetOpenFiles(self):
        return list(map(lambda item: item.name, MenuManager.Page.page_parent.get_children()))

    class Page(object):
        tab_bar = None
        page_parent = None
        menu_manager = None
        def __init__(self, name, tab_prefab, page_prefab):
            #setup tab
            self.tab_base = tab_prefab.clone()
            tab_prefab = None
            self.tab_button = self.tab_base.get_content()
            self.tab_label = self.tab_base.find_node("TabPrefabLabel").get_content()
            self.tab_delete_button = self.tab_base.find_node("TabPrefabDelete").get_content()

            base_name = os.path.basename(name)
            base_name = os.path.splitext(base_name)[0]
            tab_name = base_name[:6]
            self.tab_label.text_value = tab_name

            fill = self.tab_bar.find_node("Fill")
            self.tab_bar.add_child(self.tab_base)
            self.tab_bar.remove_child(fill)
            self.tab_bar.add_child(fill)

            #setup page
            self.base = page_prefab.clone()
            self.base.name = base_name
            page_prefab = None
            self.page_parent.add_child(self.base)

            #setup buttons
            def tab_delete(button):
                self.page_parent.remove_child(self.base)
                self.tab_bar.remove_child(self.tab_base)
                self.menu_manager.SwitchTab()
            self.tab_delete_button.register_pressed_callback(tab_delete)

            def tab_pressed(button):
                self.menu_manager.SwitchTab(self)
            self.tab_button.register_pressed_callback(tab_pressed)

            self.menu_manager.SwitchTab(self)

        def select(self):
            self.base.enabled = True
            self.tab_base.get_content().selected = True

        def deselect(self):
            self.base.enabled = False
            self.tab_base.get_content().selected = False

    class HomePage(Page):
        def __init__(self, tab, page, address):
            self.tab_base = tab
            self.base = page
            self.type = PageTypes.Home
            self.tab_button = self.tab_base.get_content()
            self.plugin = MenuManager.instance.plugin

            self.path = '.'
            self.showing_upload = False

            def tab_pressed(button):
                self.menu_manager.SwitchTab(self)
            self.tab_button.register_pressed_callback(tab_pressed)

            def open_url(button):
                self.menu_manager.plugin.open_url(address)
            url_button = self.base.find_node("URLButton").get_content()
            url_button.register_pressed_callback(open_url)

            def go_up(button):
                self.OpenFolder('..')
                self.ToggleUpload(show=False)
            self.up_button = self.base.find_node("GoUpButton").get_content()
            self.up_button.register_pressed_callback(go_up)

            self.up_button.unusable = True
            self.up_button.icon.active = True
            self.up_button.icon.value.set_all(UP_ICON_PATH)
            self.up_button.icon.size = 0.5
            self.up_button.icon.color.unusable = nanome.util.Color.Grey()

            self.upload_button = self.base.find_node("UploadButton").get_content()
            self.upload_button.register_pressed_callback(self.ToggleUpload)

            self.instructions = self.base.find_node("InstructionLabel").get_content()
            self.instructions.text_value = "Visit %s in browser to add files" % address
            self.breadcrumbs = self.base.find_node("Breadcrumbs").get_content()

            # file explorer components
            self.file_explorer = self.base.find_node("FileExplorer")

            ln_file_list = self.base.find_node("FileList")
            self.file_list = ln_file_list.get_content()
            self.file_list.parent = ln_file_list

            ln_file_loading = self.base.find_node("FileLoading")
            self.file_loading = ln_file_loading.get_content()
            self.file_loading.parent = ln_file_loading

            # unlock components
            self.ln_unlock = self.base.find_node("UnlockFolder")
            self.ln_unlock_error = self.base.find_node("UnlockError")

            self.inp_unlock = self.base.find_node("UnlockInput").get_content()
            self.inp_unlock.register_submitted_callback(self.OpenLockedFolder)
            self.btn_unlock_cancel = self.base.find_node("UnlockCancel").get_content()
            self.btn_unlock_cancel.register_pressed_callback(self.CancelOpenLocked)
            self.btn_unlock_continue = self.base.find_node("UnlockContinue").get_content()
            self.btn_unlock_continue.register_pressed_callback(self.OpenLockedFolder)

            self.locked_folders = []
            self.locked_path = None
            self.folder_key = None
            self.folder_to_unlock = None

            # upload components
            self.ln_upload = self.base.find_node("FileUpload")

            self.selected_upload_button = None
            button_workspace = self.base.find_node("UploadTypeWorkspace").get_content()
            button_workspace.name = "workspace"
            button_workspace.register_pressed_callback(self.SelectUploadType)
            button_structure = self.base.find_node("UploadTypeStructure").get_content()
            button_structure.name = "structure"
            button_structure.register_pressed_callback(self.SelectUploadType)
            button_macro = self.base.find_node("UploadTypeMacro").get_content()
            button_macro.name = "macro"
            button_macro.register_pressed_callback(self.SelectUploadType)

            self.ln_upload_message = self.base.find_node("UploadMessage")
            self.lbl_upload_message = self.ln_upload_message.get_content()

            ln_upload_list = self.base.find_node("UploadList")
            self.lst_upload = ln_upload_list.get_content()
            self.lst_upload.parent = ln_upload_list

            self.ln_upload_workspace = self.base.find_node("UploadWorkspace")
            self.inp_workspace_name = self.base.find_node("UploadWorkspaceName").get_content()
            self.inp_workspace_name.register_submitted_callback(self.UploadWorkspace)
            button_workspace_continue = self.base.find_node("UploadWorkspaceContinue").get_content()
            button_workspace_continue.register_pressed_callback(self.UploadWorkspace)

            self.ln_upload_complex_type = self.base.find_node("UploadComplexType")
            button_pdb = self.base.find_node("PDB").get_content()
            button_pdb.register_pressed_callback(partial(self.UploadComplex, "pdb"))
            button_sdf = self.base.find_node("SDF").get_content()
            button_sdf.register_pressed_callback(partial(self.UploadComplex, "sdf"))
            button_mmcif = self.base.find_node("MMCIF").get_content()
            button_mmcif.register_pressed_callback(partial(self.UploadComplex, "cif"))

            self.ln_upload_confirm = self.base.find_node("UploadConfirm")
            self.lbl_upload_confirm = self.base.find_node("UploadConfirmLabel").get_content()
            button_confirm = self.base.find_node("UploadConfirmButton").get_content()
            button_confirm.register_pressed_callback(self.ConfirmUpload)

            self.upload_item = None
            self.upload_name = None
            self.upload_ext = None

            self.select()

        def Update(self):
            items = VaultManager.list_path(self.path)
            at_root = self.path == '.'

            if at_root:
                account = self.plugin.account
                items['folders'].append(account)

            if self.upload_button.unusable != at_root:
                self.upload_button.unusable = at_root
                MenuManager.RefreshMenu(self.upload_button)

            self.UpdateBreadcrumbs()
            self.UpdateExplorer(items)

        def UpdateBreadcrumbs(self):
            at_root = self.path == '.'
            subpath = '' if at_root else self.path

            parts = subpath.split('/')
            if len(parts) > 5:
                del parts[2:-2]
                parts.insert(2, '...')
            subpath = '/'.join(parts)

            subpath = subpath.replace(self.plugin.account, 'account')
            path = '/ ' + subpath.replace('/', ' / ')

            self.breadcrumbs.text_value = path
            MenuManager.RefreshMenu(self.breadcrumbs)
            self.up_button.unusable = at_root
            MenuManager.RefreshMenu(self.up_button)

        def UpdateExplorer(self, items):
            self.locked_folders = items['locked']
            self.locked_path = items['locked_path']
            if self.locked_path is None:
                self.folder_key = None

            folders = items['folders']
            files = items['files']

            old_items = set(map(lambda item: item.name, self.file_list.items))
            new_items = folders + files

            add_set = set(new_items)
            remove_items = old_items - add_set
            add_items = add_set - old_items
            changed = False

            for item in remove_items:
                self.RemoveItem(item)
                changed = True

            # iterate list to preserve ordering
            for index, item in enumerate(new_items):
                if item not in add_items:
                    continue
                self.AddItem(item, item in folders, index)
                changed = True

            if changed or not len(old_items):
                MenuManager.RefreshMenu(self.file_list)

        def AddItem(self, name, is_folder, index=None):
            new_item = Prefabs.list_item_prefab.clone()
            new_item.name = name
            ln_button = new_item.find_node("ButtonNode")
            button = ln_button.get_content()
            button.item_name = name

            display_name = name.replace(self.plugin.account, 'account')
            label = new_item.find_node("LabelNode").get_content()
            label.text_value = display_name

            if is_folder:
                label.text_value += '/'

            if is_folder and name in self.locked_folders:
                # button.icon.value.set_all(LOCK_ICON_PATH)
                # button.icon.size = 0.5
                # button.icon.position.x = 0.9
                img = ln_button.find_node("ImageNode").add_new_image(LOCK_ICON_PATH)
                img.scaling_option = img.ScalingOptions.fit

            def FilePressedCallback(button):
                self.file_list.parent.enabled = False
                self.file_loading.parent.enabled = True
                self.file_loading.text_value = 'loading...\n' + button.item_name
                MenuManager.RefreshMenu()

                def OnFileLoaded():
                    self.file_list.parent.enabled = True
                    self.file_loading.parent.enabled = False
                    MenuManager.RefreshMenu()

                self.plugin.load_file(button.item_name, OnFileLoaded)

            def FolderPressedCallback(button):
                self.OpenFolder(button.item_name)

            cb = FolderPressedCallback if is_folder else FilePressedCallback
            button.register_pressed_callback(cb)

            if index is None:
                self.file_list.items.append(new_item)
            else:
                self.file_list.items.insert(index, new_item)

        def RemoveItem(self, name):
            items = self.file_list.items
            for child in items:
                if child.name == name:
                    items.remove(child)
                    break

        def OpenFolder(self, folder):
            if folder in self.locked_folders and not self.folder_key:
                self.file_explorer.enabled = False
                self.inp_unlock.input_text = ''
                self.ln_unlock.enabled = True
                self.ln_unlock_error.enabled = False
                self.folder_to_unlock = folder
                MenuManager.RefreshMenu()
                return

            self.ln_unlock.enabled = False
            self.file_list.items.clear()

            self.path = os.path.normpath(os.path.join(self.path, folder))
            if sys.platform.startswith('win32'):
                self.path = self.path.replace('\\', '/')
            if not VaultManager.is_safe_path(self.path):
                self.path = '.'

            self.Update()

        def OpenLockedFolder(self, button=None):
            key = self.inp_unlock.input_text
            path = os.path.join(self.path, self.folder_to_unlock)

            if VaultManager.is_key_valid(path, key):
                self.folder_key = key
                self.OpenFolder(self.folder_to_unlock)
                self.CancelOpenLocked()
            else:
                self.ln_unlock_error.enabled = True
                MenuManager.RefreshMenu()

        def CancelOpenLocked(self, button=None):
            self.file_explorer.enabled = True
            self.ln_unlock.enabled = False
            MenuManager.RefreshMenu()

        def ToggleUpload(self, button=None, show=None):
            show = not self.showing_upload if show is None else show
            self.showing_upload = show
            self.ln_upload.enabled = show
            self.ln_upload_confirm.enabled = False
            self.ln_upload_message.enabled = show
            self.file_explorer.enabled = not show
            self.upload_button.text.value.set_all('Cancel' if show else 'Upload Here')

            self.SelectUploadType()
            MenuManager.RefreshMenu()

        def ResetUpload(self):
            self.ShowUploadMessage()

            self.upload_item = None
            self.upload_name = None
            self.upload_ext = None

            self.ln_upload_message.enabled = True
            self.ln_upload_workspace.enabled = False
            self.lst_upload.parent.enabled = False
            self.ln_upload_complex_type.enabled = False
            self.ln_upload_confirm.enabled = False

            self.lst_upload.items.clear()
            MenuManager.RefreshMenu(self.lst_upload)

        def SelectUploadType(self, button=None):
            if self.selected_upload_button:
                self.selected_upload_button.selected = False
                MenuManager.RefreshMenu(self.selected_upload_button)
                self.selected_upload_button = None

            self.ResetUpload()

            if not button:
                return

            self.selected_upload_button = button
            self.selected_upload_button.selected = True
            self.ln_upload_message.enabled = False

            if button.name == 'workspace':
                self.ln_upload_workspace.enabled = True
                self.inp_workspace_name.text_value = ''
            elif button.name == 'structure':
                self.lst_upload.parent.enabled = True
                self.ShowUploadComplex()
            elif button.name == 'macro':
                self.lst_upload.parent.enabled = True
                self.ShowUploadMacro()

            MenuManager.RefreshMenu()

        def UploadWorkspace(self, button=None):
            name = self.inp_workspace_name.input_text
            if not name:
                return

            def on_workspace(workspace):
                self.upload_item = workspace
                self.upload_name = name
                self.upload_ext = 'nanome'
                self.ln_upload_workspace.enabled = False
                self.ShowUploadConfirm()

            self.plugin.request_workspace(on_workspace)

        def ShowUploadMacro(self):
            def select_macro(button):
                self.upload_item = button.macro
                self.upload_name = button.macro.title
                self.upload_ext = 'lua'
                self.lst_upload.parent.enabled = False
                self.ShowUploadConfirm()

            def on_macro_list(macros):
                self.lst_upload.items = []
                for macro in macros:
                    item = Prefabs.list_item_prefab.clone()
                    label = item.find_node("LabelNode").get_content()
                    label.text_value = macro.title
                    button = item.find_node("ButtonNode").get_content()
                    button.macro = macro
                    button.register_pressed_callback(select_macro)
                    self.lst_upload.items.append(item)

                if not macros:
                    self.lst_upload.parent.enabled = False
                    self.ShowUploadMessage('no macros found')
                else:
                    MenuManager.RefreshMenu(self.lst_upload)

            nanome.api.macro.Macro.get_live(on_macro_list)

        def ShowUploadComplex(self):
            def select_complex(button):
                self.upload_item = button.complex
                self.lst_upload.parent.enabled = False
                self.ln_upload_complex_type.enabled = True
                MenuManager.RefreshMenu()

            def on_complex_list(complexes):
                self.lst_upload.items = []
                for complex in complexes:
                    item = Prefabs.list_item_prefab.clone()
                    label = item.find_node("LabelNode").get_content()
                    label.text_value = complex.full_name
                    button = item.find_node("ButtonNode").get_content()
                    button.complex = complex
                    button.register_pressed_callback(select_complex)
                    self.lst_upload.items.append(item)

                if not complexes:
                    self.lst_upload.parent.enabled = False
                    self.ShowUploadMessage('no structures found')
                else:
                    MenuManager.RefreshMenu(self.lst_upload)

            self.plugin.request_complex_list(on_complex_list)

        def UploadComplex(self, extension, button):
            def on_complexes(complexes):
                complex = complexes[0]
                self.upload_item = complex
                self.upload_name = complex.name
                self.upload_ext = extension
                self.ln_upload_complex_type.enabled = False
                self.ShowUploadConfirm()

            self.plugin.request_complexes([self.upload_item.index], on_complexes)

        def ShowUploadMessage(self, message=None):
            self.ln_upload_message.enabled = True

            if message is None:
                self.lbl_upload_message.text_value = 'select an item to upload'
                return

            self.lbl_upload_message.text_value = message
            MenuManager.RefreshMenu()

        def ShowUploadConfirm(self):
            self.ln_upload_confirm.enabled = True
            self.lbl_upload_confirm.text_value = f'upload {self.upload_name}.{self.upload_ext}?'
            MenuManager.RefreshMenu()

        def ConfirmUpload(self, button):
            self.plugin.save_file(self.upload_item, self.upload_name, self.upload_ext)
            self.ToggleUpload(show=False)
            self.Update()

    class ImagePage(Page):
        def __init__(self, image, name):
            MenuManager.Page.__init__(self, name, Prefabs.tab_prefab, Prefabs.image_prefab)
            self.type = PageTypes.Image
            self.image = image
            self.image_content = self.base.find_node("ImageContent").add_new_image(image)
            self.image_content.scaling_option = nanome.util.enums.ScalingOptions.fit

    class PPTPage(Page):
        def __init__(self, images, name):
            MenuManager.Page.__init__(self, name, Prefabs.tab_prefab, Prefabs.ppt_prefab)
            self.type = PageTypes.PPT
            self.images = images
            self.prev_button = self.base.find_node("PrevButton").get_content()
            self.next_button = self.base.find_node("NextButton").get_content()
            self.page_text = self.base.find_node("PageText").get_content()
            self.ppt_content = self.base.find_node("PPTContent").add_new_image()
            self.ppt_content.scaling_option = nanome.util.enums.ScalingOptions.fit

            self.current_slide = 0
            def move_next(button):
                next_slide = (self.current_slide+1) % len(self.images)
                self.change_slide(next_slide)
                MenuManager.RefreshMenu(self.ppt_content)
                MenuManager.RefreshMenu(self.page_text)
            def move_prev(button):
                next_slide = (self.current_slide-1) % len(self.images)
                self.change_slide(next_slide)
                MenuManager.RefreshMenu(self.ppt_content)
                MenuManager.RefreshMenu(self.page_text)
            self.prev_button.register_pressed_callback(move_prev)
            self.next_button.register_pressed_callback(move_next)
            self.change_slide(0)

        def change_slide(self, index):
            num_slides = len(self.images)
            self.current_slide = index
            self.ppt_content.file_path = self.images[index]
            self.page_text.text_value = str(self.current_slide+1) + "/" + str(num_slides)
