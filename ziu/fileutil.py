import os
import shutil
import stat


def copyfile(src, dst, overwrite=False):
    if os.path.exists(dst):
        raise FileExistsError
    if os.path.islink(src):
        linkto = os.readlink(src)
        os.symlink(linkto, dst)
    else:
         shutil.copy2(src, dst)


def copytree(src, dst, follow_symlinks=False, ignore=None, overwrite=False):
    """Like shutil.copytree but merge directories."""
    if not os.path.exists(dst):
        os.makedirs(dst)
        shutil.copystat(src, dst)

    lst = os.listdir(src)

    if ignore:
        excl = ignore(src, lst)
        lst = [x for x in lst if x not in excl]

    for item in lst:
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.islink(s) and follow_symlinks:
            if os.path.lexists(d):
                os.remove(d)
            os.symlink(os.readlink(s), d)
            try:
                st = os.lstat(s)
                mode = stat.S_IMODE(st.st_mode)
                os.lchmod(d, mode)
            except:  # noqa
                pass  # lchmod not available
        elif os.path.isdir(s):
            copytree(s, d, follow_symlinks, ignore, overwrite)
        elif os.path.isfile(s):
            copyfile(src, dst, overwrite)
