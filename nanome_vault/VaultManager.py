import os
import re
import shutil
from . import AESCipher

LOCK_TEXT = 'nanome-vault-lock'

FILES_DIR = os.path.normpath(os.path.expanduser('~/Documents/nanome-vault'))
if not os.path.exists(os.path.join(FILES_DIR, 'shared')):
    os.makedirs(os.path.join(FILES_DIR, 'shared'))

class InvalidPathError(Exception):
    pass

# return true if path in vault and exists
def is_safe_path(sub_path, base_path=FILES_DIR, enforce_exists=True):
    safe = os.path.realpath(base_path)
    path = os.path.realpath(os.path.join(base_path, sub_path))
    common = os.path.commonprefix((safe, path))
    is_safe = common == safe
    exists = os.path.exists(path)
    return is_safe and (not enforce_exists or exists)

# return full path of item in vault
def get_vault_path(path, **kwargs):
    path = FILES_DIR if path is None else os.path.join(FILES_DIR, path)
    if not is_safe_path(path, **kwargs):
        raise InvalidPathError
    return os.path.normpath(path)

# return encryption root of path, or none if not encrypted
def get_locked_path(path):
    if os.path.commonprefix([FILES_DIR, path]) == FILES_DIR:
        path = path[len(FILES_DIR):]

    path = os.path.normpath(path)
    parts = path.split(os.path.sep)
    subpath = ''
    for part in parts:
        subpath = os.path.join(subpath, part)
        path = os.path.join(FILES_DIR, subpath)
        if os.path.exists(os.path.join(path, '.locked')):
            return subpath + '/'
    return None

# checks if folder encrypted
def is_path_locked(path):
    return get_locked_path(path) != None

# check if key is correct to decrypt
def is_key_valid(path, key):
    path = get_locked_path(path)
    if path is None:
        return True

    try:
        lock = os.path.join(FILES_DIR, path, '.locked')
        with open(lock, 'rb') as f:
            result = AESCipher.decrypt(f.read(), key)
        return result.decode('utf-8') == LOCK_TEXT
    except:
        return False

# list files, folders, and locked folders in path
def list_path(path=None):
    path = get_vault_path(path)

    result = dict()
    result['locked_path'] = get_locked_path(path)
    result['locked'] = []
    result['folders'] = []
    result['files'] = []

    if path == FILES_DIR:
        result['folders'].append('shared')
        return result

    items = [item for item in os.listdir(path) if not item.startswith('.')]
    for item in sorted(items, key=lambda s: s.lower()):
        is_dir = os.path.isdir(os.path.join(path, item))
        if is_dir and os.path.exists(os.path.join(path, item, '.locked')):
            result['locked'].append(item)
        result['folders' if is_dir else 'files'].append(item)

    return result

# creates a path and returns True. returns False if path exists
def create_path(path):
    path = get_vault_path(path, enforce_exists=False)
    if os.path.exists(path):
        return False
    os.makedirs(path)
    return True

# TODO: add key to delete locked path
# deletes a path and returns True on success, False on error
def delete_path(path):
    path = get_vault_path(path)

    try:
        if os.path.isfile(path):
            os.remove(path)
        else:
            shutil.rmtree(path)
        return True
    except:
        return False

# renames a file/folder at path and returns True on success, False on error
def rename_path(path, name):
    oldpath = get_vault_path(path)
    dir = os.path.dirname(oldpath)
    newpath = os.path.join(dir, name)

    try:
        os.rename(oldpath, newpath)
        return True
    except:
        return False

# add data to vault at path/filename, where filename can contain a path
def add_file(path, filename, data, key=None):
    path = get_vault_path(path, enforce_exists=False)

    if key is not None:
        data = AESCipher.encrypt(data, key)

    # create folder paths
    subfolder = os.path.join(path, os.path.dirname(filename))
    if not os.path.exists(subfolder):
        os.makedirs(subfolder)

    filepath = os.path.join(path, filename)

    # rename on duplicates: file.txt -> file (n).txt
    reg = r'(.+[/\\])([^/\\]+?)(?: \((\d+)\))?(\.\w+)'
    (path, name, copy, ext) = re.search(reg, filepath).groups()
    copy = 1 if copy is None else int(copy)

    while os.path.isfile(filepath):
        copy += 1
        filepath = '%s%s (%d)%s' % (path, name, copy, ext)

    with open(filepath, "wb") as f:
        f.write(data)

# encrypts full contents of path, return False if encrypted subfolder exists
def encrypt_folder(path, key):
    path = get_vault_path(path)

    # check if subfolder already encrypted
    for root, _, files in os.walk(path):
        if '.locked' in files:
            return False

    # encrypt all files not starting with '.'
    for root, _, files in os.walk(path):
        for file in [f for f in files if not f.startswith('.')]:
            file = os.path.join(root, file)
            encrypt_file(file, key, file)

    # add lock file for key verification
    lock = os.path.join(path, '.locked')
    with open(lock, 'wb') as f:
        data = AESCipher.encrypt(LOCK_TEXT, key)
        f.write(data)

    return True

# decrypts full contents of path, return False if key invalid
def decrypt_folder(path, key):
    path = get_vault_path(path)

    if not is_path_locked(path) or not is_key_valid(path, key):
        return False

    # decrypt all files not starting with '.'
    for root, _, files in os.walk(path):
        for file in [f for f in files if not f.startswith('.')]:
            file = os.path.join(root, file)
            decrypt_file(file, key, file)

    # remove lock file
    lock = os.path.join(path, '.locked')
    os.remove(lock)

    return True

# encrypt infile with key and write result to outfile, or return if no outfile
def encrypt_file(infile, key, outfile=None):
    with open(infile, 'rb') as f:
        data = AESCipher.encrypt(f.read(), key)
    if outfile is None:
        return data
    with open(outfile, 'wb') as f:
        f.write(data)

# decrypt infile with key and write result to outfile, or return if no outfile
def decrypt_file(infile, key, outfile=None):
    with open(infile, 'rb') as f:
        data = AESCipher.decrypt(f.read(), key)
    if outfile is None:
        return data
    with open(outfile, 'wb') as f:
        f.write(data)
