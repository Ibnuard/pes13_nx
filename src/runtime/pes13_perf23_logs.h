/* Retain the previous four runs before opening the current runtime log.
 * Only exact runtime-owned names are rotated. No save/config/cache paths. */
#ifndef PES13_PERF23_LOGS_H
#define PES13_PERF23_LOGS_H
#include <errno.h>
#include <stdio.h>
#include <sys/stat.h>

static FILE *pes23_open_log(const char *directory, int *rotation_error)
{
    char source[1024], destination[1024], current[1024];
    struct stat st;
    int n, exists;
    *rotation_error = 0;
    n = snprintf(current, sizeof(current), "%s/pes13-nx.log", directory);
    if (n < 0 || (size_t)n >= sizeof(current) - 16) {
        *rotation_error = ENAMETOOLONG;
        return NULL;
    }
    exists = stat(current, &st) == 0;
    if (!exists && errno != ENOENT) { *rotation_error = errno; return NULL; }
    if (exists) {
        for (int i = 4; i >= 1; --i) {
            snprintf(destination, sizeof(destination), "%s/pes13-nx.previous-%d.log", directory, i);
            if (i == 1) snprintf(source, sizeof(source), "%s", current);
            else snprintf(source, sizeof(source), "%s/pes13-nx.previous-%d.log", directory, i - 1);
            if (stat(source, &st) != 0) {
                if (errno == ENOENT) continue;
                *rotation_error = errno; break;
            }
            if (!S_ISREG(st.st_mode)) { *rotation_error = EISDIR; break; }
            if (stat(destination, &st) == 0) {
                if (!S_ISREG(st.st_mode)) { *rotation_error = EISDIR; break; }
            } else if (errno != ENOENT) { *rotation_error = errno; break; }
            /* devoptab filesystems need an absent rename destination. If a
             * step fails, keep the current log and append the new run. */
            if (remove(destination) != 0 && errno != ENOENT) {
                *rotation_error = errno; break;
            }
            if (rename(source, destination) != 0) {
                *rotation_error = errno; break;
            }
        }
    }
    return fopen(current, *rotation_error ? "a" : "w");
}
#endif
