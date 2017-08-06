import scrypt, pbkdf2,  hashlib

def and_split(bytes_):
    ba1 = bytearray()
    ba2 = bytearray()
    for byte in bytes_:
        ba1.append(byte & 0xF0)
        ba2.append(byte & 0x0F)
    return (bytes(ba1), bytes(ba2))

def xor_merge(bytes1, bytes2):
    assert len(bytes1) == len(bytes2), "Length mismatch"
    ba = bytearray()
    for i in range(len(bytes1)):
        ba.append(bytes1[i]^bytes2[i])
    return bytes(ba)

def derive_key(salt, passphrase, hd=True):
    key_length = 64 if hd else 32
    s1, s2 = and_split(bytes(salt, "utf-8"))
    p1, p2 = and_split(bytes(passphrase, "utf-8"))

    scrypt_key = scrypt.hash(
                    p1, s1,
                    N=1 << 18, buflen=key_length)
    pbkdf2_key = pbkdf2.PBKDF2(
                    p2, s2,
                    iterations=1 << 16,
                    digestmodule=hashlib.sha256).read(key_length)
    merged = xor_merge(scrypt_key, pbkdf2_key)
    
    if hd:
        se = int(merged[0:32].hex(), 16)
        cc = merged[32:]
        return (se, cc)
    else:
        return int(merged.hex(), 16)

def main():
    email = input("Enter email: ")
    passphrase = input("Enter passphrase: ")
    secret_exponent = derive_key(email, passphrase, hd=False)
    print(secret_exponent)

if __name__ == "__main__":
    main()
