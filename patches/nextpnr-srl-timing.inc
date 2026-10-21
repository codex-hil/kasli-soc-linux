// Isolated SRL16E timing model; bounds generated from pinned X-Ray SDF.
#include "srl_timing_values.h"
static bool is_static_srl16(const CellInfo *cell)
{
    return str_or_default(cell->attrs, id_X_ORIG_TYPE) == "SRL16E";
}
bool XilinxImpl::getCellDelay(const CellInfo *cell, IdString from, IdString to, DelayQuad &delay) const
{
    if (is_static_srl16(cell))
        return false; // static-address model: output is clocked, not combinational
    return HimbaechelAPI::getCellDelay(cell, from, to, delay);
}
TimingPortClass XilinxImpl::getPortTimingClass(const CellInfo *cell, IdString port, int &count) const
{
    if (!is_static_srl16(cell))
        return HimbaechelAPI::getPortTimingClass(cell, port, count);
    if (int_or_default(cell->params, id_IS_CLK_INVERTED, 0) != 0)
        log_error("SRL timing experiment supports rising clocks only\n");
    count = 0;
    if (port == id_CLK) return TMG_CLOCK_INPUT;
    if (port == id_DI2 || port == id_WE) { count = 1; return TMG_REGISTER_INPUT; }
    if (port == id_O6) { count = 1; return TMG_REGISTER_OUTPUT; }
    for (IdString a : {id_A1, id_A2, id_A3, id_A4, id_A5, id_A6}) {
        if (port != a) continue;
        const NetInfo *net = cell->getPort(a);
        if (net && net->name.str(ctx) != "$PACKER_VCC_NET" && net->name.str(ctx) != "$PACKER_GND_NET")
            log_error("SRL timing experiment requires static addresses\n");
        return TMG_IGNORE;
    }
    return TMG_IGNORE;
}
TimingClockingInfo XilinxImpl::getPortClockingInfo(const CellInfo *cell, IdString port, int index) const
{
    if (!is_static_srl16(cell))
        return HimbaechelAPI::getPortClockingInfo(cell, port, index);
    NPNR_ASSERT(index == 0);
    TimingClockingInfo result;
    result.clock_port = id_CLK;
    result.edge = RISING_EDGE;
    auto dp = [&](int low, int high) { return DelayPair(ctx->getDelayFromNS(low/1000.0), ctx->getDelayFromNS(high/1000.0)); };
    if (port == id_DI2) {
        result.setup = dp(srl_setup_min, srl_setup_max);
        result.hold = dp(srl_hold_min, srl_hold_max);
    } else if (port == id_WE) {
        result.setup = dp(srl_we_setup_min, srl_we_setup_max);
        result.hold = dp(srl_we_hold_min, srl_we_hold_max);
    } else {
        NPNR_ASSERT(port == id_O6);
        result.clockToQ = DelayQuad(ctx->getDelayFromNS(srl_cq_min/1000.0), ctx->getDelayFromNS(srl_cq_max/1000.0));
    }
    return result;
}
