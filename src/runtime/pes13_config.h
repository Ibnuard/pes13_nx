/* Unified PES13-NX runtime configuration.  The implementation lives in the
 * runtime executable; Box64 and the auxiliary runtime objects use this small
 * ABI so every boolean switch can come from one configuration.ini file. */
#ifndef PES13_CONFIG_H
#define PES13_CONFIG_H

/* `legacy_path` is retained so old installations keep working when the INI
 * file is absent or does not mention a key.  `fallback` is used by switches
 * whose historical default was enabled. */
int wine_nx_config_file_bool(const char *legacy_path, int fallback);

#endif
