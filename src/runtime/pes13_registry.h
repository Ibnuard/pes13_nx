/* PES13 installation metadata for the fixed C:\PES13 deployment.
 * Included after the release-108 horizon_registry.h, and used by its host test.
 * Only installdir is synthesized. Imported code/version are mirrored to an
 * existing 32-bit view. Existing unrelated keys and values are retained.
 */
#ifndef PES13_REGISTRY_H
#define PES13_REGISTRY_H

static inline unsigned int pes13_registry_copy_metadata(struct horizon_reg *reg,
                                                       const struct horizon_reg_key *from,
                                                       struct horizon_reg_key *to)
{
    static const unsigned short names[2][7] = {
        {'c','o','d','e'}, {'v','e','r','s','i','o','n'}
    };
    static const unsigned int lengths[] = {8, 14};
    unsigned int i, index, status;
    for (i = 0; i < 2; i++)
    {
        struct horizon_reg_value *value = horizon_reg_find_value(from, names[i], lengths[i], &index);
        if (!value) continue;
        status = horizon_reg_set_value(reg, to, names[i], lengths[i],
                                        value->type, value->data, value->len);
        if (status) return status;
    }
    return HORIZON_REG_SUCCESS;
}

static inline unsigned int pes13_registry_install(struct horizon_reg *reg,
                                                  struct horizon_reg_key *machine,
                                                  int enabled, unsigned int *views)
{
    static const unsigned short value_name[] = {'i','n','s','t','a','l','l','d','i','r'};
    static const unsigned short install_dir[] = {'C',':','\\','P','E','S','1','3','\\',0};
    static const unsigned short wow_path[] = {
        'S','o','f','t','w','a','r','e','\\','W','o','w','6','4','3','2','N','o','d','e'
    };
    struct horizon_reg_key *key, *native, *wow = NULL;
    unsigned int status;
    *views = 0;
    if (!enabled) return HORIZON_REG_SUCCESS;

    key = horizon_reg_create_ascii(reg, machine, "Software\\KONAMI\\PES2013");
    if (!key) return HORIZON_REG_NO_MEMORY;
    status = horizon_reg_set_value(reg, key, value_name, sizeof(value_name),
                                   HORIZON_REG_SZ, install_dir, sizeof(install_dir));
    if (status) return status;
    native = key;
    *views = 1;

    /* Build 108 normally has a single view. Creating Wow6432Node here would
     * change redirection for every application's Software keys. Populate the
     * redirected PES key only when that view already exists in the loaded hive.
     */
    status = horizon_reg_open(reg, machine, wow_path, sizeof(wow_path), 0, &wow);
    if (status == HORIZON_REG_NAME_NOT_FOUND) return HORIZON_REG_SUCCESS;
    if (status) return status;
    key = horizon_reg_create_ascii(reg, wow, "KONAMI\\PES2013");
    status = key ? horizon_reg_set_value(reg, key, value_name, sizeof(value_name),
                                         HORIZON_REG_SZ, install_dir, sizeof(install_dir))
                 : HORIZON_REG_NO_MEMORY;
    if (!status) status = pes13_registry_copy_metadata(reg, native, key);
    horizon_reg_release(reg, wow);
    if (!status) *views = 2;
    return status;
}

#endif
