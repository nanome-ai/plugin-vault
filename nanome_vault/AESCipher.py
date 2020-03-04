from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

# brute force protection, key is hashed 8192 times
def get_key(key):
    key = key.encode('utf-8')
    for _ in range(8192):
        key = SHA256.new(key).digest()
    return key

def encrypt(data, key):
    key = get_key(key)
    iv = get_random_bytes(AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    if isinstance(data, str):
        data = data.encode('utf-8')
    data = pad(data, AES.block_size)
    return iv + cipher.encrypt(data)

def decrypt(data, key):
    key = get_key(key)
    iv = data[:AES.block_size]
    raw = data[AES.block_size:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(raw), AES.block_size)
