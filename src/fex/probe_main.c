/* SPDX-License-Identifier: MIT */
#include <switch.h>
#include <stdio.h>
#include <sys/stat.h>
#include "horizon_host.h"

extern int pes13_fex_jit_test(void);
static FILE *log_file;

static void log_message(const char *message) {
    printf("%s\n", message);
    if (log_file) { fprintf(log_file, "%s\n", message); fflush(log_file); }
    consoleUpdate(NULL);
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    consoleInit(NULL);
    mkdir("sdmc:/switch/pes13-fex-probe", 0777);
    log_file = fopen("sdmc:/switch/pes13-fex-probe/jit-probe.log", "w");
    log_message("PES13 FEX1: Horizon JIT adapter probe");
    log_message("This tests FEX's emitter and RW/RX mappings, not the PES game.");
    pes13_fex_set_logger(log_message);
    int result = pes13_fex_jit_test();
    char summary[120];
    snprintf(summary, sizeof(summary), "[FEX-PROBE] %s result=%d", result ? "FAIL" : "PASS", result);
    log_message(summary);
    log_message("Press + to exit. Log: switch/pes13-fex-probe/jit-probe.log");
    if (log_file) { fclose(log_file); log_file = NULL; }
    PadState pad;
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    padInitializeDefault(&pad);
    while (appletMainLoop()) {
        padUpdate(&pad);
        if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;
        consoleUpdate(NULL);
    }
    consoleExit(NULL);
    return result ? 1 : 0;
}
