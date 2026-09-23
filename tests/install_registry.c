#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "horizon_registry.h"
#include "pes13_registry.h"

static long long now(void) { return 123; }
static void signal_event(void *event) { (void)event; }

static struct horizon_reg_key *lookup(struct horizon_reg *reg, struct horizon_reg_key *base,
                                     const char *path)
{
    unsigned short wide[128];
    struct horizon_reg_key *key = NULL;
    size_t n = strlen(path), i;
    assert(n < 128);
    for (i = 0; i < n; i++) wide[i] = path[i];
    unsigned int status = horizon_reg_open(reg, base, wide, n * 2, 0, &key);
    assert(status == 0 || status == HORIZON_REG_NAME_NOT_FOUND);
    if (key) horizon_reg_release(reg, key); /* the tree retains its reference */
    return key;
}

static void expect_dir(struct horizon_reg_key *key)
{
    const unsigned short name[] = {'I','N','S','T','A','L','L','D','I','R'};
    const unsigned short expected[] = {'C',':','\\','P','E','S','1','3','\\',0};
    unsigned short value[32];
    int type;
    unsigned int total, size;
    assert(key);
    assert(!horizon_reg_get_value(key, name, sizeof(name), &type, &total, (unsigned char *)value, sizeof(value), &size));
    assert(type == HORIZON_REG_SZ && total == sizeof(expected) && size == sizeof(expected));
    assert(!memcmp(value, expected, size));
}

int main(int argc, char **argv)
{
    struct horizon_reg reg;
    unsigned int views, errors = 0, index;
    const char seed[] = "WINE REGISTRY Version 2\n"
        "[Software\\\\OtherGame]\n\"keep\"=dword:12345678\n"
        "[Software\\\\KONAMI\\\\PES2013]\n\"version\"=\"user-value\"\n"
        "\"installdir\"=\"D:\\\\OldPath\\\\\"\n";
    const unsigned short keep[] = {'k','e','e','p'}, version[] = {'v','e','r','s','i','o','n'};
    assert(horizon_reg_init(&reg, now, signal_event));
    struct horizon_reg_key *machine = horizon_reg_create_ascii(&reg, reg.root, "Machine");
    assert(machine);

    assert(!pes13_registry_install(&reg, machine, 0, &views) && !views);
    assert(!machine->subkey_count);
    assert(!horizon_reg_load(&reg, machine, seed, sizeof(seed) - 1, &errors) && !errors);
    struct horizon_reg_key *other = lookup(&reg, machine, "Software\\OtherGame");
    struct horizon_reg_value *preserved = horizon_reg_find_value(other, keep, sizeof(keep), &index);
    assert(preserved && preserved->type == HORIZON_REG_DWORD);
    unsigned int keep_data;
    memcpy(&keep_data, preserved->data, sizeof(keep_data));
    assert(keep_data == 0x12345678);

    assert(!pes13_registry_install(&reg, machine, 1, &views) && views == 1);
    struct horizon_reg_key *pes = lookup(&reg, machine, "Software\\Konami\\PES2013");
    expect_dir(pes);
    assert(pes->value_count == 2);
    assert(horizon_reg_find_value(pes, version, sizeof(version), &index));
    assert(!lookup(&reg, machine, "Software\\Wow6432Node"));
    assert(lookup(&reg, machine, "Software\\OtherGame") == other);
    assert(!pes13_registry_install(&reg, machine, 1, &views) && views == 1);
    assert(pes->value_count == 2);
    expect_dir(pes);

    assert(horizon_reg_create_ascii(&reg, machine, "Software\\Wow6432Node\\ExistingApp"));
    assert(!pes13_registry_install(&reg, machine, 1, &views) && views == 2);
    expect_dir(lookup(&reg, machine, "Software\\Wow6432Node\\KONAMI\\PES2013"));
    assert(lookup(&reg, machine, "Software\\Wow6432Node\\ExistingApp"));
    preserved = horizon_reg_find_value(other, keep, sizeof(keep), &index);
    memcpy(&keep_data, preserved->data, sizeof(keep_data));
    assert(keep_data == 0x12345678);
    if (argc == 2)
    {
        FILE *file = fopen(argv[1], "rb");
        char buffer[4096];
        size_t count;
        const unsigned short code[] = {'c','o','d','e'};
        assert(file);
        count = fread(buffer, 1, sizeof(buffer), file);
        assert(!ferror(file) && count < sizeof(buffer) && feof(file));
        fclose(file);
        errors = 0;
        assert(!horizon_reg_load(&reg, machine, buffer, count, &errors) && !errors);
        assert(!pes13_registry_install(&reg, machine, 1, &views) && views == 2);
        struct horizon_reg_key *redirected = lookup(&reg, machine, "Software\\Wow6432Node\\KONAMI\\PES2013");
        const struct horizon_reg_value *a = horizon_reg_find_value(pes, code, sizeof(code), &index);
        const struct horizon_reg_value *b = horizon_reg_find_value(redirected, code, sizeof(code), &index);
        assert(a && b && a->type == HORIZON_REG_SZ && b->type == HORIZON_REG_SZ);
        assert(a->len >= 4 && a->len == b->len && !memcmp(a->data, b->data, a->len));
        assert(!((const unsigned short *)a->data)[a->len / 2 - 1]);
        a = horizon_reg_find_value(pes, version, sizeof(version), &index);
        b = horizon_reg_find_value(redirected, version, sizeof(version), &index);
        assert(a && b && a->type == HORIZON_REG_SZ && b->type == HORIZON_REG_SZ);
        assert(a->len == b->len && !memcmp(a->data, b->data, a->len));
        expect_dir(pes);
        expect_dir(redirected);
        preserved = horizon_reg_find_value(other, keep, sizeof(keep), &index);
        memcpy(&keep_data, preserved->data, sizeof(keep_data));
        assert(keep_data == 0x12345678);
        puts("Imported metadata: code/version parsed, mirrored exactly, install path and unrelated data preserved (contents not printed)");
    }
    horizon_reg_release(&reg, reg.root);
    puts("PES installation registry: disabled target, merge, UTF-16 value, preservation, idempotence and existing WoW64 view passed");
}
