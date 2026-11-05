# -*- coding: utf-8 -*-
# Copyright (C) 2018-2020 fjord-technologies
# SPDX-License-Identifier: GPL-3.0-or-later
"""covenant.plugins.pfilestat"""

from contextlib import contextmanager

import errno
import json
import grp
import hashlib
import os
import pwd
import stat
import re
import logging

from six import (ensure_binary,
                 string_types)

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
    _PATTERNS   = {}

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

    def _load_patterns(self, patterns):
        r = set()

        if patterns is None or patterns == '':
            return r

        if isinstance(patterns, string_types):
            patterns = [patterns]

        if not isinstance(patterns, (list, tuple)):
            raise ValueError("file path rules must be a regex or list of regexes")

        xsum = hashlib.md5(json.dumps(patterns).encode('utf-8')).hexdigest()

        if xsum in self._PATTERNS:
            return self._PATTERNS[xsum]

        for pattern in patterns:
            r.add(re.compile(ensure_binary(pattern, errors = 'surrogate_or_strict')).match)

        self._PATTERNS[xsum] = r

        return r

    @staticmethod
    def _require_allowed(path, relative, includes, excludes):
        name = os.path.relpath(path) if relative else path
        if includes and not any(match(name) for match in includes):
            raise ValueError("file path outside include_paths")
        if any(match(name) or match(path) for match in excludes):
            raise ValueError("file path denied by exclude_paths")

    @staticmethod
    @contextmanager
    def _entry(path, expected, follow):
        # On Linux pin the inode before collecting permissions or metadata.
        # A symlink swapped into an ancestor cannot redirect the returned data.
        if (hasattr(os, 'O_PATH') and os.readlink in getattr(os, 'supports_dir_fd', ())
                and os.path.isdir('/proc/self/fd')):
            flags = os.O_PATH if follow else os.O_PATH | os.O_NOFOLLOW
            fd = os.open(path, flags)
            try:
                ref = b'/proc/self/fd/%d' % fd
                if os.readlink(ref) != expected:
                    raise ValueError("file path changed during collection")
                st = os.fstat(fd)
                link = None
                if stat.S_ISLNK(st.st_mode):
                    if follow:
                        raise ValueError("file path changed during collection")
                    link = os.readlink(b'', dir_fd=fd)
                yield st, ref, link
            finally:
                os.close(fd)
        else:
            st = os.stat(path) if follow else os.lstat(path)
            if not os.path.samestat(st, os.lstat(expected)):
                raise ValueError("file path changed during collection")
            link = None
            if stat.S_ISLNK(st.st_mode):
                if follow:
                    raise ValueError("file path changed during collection")
                link = os.readlink(expected)
            yield st, expected, link

    @staticmethod
    def _permissions(path):
        return {name: os.access(path, mode) for name, mode in _PERMS}

    def _restricted_details(self, path, follow, includes, excludes):
        if (not path or path.startswith(b'//') or os.path.normpath(path) != path
                or b'..' in path.split(b'/')):
            raise ValueError("filtered file probes require a normalized path")
        relative = not os.path.isabs(path)
        absolute = os.path.abspath(path)
        self._require_allowed(absolute, relative, includes, excludes)

        parent, name = os.path.split(absolute)
        entry = os.path.join(os.path.realpath(parent), name) if name else absolute
        self._require_allowed(entry, relative, includes, excludes)
        if follow:
            resolved = os.path.realpath(absolute)
            self._require_allowed(resolved, relative, includes, excludes)
            with self._entry(absolute, resolved, follow=True) as (st, ref, _):
                return st, self._permissions(ref)

        with self._entry(absolute, entry, follow=False) as (st, ref, link):
            if link is None:
                return st, self._permissions(ref)
            # The link text and the target permissions describe separate inodes.
            destination = os.path.join(os.path.dirname(entry), link)
            resolved = os.path.realpath(destination)
            self._require_allowed(resolved, relative, includes, excludes)
            try:
                with self._entry(destination, resolved, follow=True) as (_, target_ref, _link):
                    details = self._permissions(target_ref)
            except OSError as error:
                if error.errno != errno.ENOENT:
                    raise
                details = {key: False for key, _ in _PERMS}
            details.update(lnk_source=resolved, lnk_target=link)
            return st, details

    def _result(self, cfg, param_target = None):
        if param_target and not cfg.get('path'):
            cfg['path'] = param_target

        include_paths = self._load_patterns(cfg.get('include_paths'))
        exclude_paths = self._load_patterns(cfg.get('exclude_paths'))

        data = {'exists': False,
                'path': cfg.pop('path')}

        b_path = ensure_binary(data['path'], errors = 'surrogate_or_strict')

        follow = False
        if 'follow' in cfg:
            follow = bool(cfg.pop('follow'))

        try:
            if include_paths or exclude_paths:
                st, details = self._restricted_details(b_path, follow, include_paths, exclude_paths)
            else:
                st = os.stat(b_path) if follow else os.lstat(b_path)
                details = self._permissions(b_path)
                if stat.S_ISLNK(st.st_mode):
                    details.update(lnk_source=os.path.realpath(b_path), lnk_target=os.readlink(b_path))
        except OSError as e:
            if e.errno == errno.ENOENT:
                return data
            raise

        data.update(self._st_flags(st))
        data.update(details)
        data['exists'] = True

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

        param_target = obj.get_params().get('target')

        for target in targets:
            try:
                data = self._result(target.config, param_target)
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
