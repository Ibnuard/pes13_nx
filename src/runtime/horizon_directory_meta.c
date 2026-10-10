/* Native SD enumeration metadata. No directory-sized cache and no file writes.
 * Include after the Wine/libnx headers in horizon.c. */
#include <sys/iosupport.h>
#include "horizon_directory_meta.h"

static int horizon_dir_asset_scan;

void horizon_dir_set_asset_scan(int enabled)
{
    __atomic_store_n(&horizon_dir_asset_scan, !!enabled, __ATOMIC_RELEASE);
}

/* AFS2FS's filename-index scan consumes names/attributes, not file dates.
 * Limit this compatibility policy to files immediately under a Kitserver
 * img/<archive>.img directory. Explicit file queries retain real timestamps. */
static int horizon_dir_is_asset(const char *path)
{
    const char *part, *end, *parent = NULL, *grandparent = NULL;
    size_t parent_len = 0, grandparent_len = 0;
    int kitserver = 0;
    if (strncmp(path, "sdmc:/", 6)) return 0;
    for (part = path + 6; *part; part = end + 1)
    {
        size_t len;
        end = strchr(part, '/');
        len = end ? (size_t)(end - part) : strlen(part);
        if (!len || (len == 2 && part[0] == '.' && part[1] == '.')) return 0;
        if (!end)
            return kitserver && parent_len > 4 && grandparent_len == 3 &&
                   !strncasecmp(grandparent, "img", 3) &&
                   !strncasecmp(parent + parent_len - 4, ".img", 4) &&
                   !(len == 1 && part[0] == '.');
        if (len == 1 && part[0] == '.') continue;
        if (len >= 9 && !strncasecmp(part, "kitserver", 9))
        {
            size_t i = 9;
            while (i < len && part[i] >= '0' && part[i] <= '9') i++;
            if (i == len) kitserver = 1;
        }
        grandparent = parent;
        grandparent_len = parent_len;
        parent = part;
        parent_len = len;
    }
    return 0;
}

static void horizon_dir_capture_metadata(DIR *stream, const char *path, const char *name,
                                         struct horizon_directory_file_entry *out)
{
    const devoptab_t *device;
    fsdev_dir_t *cursor;
    const FsDirectoryEntry *entry;
    out->metadata = 0;
    out->file_size = 0;
    /* Never interpret a different devoptab's private storage as fsdev state. */
    if (!stream || !stream->dirData || strncmp(path, "sdmc:/", 6) ||
        stream->dirData->device != FindDevice("sdmc:") ||
        !(device = GetDeviceOpTab("sdmc:")) || device->dirStateSize < sizeof(fsdev_dir_t) ||
        !(cursor = stream->dirData->dirStruct) || cursor->magic != FSDEV_DIRITER_MAGIC ||
        cursor->index < 0 || (size_t)cursor->index >= cursor->size ||
        cursor->size > (device->dirStateSize - sizeof(fsdev_dir_t)) / sizeof(FsDirectoryEntry)) return;
    entry = &fsdevDirGetEntries(cursor)[cursor->index];
    if (entry->type != FsDirEntryType_File || entry->file_size < 0 ||
        strnlen(entry->name, sizeof(entry->name)) == sizeof(entry->name) || strcmp(entry->name, name)) return;
    out->file_size = entry->file_size;
    out->metadata = 1;
}

/* Match fsdev's local-filesystem-time -> UTC semantics, including fallback
 * when the time service is unavailable. gmtime_r avoids shared tm storage. */
static time_t horizon_dir_time_utc(u64 raw)
{
    time_t input = (time_t)raw;
    struct tm parts;
    TimeCalendarTime calendar = {0};
    u64 converted = raw;
    if (!gmtime_r(&input, &parts)) return input;
    calendar.year = parts.tm_year + 1900;
    calendar.month = parts.tm_mon + 1;
    calendar.day = parts.tm_mday;
    calendar.hour = parts.tm_hour;
    calendar.minute = parts.tm_min;
    calendar.second = parts.tm_sec;
    if (R_FAILED(timeToPosixTimeWithMyRule(&calendar, &converted, 1, NULL))) return input;
    return (time_t)converted;
}

int horizon_dir_entry_stat(const char *path, const struct horizon_directory_file_entry *entry,
                          struct stat *st, unsigned token)
{
    FsFileSystem *fs = NULL;
    FsTimeStampRaw times = {0};
    char translated[FS_MAX_PATH];
    int saved = errno;
    if (entry->metadata != 1 || entry->file_size > 0x7fffffffffffffffULL || strncmp(path, "sdmc:/", 6)) return 0;
    if (__atomic_load_n(&horizon_dir_asset_scan, __ATOMIC_ACQUIRE) && horizon_dir_is_asset(path))
    {
        memset(st, 0, sizeof(*st));
        st->st_mode = S_IFREG | 0666;
        st->st_nlink = 1;
        st->st_size = entry->file_size;
        /* Caller marks directory-result time fields unavailable (zero). */
        return 2;
    }
    horizon_dir_diag_stage(token, 4);
    if (fsdevTranslatePath(path, &fs, translated) == -1 || !fs ||
        R_FAILED(fsFsGetFileTimeStampRaw(fs, translated, &times)))
    {
        errno = saved;
        horizon_dir_diag_stage(token, 3);
        return 0; /* Original lstat path handles deletion, permissions and IO errors. */
    }
    memset(st, 0, sizeof(*st));
    st->st_mode = S_IFREG | 0666;
    st->st_nlink = 1;
    st->st_size = entry->file_size;
    if (times.is_valid)
    {
        horizon_dir_diag_stage(token, 5);
        st->st_ctime = horizon_dir_time_utc(times.created);
        st->st_mtime = horizon_dir_time_utc(times.modified);
        st->st_atime = horizon_dir_time_utc(times.accessed);
    }
    errno = saved;
    horizon_dir_diag_stage(token, 3);
    return 1;
}

/* Debug-only observations, drained by the existing maintenance thread. No
 * new worker, suspension, server lock, dynamic allocation or SD operation. */
#define HORIZON_DIR_DIAG_SLOTS 16
#define HORIZON_DIR_DIAG_PHASES 6
static struct horizon_dir_diag_slot {
    unsigned claimed, phase, handle;
    unsigned long long since;
} horizon_dir_diag_slots[HORIZON_DIR_DIAG_SLOTS];
static struct horizon_dir_diag_cost {
    unsigned long long calls, ticks, peak;
} horizon_dir_diag_costs[HORIZON_DIR_DIAG_PHASES];
static unsigned long long horizon_dir_diag_finished, horizon_dir_diag_fast, horizon_dir_diag_fallback;
static unsigned long long horizon_dir_diag_assets;
static unsigned long long horizon_dir_diag_last_finished;

unsigned horizon_dir_diag_begin(unsigned handle)
{
    extern int wine_nx_launch_debug_active(void);
    unsigned i;
    if (!wine_nx_launch_debug_active()) return 0;
    for (i = 0; i < HORIZON_DIR_DIAG_SLOTS; i++)
    {
        unsigned empty = 0;
        struct horizon_dir_diag_slot *slot = &horizon_dir_diag_slots[i];
        if (!__atomic_compare_exchange_n(&slot->claimed, &empty, 1, 0, __ATOMIC_ACQ_REL, __ATOMIC_RELAXED)) continue;
        __atomic_store_n(&slot->handle, handle, __ATOMIC_RELAXED);
        __atomic_store_n(&slot->since, horizon_interrupt_time(), __ATOMIC_RELAXED);
        __atomic_store_n(&slot->phase, 1, __ATOMIC_RELEASE);
        return i + 1;
    }
    return 0; /* Observation pressure must never delay the caller. */
}

void horizon_dir_diag_stage(unsigned token, unsigned phase)
{
    struct horizon_dir_diag_slot *slot;
    struct horizon_dir_diag_cost *cost;
    unsigned previous;
    unsigned long long now, elapsed, peak;
    if (!token || token > HORIZON_DIR_DIAG_SLOTS || phase >= HORIZON_DIR_DIAG_PHASES) return;
    slot = &horizon_dir_diag_slots[token - 1];
    previous = __atomic_load_n(&slot->phase, __ATOMIC_ACQUIRE);
    now = horizon_interrupt_time();
    elapsed = now - __atomic_load_n(&slot->since, __ATOMIC_RELAXED);
    if (previous && previous < HORIZON_DIR_DIAG_PHASES)
    {
        cost = &horizon_dir_diag_costs[previous];
        __atomic_add_fetch(&cost->calls, 1, __ATOMIC_RELAXED);
        __atomic_add_fetch(&cost->ticks, elapsed, __ATOMIC_RELAXED);
        peak = __atomic_load_n(&cost->peak, __ATOMIC_RELAXED);
        while (elapsed > peak && !__atomic_compare_exchange_n(&cost->peak, &peak, elapsed, 0,
                                                              __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
    }
    __atomic_store_n(&slot->since, now, __ATOMIC_RELAXED);
    __atomic_store_n(&slot->phase, phase, __ATOMIC_RELEASE);
}

void horizon_dir_diag_end(unsigned token, int hint)
{
    if (!token || token > HORIZON_DIR_DIAG_SLOTS) return;
    horizon_dir_diag_stage(token, 0);
    __atomic_add_fetch(&horizon_dir_diag_finished, 1, __ATOMIC_RELAXED);
    if (hint > 0) __atomic_add_fetch(&horizon_dir_diag_fast, 1, __ATOMIC_RELAXED);
    else if (!hint) __atomic_add_fetch(&horizon_dir_diag_fallback, 1, __ATOMIC_RELAXED);
    if (hint == 2) __atomic_add_fetch(&horizon_dir_diag_assets, 1, __ATOMIC_RELAXED);
    __atomic_store_n(&horizon_dir_diag_slots[token - 1].claimed, 0, __ATOMIC_RELEASE);
}

void horizon_dir_diag_tick(void)
{
    extern int wine_nx_launch_debug_active(void);
    static const char *names[HORIZON_DIR_DIAG_PHASES] = {"idle", "server", "path", "metadata", "timestamp", "timezone"};
    unsigned i, active = 0;
    unsigned long long now, finished;
    int saved;
    if (!wine_nx_launch_debug_active()) return;
    saved = errno;
    now = horizon_interrupt_time();
    finished = __atomic_load_n(&horizon_dir_diag_finished, __ATOMIC_RELAXED);
    for (i = 0; i < HORIZON_DIR_DIAG_SLOTS; i++)
    {
        struct horizon_dir_diag_slot *slot = &horizon_dir_diag_slots[i];
        unsigned phase = __atomic_load_n(&slot->phase, __ATOMIC_ACQUIRE);
        unsigned long long since = __atomic_load_n(&slot->since, __ATOMIC_RELAXED);
        if (!phase || phase >= HORIZON_DIR_DIAG_PHASES) continue;
        active++;
        if (now >= since && now - since >= 5000000ULL)
            horizon_trace("[HZDIR-COST] pending handle=%08x phase=%s ms=%llu\n",
                          __atomic_load_n(&slot->handle, __ATOMIC_RELAXED), names[phase], (now - since) / 10000);
    }
    if (finished != horizon_dir_diag_last_finished || active)
    {
        horizon_dir_diag_last_finished = finished;
        horizon_trace("[HZDIR-COST] done=%llu fast=%llu fallback=%llu active=%u\n", finished,
                      __atomic_load_n(&horizon_dir_diag_fast, __ATOMIC_RELAXED),
                      __atomic_load_n(&horizon_dir_diag_fallback, __ATOMIC_RELAXED), active);
        horizon_trace("[HZDIR-COST] asset_names=%llu\n",
                      __atomic_load_n(&horizon_dir_diag_assets, __ATOMIC_RELAXED));
        for (i = 1; i < HORIZON_DIR_DIAG_PHASES; i++)
        {
            struct horizon_dir_diag_cost *cost = &horizon_dir_diag_costs[i];
            horizon_trace("[HZDIR-COST] phase=%s calls=%llu total_ms=%llu peak_ms=%llu\n", names[i],
                          __atomic_load_n(&cost->calls, __ATOMIC_RELAXED),
                          __atomic_load_n(&cost->ticks, __ATOMIC_RELAXED) / 10000,
                          __atomic_load_n(&cost->peak, __ATOMIC_RELAXED) / 10000);
        }
    }
    errno = saved;
}
