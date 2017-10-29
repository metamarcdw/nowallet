import pytest
from nowallet import keys

def test_and_split():
    bytes_ = b"\xff\xff\xff\xff"
    b1, b2 = keys.and_split(bytes_)
    assert isinstance(b1, bytes)
    assert isinstance(b2, bytes)
    assert b1 == b"\xf0\xf0\xf0\xf0"
    assert b2 == b"\x0f\x0f\x0f\x0f"

def test_xor_merge():
    b1 = b"\xf0\xf0\xf0\xf0"
    b2 = b"\x0f\x0f\x0f\x0f"
    bytes_ = keys.xor_merge(b1, b2)
    assert isinstance(bytes_, bytes)
    assert bytes_ == b"\xff\xff\xff\xff"
    with pytest.raises(ValueError):
        keys.xor_merge(b"\x00", b"\x00\x00")

def test_derive_keys():
    salt = "test"
    passphrase = "CORRECT HORSE BATTERY STAPLE"
    secret_exp = int("35645493381215587888643547950114" + 
        "523511569659408346598921044976623615331125007")
    chain_code = (b"^I\xa3k\xf3jO\xd3%\xd3\x81\x98\xf9\x1f" + 
        b"\xb4\x01:\xd4T\x14\xdc\r\xe6\x16Pn9\x9f\x16kRW")
    assert keys.derive_key(salt, passphrase, hd=False) == secret_exp

    derived_exp, derived_code = keys.derive_key(salt, passphrase)
    assert isinstance(derived_exp, int)
    assert isinstance(derived_code, bytes)
    assert derived_exp == secret_exp
    assert derived_code == chain_code
