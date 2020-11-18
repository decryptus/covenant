# -*- coding: utf-8 -*-
# Copyright (C) 2018-2020 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.plugins.pfilestat"""

import errno
import grp
import os
import pwd
import stat
import logging

from six import ensure_binary

from covenant.classes.plugins import CovenantPlugBase, CovenantTargetFailed, PLUGINS

LOG = logging.getLogger('covenant.plugins.pfilestat')

# Platform dependent flags
_PLATFORM_FLAGS = (
    # Some Linux
    ('st_blocks', 'blocks'),
    ('st_blksize', 'block_size'),
    ('st_rdev', 'device_type'),
    ('st_flags', 'flags'),
    # Some Berkley based
    ('st_gen', 'generation'),
    ('st_birthtime', 'birthtime'),
    # RISCOS
    ('st_ftype', 'file_type'),
    ('st_attrs', 'attrs'),
    ('st_obtype', 'object_type'),
    # macOS
    ('st_rsize', 'real_size'),
    ('st_creator', 'creator'),
    ('st_type', 'file_type'))

_PERMS = (('readable', os.R_OK),
          ('writeable', os.W_OK),
          ('executable', os.X_OK))


class CovenantFilestatPlugin(CovenantPlugBase):
    PLUGIN_NAME = 'filestat'

    @staticmethod
    def _st_flags(st):
        mode = st.st_mode

        r = {'mode': "%04o" % stat.S_IMODE(mode),
             'isdir': stat.S_ISDIR(mode),
             'ischr': stat.S_ISCHR(mode),
             'isblk': stat.S_ISBLK(mode),
             'isreg': stat.S_ISREG(mode),
             'isfifo': stat.S_ISFIFO(mode),
             'islnk': stat.S_ISLNK(mode),
             'issock': stat.S_ISSOCK(mode),
             'uid': st.st_uid,
             'gid': st.st_gid,
             'size': st.st_size,
             'inode': st.st_ino,
             'dev': st.st_dev,
             'nlink': st.st_nlink,
             'atime': st.st_atime,
             'mtime': st.st_mtime,
             'ctime': st.st_ctime,
             'wusr': bool(mode & stat.S_IWUSR),
             'rusr': bool(mode & stat.S_IRUSR),
             'xusr': bool(mode & stat.S_IXUSR),
             'wgrp': bool(mode & stat.S_IWGRP),
             'rgrp': bool(mode & stat.S_IRGRP),
             'xgrp': bool(mode & stat.S_IXGRP),
             'woth': bool(mode & stat.S_IWOTH),
             'roth': bool(mode & stat.S_IROTH),
             'xoth': bool(mode & stat.S_IXOTH),
             'isuid': bool(mode & stat.S_ISUID),
             'isgid': bool(mode & stat.S_ISGID)}

        for x in _PLATFORM_FLAGS:
            if hasattr(st, x[0]):
                r[x[1]] = getattr(st, x[0])

        return r

    def _result(self, cfg):
        data = {'exists': False,
                'path': cfg.pop('path')}

        b_path = ensure_binary(data['path'], errors = 'surrogate_or_strict')

        follow = False
        if 'follow' in cfg:
            follow = bool(cfg.pop('follow'))

        try:
            if follow:
                st = os.stat(b_path)
            else:
                st = os.lstat(b_path)
        except OSError as e:
            if e.errno == errno.ENOENT:
                return data
            raise

        data.update(self._st_flags(st))
        data['exists'] = True

        for perm in _PERMS:
            data[perm[0]] = os.access(b_path, perm[1])

        if data.get('islnk'):
            data['lnk_source'] = os.path.realpath(b_path)
            data['lnk_target'] = os.readlink(b_path)

        try:
            pw = pwd.getpwuid(st.st_uid)
            data['pw_name'] = pw.pw_nam
        except Exception:
            pass

        try:
            gr = grp.getgrgid(st.st_gid)
            data['gr_name'] = gr.gr_name
        except Exception:
            pass

        return data

    def _do_call(self, obj, targets = None, registry = None): # pylint: disable=unused-argument
        if not targets:
            targets = self.targets

        for target in targets:
            try:
                data = self._result(target.config)
            except Exception as e:
                data = CovenantTargetFailed(e)
                LOG.exception("error on target: %r. exception: %r",
                              target.name,
                              e)

            target(data)

        return self.generate_latest(registry)


if __name__ != "__main__":
    def _start():
        PLUGINS.register(CovenantFilestatPlugin)
    _start()
