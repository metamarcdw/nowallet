import hashlib
from typing import Union, Tuple

import scrypt
import pbkdf2

def and_split(bytes_: bytes) -> Tuple[bytes, bytes]:
    ba1: bytearray = bytearray()
    ba2: bytearray = bytearray()
    for byte in bytes_:
        ba1.append(byte & 0xF0)
        ba2.append(byte & 0x0F)
    return (bytes(ba1), bytes(ba2))

def xor_merge(bytes1: bytes, bytes2: bytes) -> bytes:
    if len(bytes1) != len(bytes2):
        raise ValueError("Length mismatch")
    byte_array: bytearray = bytearray()
    for i in range(len(bytes1)):
        byte_array.append(bytes1[i] ^ bytes2[i])
    return bytes(byte_array)

def derive_key(salt: str, passphrase: str, hd: bool=True) -> \
    Union[int, Tuple[int, bytes]]:
    key_length: int = 64 if hd else 32

    t1: Tuple[bytes, bytes] = and_split(bytes(salt, "utf-8"))
    salt1, salt2 = t1
    t2: Tuple[bytes, bytes] = and_split(bytes(passphrase, "utf-8"))
    pass1, pass2 = t2

    scrypt_key: bytes = scrypt.hash(
        pass1, salt1,
        N=1 << 18, buflen=key_length)
    pbkdf2_key: bytes = pbkdf2.PBKDF2(
        pass2, salt2,
        iterations=1 << 16,
        digestmodule=hashlib.sha256).read(key_length)
    merged: bytes = xor_merge(scrypt_key, pbkdf2_key)

    if hd:
        secret_exp: int = int(merged[0:32].hex(), 16)
        chain_code: bytes = merged[32:]
        return (secret_exp, chain_code)

    return int(merged.hex(), 16)

def main():
    email: str = input("Enter email: ")
    passphrase: str = input("Enter passphrase: ")
    t: Tuple[int, bytes] = derive_key(email, passphrase)
    secret_exp, chain_code = t
    print("Secret exp: {}\nChain code: {}".format(secret_exp, chain_code))

if __name__ == "__main__":
    main()
