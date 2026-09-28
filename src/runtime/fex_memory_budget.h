/* LGPL-2.1-or-later. Advertise only the optional capability we can afford.
 * Preserve host capabilities and every other client extension. DXVK uses its
 * ordinary no-budget path; no fabricated/stale memory figures are returned. */
extern int wine_nx_fex_memory_budget_enabled;
void wine_nx_fex_filter_client_budget(struct vulkan_device_extensions *extensions)
{
    if (!wine_nx_fex_memory_budget_enabled)
        extensions->has_VK_EXT_memory_budget = 0;
}
