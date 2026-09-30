/* LGPL-2.1-or-later. No-storage stdio for the production-only runtime. */
#ifndef FEXTENDO_SILENT_IO_H
#define FEXTENDO_SILENT_IO_H
#include <sys/iosupport.h>
#include <string.h>

#define FX_NULL_PATH "fextendo-null:/stdio"

static int fx_null_open(struct _reent *r, void *fd, const char *path, int flags, int mode)
{
    (void)r; (void)fd; (void)path; (void)flags; (void)mode;
    return 0;
}
static int fx_null_close(struct _reent *r, void *fd)
{
    (void)r; (void)fd; return 0;
}
static ssize_t fx_null_write(struct _reent *r, void *fd, const char *data, size_t size)
{
    (void)r; (void)fd; (void)data; return (ssize_t)size;
}
static ssize_t fx_null_read(struct _reent *r, void *fd, char *data, size_t size)
{
    (void)r; (void)fd; (void)data; (void)size; return 0;
}
static off_t fx_null_seek(struct _reent *r, void *fd, off_t offset, int whence)
{
    (void)r; (void)fd; (void)offset; (void)whence; return 0;
}
static int fx_null_fstat(struct _reent *r, void *fd, struct stat *st)
{
    (void)r; (void)fd;
    memset(st, 0, sizeof(*st));
    st->st_mode = S_IFCHR | 0666;
    st->st_nlink = 1;
    return 0;
}
static int fx_null_stat(struct _reent *r, const char *path, struct stat *st)
{
    (void)path; return fx_null_fstat(r, NULL, st);
}
static int fx_null_truncate(struct _reent *r, void *fd, off_t size)
{
    (void)size; return fx_null_close(r, fd);
}
static const devoptab_t fx_null_device = {
    .name = "fextendo-null", .structSize = 0,
    .open_r = fx_null_open, .close_r = fx_null_close,
    .write_r = fx_null_write, .read_r = fx_null_read,
    .seek_r = fx_null_seek, .fstat_r = fx_null_fstat, .stat_r = fx_null_stat,
    .ftruncate_r = fx_null_truncate, .fsync_r = fx_null_close,
};
static int fx_silent_io_init(void)
{
    if (AddDevice(&fx_null_device) < 0) return 0;
    /* Native libraries use descriptors 0/1/2; Wine gets ordinary, duplicable
     * file handles backed by this same device instead of std*.txt on SD. */
    devoptab_list[STD_IN] = &fx_null_device;
    devoptab_list[STD_OUT] = &fx_null_device;
    devoptab_list[STD_ERR] = &fx_null_device;
    return 1;
}
#endif
