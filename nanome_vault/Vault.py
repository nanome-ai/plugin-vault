import sys
import os
import socket
import tempfile
from functools import partial
from timeit import default_timer as timer

import nanome
from nanome.util import Logs
from nanome.util.enums import NotificationTypes
from nanome.api.structure import Complex

from .VaultServer import VaultServer
from .Menu.MenuManager import MenuManager, PageTypes
from .PPTConverter import PPTConverter
from . import VaultManager, Workspace

DEFAULT_SERVER_PORT = 80
DEFAULT_KEEP_FILES_DAYS = 0

# Plugin instance (for Nanome)
class Vault(nanome.PluginInstance):
    def start(self):
        self.set_plugin_list_button(self.PluginListButtonType.run, 'Open')

        # set to empty string to read/write macros in Macros folder
        nanome.api.macro.Macro.set_plugin_identifier('')

        # "hack" to check if Nanome supports send_files_to_load
        self.can_send_files = self._network._ProcessNetwork__version_table.get('LoadFile') != None

        self.running = False
        self.ppt_readers = {}
        self.account = 'user-00000000'
        self.menu_manager = MenuManager(self, self.get_server_url())
        self.on_run()

    def update(self):
        if not self.running:
            return

        if self.menu_manager.selected_page == self.menu_manager.home_page:
            if timer() - self.__timer >= 3.0:
                for ppt_reader in self.ppt_readers.values():
                    ppt_reader.update()

                self.menu_manager.home_page.Update()
                self.__timer = timer()

        if timer() - self.big_timer >= 600:
            filtered_ppt_readers = {}
            for file in self.menu_manager.GetOpenFiles():
                for key, value in self.ppt_readers.items():
                    if not value.done or key.startswith(file):
                        filtered_ppt_readers[key] = value
            self.ppt_readers = filtered_ppt_readers
            self.big_timer = timer()

    def on_run(self):
        self.running = True
        self.__timer = timer()
        self.big_timer = timer()
        self.on_presenter_change()
        self.menu_manager.Refresh()
        self.menu_manager.home_page.OpenFolder('.')

    def on_presenter_change(self):
        self.request_presenter_info(self.update_account)

    def update_account(self, info):
        if not info.account_id:
            return

        self.account = info.account_id
        VaultManager.create_path(self.account)
        self.menu_manager.home_page.Update()

    def load_file(self, name, callback):
        item_name, extension = name.rsplit(".", 1)

        path = self.menu_manager.home_page.path
        file_path = VaultManager.get_vault_path(os.path.join(path, name))

        temp = None
        if self.menu_manager.home_page.locked_path:
            key = self.menu_manager.home_page.folder_key
            temp = tempfile.TemporaryDirectory()
            temp_path = os.path.join(temp.name, name)
            VaultManager.decrypt_file(file_path, key, temp_path)
            file_path = temp_path

        msg = None

        # workspace
        if extension == 'nanome':
            with open(file_path, 'rb') as f:
                workspace = Workspace.from_data(f.read())
                self.update_workspace(workspace)
            msg = f'Workspace "{item_name}" loaded'
            callback()

        # macro
        elif extension == 'lua':
            with open(file_path, 'r') as f:
                macro = nanome.api.macro.Macro()
                macro.title = item_name
                macro.logic = f.read()
                macro.save()
            msg = f'Macro "{item_name}" added'
            callback()

        elif self.can_send_files and extension not in ['ppt', 'pptx', 'odp']:
            self.send_files_to_load(file_path, lambda _: callback())

        # structure
        elif extension == 'pdb':
            complex = Complex.io.from_pdb(path=file_path)
            complex.name = item_name
            self.add_bonds([complex], partial(self.bonds_ready, callback=callback))
        elif extension == 'sdf':
            complex = Complex.io.from_sdf(path=file_path)
            complex.name = item_name
            self.bonds_ready([complex], callback)
        elif extension == 'cif':
            complex = Complex.io.from_mmcif(path=file_path)
            complex.name = item_name
            self.add_bonds([complex], partial(self.bonds_ready, callback=callback))

        # document/image
        elif extension in ['ppt', 'pptx', 'odp', 'pdf']:
            self.display_ppt(file_path, callback)
        elif extension in ['png', 'jpg']:
            self.display_image(item_name, file_path, callback)

        else:
            error = f'Extension not yet supported: {extension}'
            self.send_notification(NotificationTypes.error, error)
            Logs.warning(error)
            callback()

        if msg is not None:
            self.send_notification(NotificationTypes.success, msg)

        if temp:
            temp.cleanup()

    def save_file(self, item, name, extension):
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=extension)

        # workspace
        if extension == 'nanome':
            with open(temp.name, 'wb') as f:
                f.write(Workspace.to_data(item))

        # macro
        elif extension == 'lua':
            with open(temp.name, 'wb') as f:
                f.write(item.logic.encode('utf-8'))

        # structures
        elif extension == 'pdb':
            item.io.to_pdb(temp.name)
        elif extension == 'sdf':
            item.io.to_sdf(temp.name)
        elif extension == 'cif':
            item.io.to_mmcif(temp.name)

        with open(temp.name, 'rb') as f:
            path = VaultManager.get_vault_path(self.menu_manager.home_page.path)
            key = self.menu_manager.home_page.folder_key
            file_name = f'{name}.{extension}'

            VaultManager.add_file(path, file_name, f.read(), key)
            self.send_notification(NotificationTypes.success, f'"{file_name}" saved')

        temp.close() # unsure if needed
        os.remove(temp.name)

    def bonds_ready(self, complexes, callback):
        self.add_dssp(complexes, partial(self.send_complexes, callback=callback))

    def send_complexes(self, complexes, callback):
        self.add_to_workspace(complexes)
        self.send_notification(NotificationTypes.success, f'"{complexes[0].name}" loaded')
        callback()

    def display_ppt(self, file_name, callback):
        key = os.path.basename(file_name) + str(os.path.getmtime(file_name))
        if key in self.ppt_readers:
            ppt_reader = self.ppt_readers[key]
        else:
            ppt_reader = PPTConverter(file_name)
            self.ppt_readers[key] = ppt_reader
        def done_delegate(images):
            if len(images) == 1:
                self.menu_manager.OpenPage(PageTypes.Image, images[0], file_name)
            elif len(images) > 1:
                self.menu_manager.OpenPage(PageTypes.PPT, images, file_name)
            if callback:
                callback()
        def error_delegate():
            #cleanup ppt_reader
            pass
        ppt_reader.Convert(done_delegate, error_delegate)

    def display_image(self, name, path, callback):
        self.menu_manager.OpenPage(PageTypes.Image, path, name)
        if callback:
            callback()

    def get_server_url(self):
        url, port = self.custom_data
        if url is not None:
            return url

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            url = s.getsockname()[0]
        except:
            url = '127.0.0.1'
        finally:
            s.close()

        if port != DEFAULT_SERVER_PORT:
            url += ":" + str(port)
        return url

def main():
    # Plugin server (for Web)
    port = DEFAULT_SERVER_PORT
    ssl_cert = None
    url = None
    keep_files_days = DEFAULT_KEEP_FILES_DAYS

    try:
        for i in range(len(sys.argv)):
            if sys.argv[i] == "-w":
                port = int(sys.argv[i + 1])
            elif sys.argv[i] == "-s":
                ssl_cert = sys.argv[i + 1]
            elif sys.argv[i] == "-u":
                url = sys.argv[i + 1]
            elif sys.argv[i] == "-k":
                keep_files_days = int(sys.argv[i + 1])
    except:
        pass

    if ssl_cert is not None and port == DEFAULT_SERVER_PORT:
        port = 443

    server = None
    def pre_run():
        nonlocal server
        server = VaultServer(port, ssl_cert, keep_files_days)
        server.start()
    def post_run():
        server.stop()

    # Plugin
    plugin = nanome.Plugin("Nanome Vault", "Use your browser to upload files and folders to make them available in Nanome.", "Loading", False)
    plugin.set_plugin_class(Vault)
    plugin.set_custom_data(url, port)
    plugin.pre_run = pre_run
    plugin.post_run = post_run
    plugin.run('127.0.0.1', 8888)

if __name__ == "__main__":
    main()
