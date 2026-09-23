/* A real object makes the linker emit a DLL, not just a DEF import library.
 * All callable exports are PE forwarders specified in xinput1_1.def. */
const char pes13_xinput_bridge_version[] = "PES13 Wine-NX build108 XInput forwarder v1";
/* Keep base relocations so this DLL can coexist with the game's local DLLs. */
static const void *volatile relocation_anchor = pes13_xinput_bridge_version;

int __attribute__((stdcall)) DllMain(void *module, unsigned int reason, void *reserved)
{
    (void)module;
    (void)reason;
    (void)reserved;
    return relocation_anchor != 0;
}
