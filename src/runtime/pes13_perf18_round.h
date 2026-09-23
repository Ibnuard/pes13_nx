/* Included only by D8/DE arithmetic and D9 float-store emitters.
 * The private token must only be passed to pes18_restoreround: it is not
 * an ARM register number and must never be passed to CALL_D or SSE helpers. */
extern int wine_nx_perf18_round_site(uintptr_t addr, int pass);

static int pes18_setround(dynarec_arm_t *dyn, int ninst, int s1, int s2, int s3)
{
    if (s1 == s2 || s1 == s3 || s2 == s3 ||
        !wine_nx_perf18_round_site(dyn->insts[ninst].x64.addr, STEP))
        return x87_setround(dyn, ninst, s1, s2, s3);
    LDRw_U12(s1, xEmu, offsetof(x64emu_t, cw));
    BFXILw(s1, s1, 10, 2);
    UBFXw(s2, s1, 1, 1);
    BFIw(s2, s1, 1, 1);
    MRS_fpcr(s1);
    MOVx_REG(s3, s1);
    BFIx(s1, s2, 22, 2);
    EORw_REG(s2, s1, s3);
    CBZw(s2, 12);                 /* Already equal: skip MSR and marker. */
    MSR_fpcr(s1);
    ORRx_mask(s3, s3, 1, 1, 0);   /* bit 63, in saved GPR only */
    return s3 + 32;
}

static void pes18_restoreround(dynarec_arm_t *dyn, int ninst, int token)
{
    if (token < 32) { x87_restoreround(dyn, ninst, token); return; }
    int saved = token - 32;
    TBZ(saved, 63, 12);           /* No change: no restoration required. */
    BFCx(saved, 63, 1);           /* Never write the marker to FPCR. */
    MSR_fpcr(saved);
}
