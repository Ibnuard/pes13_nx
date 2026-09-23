/* Included by runtime.c after read_key_map/read_bool_file. LGPL-2.1-or-later. */
#ifndef PES13_CONTROLLER_UI_H
#define PES13_CONTROLLER_UI_H

/* Use the existing startup console before Wine or Vulkan owns the window.
 * This only reads input. It does not open settings.exe or write game settings. */
static void pes13_controller_check(int requested)
{
    PadState pad;
    const u64 entry_buttons = HidNpadButton_L | HidNpadButton_R;
    u64 seen = 0;
    int allow_continue = 0;
    static const struct { u64 mask; const char *name; WORD xbox; int key; } face[] = {
        { HidNpadButton_B, "B (bottom)", XINPUT_GAMEPAD_A, WINE_NX_KEY_B },
        { HidNpadButton_A, "A (right) ", XINPUT_GAMEPAD_B, WINE_NX_KEY_A },
        { HidNpadButton_Y, "Y (left)  ", XINPUT_GAMEPAD_X, WINE_NX_KEY_Y },
        { HidNpadButton_X, "X (top)   ", XINPUT_GAMEPAD_Y, WINE_NX_KEY_X },
    };
    unsigned int i;

    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    padInitializeDefault(&pad);
    padUpdate(&pad);
    if (!requested && (padGetButtons(&pad) & entry_buttons) != entry_buttons) return;
    log_line("[PES13-PAD-CHECK] started; read-only native controller check");
    printf("\x1b[2J");
    while (appletMainLoop())
    {
        XINPUT_GAMEPAD mapped;
        HidAnalogStickState left, right;
        u64 held;
        padUpdate(&pad);
        held = padGetButtons(&pad);
        seen |= held;
        left = padGetStickPos(&pad, 0);
        right = padGetStickPos(&pad, 1);
        nx_xinput_map(held, left.x, left.y, right.x, right.y, &mapped);
        if (!(held & HidNpadButton_Plus)) allow_continue = 1;
        if (allow_continue && (padGetButtonsDown(&pad) & HidNpadButton_Plus)) break;
        printf("\x1b[HPES13-NX - Controller Check\x1b[K\n\n");
        printf("Controller: %-12s  Mode: %-14s\x1b[K\n\n",
               padIsConnected(&pad) ? "CONNECTED" : "DISCONNECTED",
               wine_nx_pes13_keyboard_only ? "Keyboard" :
               wine_nx_pes13_gamepad_only ? "Gamepad only" : "Auto / XInput");
        printf("Press each button. 'SEEN' stays on after release.\x1b[K\n");
        printf("Switch button    NOW     SEEN    Xbox bit    Keyboard VK\x1b[K\n");
        for (i = 0; i < sizeof(face) / sizeof(face[0]); ++i)
            printf("%-14s   %-5s   %-5s   %04x/%04x   %02x\x1b[K\n", face[i].name,
                   held & face[i].mask ? "DOWN" : "--", seen & face[i].mask ? "YES" : "--",
                   mapped.wButtons & face[i].xbox, face[i].xbox, wine_nx_pad_keys[face[i].key]);
        printf("\nD-pad: U=%d D=%d L=%d R=%d\x1b[K\n",
               !!(held & HidNpadButton_Up), !!(held & HidNpadButton_Down),
               !!(held & HidNpadButton_Left), !!(held & HidNpadButton_Right));
        printf("L=%d R=%d ZL=%d ZR=%d Minus=%d L3=%d R3=%d\x1b[K\n",
               !!(held & HidNpadButton_L), !!(held & HidNpadButton_R),
               !!(held & HidNpadButton_ZL), !!(held & HidNpadButton_ZR),
               !!(held & HidNpadButton_Minus), !!(held & HidNpadButton_StickL), !!(held & HidNpadButton_StickR));
        printf("Left stick:  X=%7d Y=%7d\x1b[K\nRight stick: X=%7d Y=%7d\x1b[K\n",
               left.x, left.y, right.x, right.y);
        printf("\nRaw: %04llx  Xbox: %04x  LT=%3u RT=%3u\x1b[K\n",
               (unsigned long long)(held & 0xffff), mapped.wButtons, mapped.bLeftTrigger, mapped.bRightTrigger);
        printf("\nRead-only test. Game delivery is checked in pes13-nx.log.\x1b[K\n");
        printf("No graphics or game configuration is changed.\x1b[K\n\n");
        printf("Press + to continue to PES. HOME closes the application.\x1b[K\n");
        consoleUpdate(NULL);
    }
    if (!appletMainLoop()) exit(0);
    /* Do not carry the continue button into the game as a pause/escape. */
    while (appletMainLoop())
    {
        padUpdate(&pad);
        if (!(padGetButtons(&pad) & HidNpadButton_Plus)) break;
        consoleUpdate(NULL);
    }
    if (!appletMainLoop()) exit(0);
    printf("\x1b[2J\x1b[H");
    log_line("[PES13-PAD-CHECK] finished; seen_raw=%04llx face_seen=%x (all=0xf)",
             (unsigned long long)(seen & 0xffff), (unsigned int)(seen & 0xf));
}
#endif
