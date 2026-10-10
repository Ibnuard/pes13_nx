/* Private to the in-process Horizon directory request/reply. Both ends are
 * built into the same native ELF; this is not a Windows/PE structure. */
#ifndef FEXTENDO_DIRECTORY_META_H
#define FEXTENDO_DIRECTORY_META_H
struct horizon_directory_file_entry
{
    unsigned int name_len;
    unsigned int metadata; /* 1: regular SD file, size from current directory batch */
    unsigned long long file_size;
};
struct stat;
extern int horizon_dir_entry_stat(const char *, const struct horizon_directory_file_entry *, struct stat *, unsigned);
extern void horizon_dir_set_asset_scan(int enabled);
extern unsigned horizon_dir_diag_begin(unsigned handle);
extern void horizon_dir_diag_stage(unsigned token, unsigned phase);
extern void horizon_dir_diag_end(unsigned token, int hint);
extern void horizon_dir_diag_tick(void);
#endif
