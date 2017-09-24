import hashlib

import scrypt
import pbkdf2

def and_split(bytes_):
    ba1 = bytearray()
    ba2 = bytearray()
    for byte in bytes_:
        ba1.append(byte & 0xF0)
        ba2.append(byte & 0x0F)
    return (bytes(ba1), bytes(ba2))

def xor_merge(bytes1, bytes2):
    assert len(bytes1) == len(bytes2), "Length mismatch"
    byte_array = bytearray()
    for i in range(len(bytes1)):
        byte_array.append(bytes1[i] ^ bytes2[i])
    return bytes(byte_array)

def derive_key(salt, passphrase, hd=True):
    key_length = 64 if hd else 32
    salt1, salt2 = and_split(bytes(salt, "utf-8"))
    pass1, pass2 = and_split(bytes(passphrase, "utf-8"))

    scrypt_key = scrypt.hash(
        pass1, salt1,
        N=1 << 18, buflen=key_length)
    pbkdf2_key = pbkdf2.PBKDF2(
        pass2, salt2,
        iterations=1 << 16,
        digestmodule=hashlib.sha256).read(key_length)
    merged = xor_merge(scrypt_key, pbkdf2_key)

    if hd:
        secret_exp = int(merged[0:32].hex(), 16)
        chain_code = merged[32:]
        return (secret_exp, chain_code)

    return int(merged.hex(), 16)

def main():
    email = input("Enter email: ")
    passphrase = input("Enter passphrase: ")
    secret_exponent = derive_key(email, passphrase, hd=False)
    print(secret_exponent)

if __name__ == "__main__":
    main()
