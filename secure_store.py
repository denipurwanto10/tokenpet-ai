"""Penyimpanan kredensial lokal TokenPet.

Pada Windows, nilai dienkripsi per-user melalui DPAPI sebelum ditulis ke
disk.  File yang tersisa hanya berisi blob base64 terenkripsi, bukan
kredensial plaintext.  Modul ini sengaja hanya memakai standard library.
"""

import base64
import ctypes
from ctypes import wintypes
import json
import os


class SecureStorageError(RuntimeError):
    """DPAPI atau file store tidak dapat dipakai dengan aman."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]


def _win32():
    """crypt32/kernel32 dengan signature ctypes yang benar.

    Tanpa argtypes, ctypes menganggap argumen = c_int 32-bit sehingga
    pointer 64-bit dari DPAPI gagal (OverflowError: int too long) saat
    dilepas lewat LocalFree.
    """
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(_DataBlob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(_DataBlob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


class SecureCredentialStore:
    """Small DPAPI-backed key/value store for TokenPet credentials.

    Interface intentionally stays tiny so account metadata can remain in the
    regular JSON file while secrets never need to be placed there.
    """

    def __init__(self, path):
        self.path = path

    @staticmethod
    def _blob(raw):
        raw = bytes(raw)
        buf = ctypes.create_string_buffer(raw, len(raw) or 1)
        return _DataBlob(len(raw), ctypes.cast(buf, ctypes.c_void_p)), buf

    def _protect(self, value):
        if os.name != "nt":
            raise SecureStorageError("secure storage requires Windows DPAPI")
        crypt32, kernel32 = _win32()
        src, keep = self._blob(value.encode("utf-8"))
        dst = _DataBlob()
        ok = crypt32.CryptProtectData(ctypes.byref(src), "TokenPet", None,
                                      None, None, 0, ctypes.byref(dst))
        if not ok:
            raise SecureStorageError("Windows DPAPI failed to encrypt")
        try:
            return ctypes.string_at(dst.pbData, dst.cbData)
        finally:
            kernel32.LocalFree(dst.pbData)

    def _unprotect(self, value):
        if os.name != "nt":
            raise SecureStorageError("secure storage requires Windows DPAPI")
        try:
            raw = base64.b64decode(value.encode("ascii"), validate=True)
        except (ValueError, UnicodeError) as exc:
            raise SecureStorageError("credential store is malformed") from exc
        crypt32, kernel32 = _win32()
        src, keep = self._blob(raw)
        dst = _DataBlob()
        ok = crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None,
                                        None, 0, ctypes.byref(dst))
        if not ok:
            raise SecureStorageError("Windows DPAPI could not decrypt credential")
        try:
            return ctypes.string_at(dst.pbData, dst.cbData).decode("utf-8")
        finally:
            kernel32.LocalFree(dst.pbData)

    def _read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError) as exc:
            raise SecureStorageError("credential store cannot be read") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("items", {}), dict):
            raise SecureStorageError("credential store is malformed")
        return dict(raw["items"])

    def _write(self, items):
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"schema_version": 1, "items": items}, f)
            os.replace(tmp, self.path)
        except OSError as exc:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise SecureStorageError("credential store cannot be saved") from exc

    def save(self, provider, credential):
        key, secret = str(provider).strip(), str(credential or "")
        if not key:
            raise SecureStorageError("provider is required")
        if not secret:
            self.delete(key)
            return
        items = self._read()
        items[key] = base64.b64encode(self._protect(secret)).decode("ascii")
        self._write(items)

    def get(self, provider):
        key = str(provider).strip()
        if not key:
            return None
        encoded = self._read().get(key)
        return self._unprotect(encoded) if encoded else None

    def delete(self, provider):
        key = str(provider).strip()
        items = self._read()
        if key in items:
            del items[key]
            self._write(items)

    def delete_all(self):
        items = self._read()
        if items:
            self._write({})
