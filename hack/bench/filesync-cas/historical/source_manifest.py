"""Byte/type/mode manifest for the raw-import fixture, outside timed regions."""
import hashlib
import os
from pathlib import Path
import stat


def manifest(root):
    root = Path(root)
    result = {}
    excluded = {'.git', 'target', 'dagger.toml', 'dagger.lock'}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in excluded)
        for name in dirs + sorted(name for name in files if name not in excluded):
            path = Path(directory) / name
            before = path.lstat()
            item = {'mode': stat.S_IMODE(before.st_mode)}
            if stat.S_ISLNK(before.st_mode):
                item.update(kind='symlink', target=os.readlink(path))
            elif stat.S_ISREG(before.st_mode):
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                after = path.lstat()
                assert (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
                    after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), str(path)
                item.update(kind='file', size=before.st_size, sha256=digest)
            elif stat.S_ISDIR(before.st_mode):
                item.update(kind='directory')
            else:
                raise AssertionError('unsupported fixture entry: ' + str(path))
            result[path.relative_to(root).as_posix()] = item
    return dict(sorted(result.items()))
