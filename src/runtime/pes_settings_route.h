/* LGPL-2.1-or-later. PES-only Wine settings aliases, never save-directory aliases.
 * Included by ntdll/unix/file.c after the Wine NT types are available. */
#ifndef PES_SETTINGS_ROUTE_H
#define PES_SETTINGS_ROUTE_H

static int pes_settings_ascii(const WCHAR *name, unsigned length, const char *ascii)
{
    unsigned i;
    for (i = 0; i < length && ascii[i]; i++)
    {
        unsigned ch = name[i], ref = (unsigned char)ascii[i];
        if (ch >= 'A' && ch <= 'Z') ch += 'a' - 'A';
        if (ref >= 'A' && ref <= 'Z') ref += 'a' - 'A';
        if (ch != ref) return 0;
    }
    return i == length && !ascii[i];
}

/* Consume a complete component, not a substring or a NUL-terminated guest string. */
static int pes_settings_component(const WCHAR **name, unsigned *length, const char *ascii)
{
    unsigned i = 0;
    while (i < *length && (*name)[i] != '\\') i++;
    if (i == *length || !pes_settings_ascii(*name, i, ascii)) return 0;
    *name += i + 1;
    *length -= i + 1;
    return 1;
}

static int pes_settings_folder(const WCHAR **name, unsigned *length)
{
    unsigned i = 0;
    while (i < *length && (*name)[i] != '\\')
    {
        unsigned ch = (*name)[i];
        if (ch < 32 || ch == '/' || ch == ':' || ch == '"' || ch == '*' ||
            ch == '?' || ch == '<' || ch == '>' || ch == '|') return 0;
        i++;
    }
    if (!i || i == *length || (*name)[i - 1] == '.' || (*name)[i - 1] == ' ') return 0;
    *name += i + 1;
    *length -= i + 1;
    return 1;
}

/* KernelBase has already resolved DOS/current-directory paths to NT names.
 * The three launcher-managed original locations retain their ordinary lookup.
 * Only a renamed patch's settings.dat gets the shared preset. In particular,
 * EDIT.bin, OPTION.bin, directory opens and Kitserver configs never match. */
static int pes_settings_is_patch(const WCHAR *name, unsigned length)
{
    const WCHAR *rest;
    unsigned remaining;
    if (!name || length < 4) return 0;
    if (pes_settings_ascii(name, 4, "\\??\\")) { name += 4; length -= 4; }
    else if (length >= 12 && pes_settings_ascii(name, 12, "\\DosDevices\\"))
    { name += 12; length -= 12; }
    else return 0;
    if (!pes_settings_component(&name, &length, "C:")) return 0;
    rest = name; remaining = length;
    if (pes_settings_component(&rest, &remaining, "PES13"))
    { name = rest; length = remaining; }
    else if (pes_settings_component(&rest, &remaining, "users"))
    {
        if (!pes_settings_folder(&rest, &remaining) ||
            !pes_settings_component(&rest, &remaining, "Documents")) return 0;
        name = rest; length = remaining;
    }
    if (!pes_settings_component(&name, &length, "KONAMI")) return 0;
    rest = name; remaining = length;
    if (pes_settings_component(&rest, &remaining, "Pro Evolution Soccer 2013")) return 0;
    if (!pes_settings_folder(&name, &length)) return 0;
    return pes_settings_ascii(name, length, "settings.dat");
}

/* Reuse Wine's owned nt_name convention so stat/open/create/write all resolve
 * the same real file and preserve normal errors, permissions and sharing.
 * Allocation failure leaves the caller's attributes and owned buffer intact. */
static NTSTATUS pes_settings_route(OBJECT_ATTRIBUTES *attr, UNICODE_STRING *nt_name)
{
    static const char canonical[] = "\\??\\C:\\KONAMI\\Pro Evolution Soccer 2013\\settings.dat";
    UNICODE_STRING *original = attr->ObjectName;
    WCHAR *buffer;
    unsigned i;
    if (attr->RootDirectory || !original || (original->Length & 1) ||
        !pes_settings_is_patch(original->Buffer, original->Length / sizeof(WCHAR))) return STATUS_SUCCESS;
    buffer = malloc(sizeof(canonical) * sizeof(WCHAR));
    if (!buffer) return STATUS_NO_MEMORY;
    for (i = 0; i < sizeof(canonical); i++) buffer[i] = (unsigned char)canonical[i];
    {
        extern int wine_nx_launch_debug_active(void);
        extern void wine_nx_runtime_trace(const char *message);
        static unsigned reports;
        if (wine_nx_launch_debug_active() && __atomic_fetch_add(&reports, 1, __ATOMIC_RELAXED) < 8)
        {
            char from[192], message[320];
            unsigned count = original->Length / sizeof(WCHAR);
            if (count >= sizeof(from)) count = sizeof(from) - 1;
            for (i = 0; i < count; i++)
                from[i] = original->Buffer[i] >= 32 && original->Buffer[i] < 127 ? original->Buffer[i] : '?';
            from[count] = 0;
            snprintf(message, sizeof(message), "[LW6-SETTINGS] alias=%s -> %s", from, canonical);
            wine_nx_runtime_trace(message);
        }
    }
    if (original == nt_name) free(nt_name->Buffer);
    nt_name->Buffer = buffer;
    nt_name->Length = (sizeof(canonical) - 1) * sizeof(WCHAR);
    nt_name->MaximumLength = sizeof(canonical) * sizeof(WCHAR);
    attr->ObjectName = nt_name;
    return STATUS_SUCCESS;
}
#endif
