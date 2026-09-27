/* Startup-only cache directory preparation. DXVK owns all cache files. */
static void fex_cache_prepare_directory(void)
{
    struct stat info;
    const char *status = "created";
    int error = 0;

    if (mkdir(WINE_DRIVE_C "/dxvk-cache", 0777))
    {
        error = errno;
        status = "unavailable";
        if (error == EEXIST)
        {
            if (stat(WINE_DRIVE_C "/dxvk-cache", &info)) error = errno;
            else if (!S_ISDIR(info.st_mode)) error = ENOTDIR;
            else
            {
                status = "existing";
                error = 0;
            }
        }
    }
    /* Directory creation is not evidence of a usable or durable DXVK cache. */
    log_line("[FEX-CACHE] path=%s status=%s errno=%d persistence=unverified; continuing",
             WINE_DRIVE_C "/dxvk-cache", status, error);
}
