import scrypt, pbkdf2,  hashlib

def and_split(_bytes):
    ba1 = bytearray()
    ba2 = bytearray()
    for byte in _bytes:
        ba1.append(byte & 0xF0)
        ba2.append(byte & 0x0F)
    return (bytes(ba1), bytes(ba2))

def xor_merge(bytes1, bytes2):
    ba = bytearray()
    for i in range(len(bytes1)):
        ba.append(bytes1[i]^bytes2[i])
    return bytes(ba)

def derive_key(email, passphrase, hd=True):
    if hd:
        key_length = 64
    else:
        key_length = 32

    e1, e2 = and_split(bytes(email, "utf-8"))
    p1, p2 = and_split(bytes(passphrase, "utf-8"))

    scrypt_key = scrypt.hash(
                    p1, e1,
                    N=1 << 18, buflen=key_length)
    pbkdf2_key = pbkdf2.PBKDF2(
                    p2, e2,
                    iterations=1 << 16,
                    digestmodule=hashlib.sha256).read(key_length)
    merged = xor_merge(scrypt_key, pbkdf2_key)
    
    if hd:
        se = int(merged[0:32].hex(), 16)
        cc = merged[32:]
        return (se, cc)
    else:
        return merged

def main():
    email = input("Enter email: ")
    passphrase = input("Enter passphrase: ")
    master_key = derive_key(email, passphrase, hd=False)
    print(master_key.hex())

if __name__ == "__main__":
    main()
