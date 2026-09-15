"""Stat-based change detection, independent of the cached pre-update utils module.

Legacy updaters retain utils while importing fresh config/gateway modules. Keep
this helper in its own module so those consumers do not require a newer utils.
"""

import os


def file_signature(st: os.stat_result) -> "tuple[int, int, int, int]":
    """Change-detection key for a stat result: ``(st_mtime_ns, st_size, st_ino, st_ctime_ns)``.

    mtime + size alone miss a replacement that preserves both (``cp -p``, ``rsync -t``, a tar
    restore, a script pinning the timestamp with ``os.utime``). The inode changes on an atomic
    replace and ctime cannot be backdated from user space, so the pair catches those writers.
    On Windows ``st_ino`` may be 0 and ``st_ctime_ns`` is the creation time — both stable across
    an in-place rewrite, so the key degrades to mtime + size there rather than misfiring.
    """
    return (st.st_mtime_ns, st.st_size, st.st_ino, st.st_ctime_ns)
