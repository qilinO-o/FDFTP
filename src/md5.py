import hashlib

def get_file_md5(f):
    md5_hash = hashlib.md5()
    f.seek(0,0)
    while True:
        byte_data = f.read(4096)
        if not byte_data:
            break
        md5_hash.update(byte_data)
    return md5_hash.hexdigest()
