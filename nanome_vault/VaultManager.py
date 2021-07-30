import requests

API = 'http://localhost/'

class VaultManager:
    def __init__(self, api_key):
        self.api_key = api_key

    def command(self, command, path, data=None, files=None):
        headers = {}
        if self.api_key:
            headers['vault-api-key'] = self.api_key
        if data is None:
            data = {}
        data['command'] = command
        url = API + 'files/' + path
        return requests.post(url, headers=headers, data=data, files=files)

    def get(self, path, key):
        headers = {}
        if self.api_key:
            headers['vault-api-key'] = self.api_key
        if key:
            headers['vault-key'] = key
        url = API + 'files/' + (path or '')
        return requests.get(url, headers=headers)


    # add data to vault at path/filename, where filename can contain a path
    def add_file(self, path, filename, data, key=None):
        return self.command('upload', path, {'key': key}, {'files': (filename, data)})

    # creates a path and returns True. returns False if path exists
    def create_path(self, path, key=None):
        return self.command('create', path, {'key': key})

    # decrypts full contents of path, return False if key invalid
    def decrypt_folder(self, path, key):
        return self.command('decrypt', path, {'key': key})

    # deletes a path and returns True on success, False on error
    def delete_path(self, path, key=None):
        return self.command('delete', path, {'key': key})

    # encrypts full contents of path, return False if encrypted subfolder exists
    def encrypt_folder(self, path, key):
        return self.command('encrypt', path, {'key': key})

    # get supported file extensions
    def get_extensions(self, ):
        r = requests.get(API + 'info')
        return r.json()['extensions']

    # write decrypted file to out_put
    def get_file(self, path, key, out_path):
        r = self.get(path, key)
        with open(out_path, 'wb') as f:
            f.write(r.content)

    # check if key is correct to decrypt
    def is_key_valid(self, path, key):
        r = self.command('verify', path, {'key': key})
        return r.json()['success']

    # list files, folders, and locked folders in path
    def list_path(self, path=None, key=None):
        r = self.get(path, key)
        return r.json()

    # renames a file/folder at path and returns True on success, False on error
    def rename_path(self, path, name, key=None):
        return self.command('rename', path, {'name': name, 'key': key})
