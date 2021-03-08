import requests

API = 'http://vault-server/'

def command(command, path, data=None, files=None):
    if data is None:
        data = {}
    data['command'] = command
    url = API + 'files/' + path
    return requests.post(url, data=data, files=files)

def get(path, key):
    headers = {}
    if key:
        headers['vault-key'] = key
    url = API + 'files/' + (path or '')
    return requests.get(url, headers=headers)


# add data to vault at path/filename, where filename can contain a path
def add_file(path, filename, data, key=None):
    command('upload', path, {'key': key}, (filename, data))

# creates a path and returns True. returns False if path exists
def create_path(path):
    command('create', path)

# decrypts full contents of path, return False if key invalid
def decrypt_folder(path, key):
    command('decrypt', path, {'key': key})

# deletes a path and returns True on success, False on error
def delete_path(path, key=None):
    command('delete', path, {'key': key})

# encrypts full contents of path, return False if encrypted subfolder exists
def encrypt_folder(path, key):
    command('encrypt', path, {'key': key})

# get supported file extensions
def get_extensions():
    r = requests.get(API + 'info')
    return r.json()['extensions']

# write decrypted file to out_put
def get_file(path, key, out_path):
    r = get(path, key)
    with open(out_path, 'wb') as f:
        f.write(r.content)

# check if key is correct to decrypt
def is_key_valid(path, key):
    r = command('verify', path, {'key': key})
    return r.json()['success']

# list files, folders, and locked folders in path
def list_path(path=None, key=None):
    r = get(path, key)
    return r.json()

# renames a file/folder at path and returns True on success, False on error
def rename_path(path, name):
    command('rename', path, {'name': name})
