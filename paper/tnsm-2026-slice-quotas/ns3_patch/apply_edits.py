#!/usr/bin/env python3
"""Produce the standalone example sources from orig/. Every edit is additive: a block-level diagnostic on the UE PHY trace,
a queue-proportional quota policy and, for the tenant study, a flag that limits A at the source under any scheduler."""
import os
H = os.path.dirname(os.path.abspath(__file__))
DIAG = r'''
#include "ns3/nr-phy-mac-common.h"
#include <array>
#include <functional>
#include <map>
namespace {
// Block-level diagnostic, read from the UEs' PHY trace; passive, it draws no random numbers and schedules no event.
struct DiagBin { uint64_t slotsNew{0}, slotsRetx{0}, slotsMixed{0}, tbNew{0}, tbRetx{0}, nack{0}; double kbNew{0}; };
struct Diag {
    std::map<uint16_t, uint32_t> sliceOf;
    std::function<void()> init;
    double warmup{0}, windowS{5};
    uint64_t cur{~0ULL};
    uint32_t curNew{0}, curRetx{0};
    size_t curBin{0};
    std::array<uint64_t, 3> tbNew{}, tbRetx{}, nackNew{}, nackRetx{}, rbNew{};
    std::vector<DiagBin> bins;
    void Close() {
        if (cur == ~0ULL) return;
        DiagBin& b = bins[curBin];
        if (curNew && curRetx) b.slotsMixed++; else if (curNew) b.slotsNew++; else if (curRetx) b.slotsRetx++;
        curNew = curRetx = 0;
    }
} gd;
void OnUeRx(RxPacketTraceParams p) {
    const double now = Simulator::Now().GetSeconds();
    if (now < gd.warmup) return;
    if (gd.init) { gd.init(); gd.init = nullptr; }
    const uint64_t key = (uint64_t(p.m_frameNum) << 16) | (uint64_t(p.m_subframeNum) << 8) | p.m_slotNum;
    const size_t bin = size_t((now - gd.warmup) / gd.windowS);
    if (bin >= gd.bins.size()) gd.bins.resize(bin + 1);
    if (key != gd.cur) { gd.Close(); gd.cur = key; gd.curBin = bin; }
    auto it = gd.sliceOf.find(p.m_rnti);
    const uint32_t s = it == gd.sliceOf.end() ? 0 : it->second;
    DiagBin& b = gd.bins[bin];
    if (p.m_rv == 0) {
        gd.curNew++; b.tbNew++; b.kbNew += p.m_tbSize / 1000.0; gd.tbNew[s]++; gd.rbNew[s] += p.m_rbAssignedNum;
        if (p.m_corrupt) { gd.nackNew[s]++; b.nack++; }
    } else {
        gd.curRetx++; b.tbRetx++; gd.tbRetx[s]++;
        if (p.m_corrupt) { gd.nackRetx[s]++; b.nack++; }
    }
}
std::string DiagJson() {
    gd.Close();
    uint64_t sn = 0, sr = 0, sm = 0;
    std::ostringstream o;
    o << ",\"diag_win\":[";
    for (size_t i = 0; i < gd.bins.size(); ++i) {
        const DiagBin& b = gd.bins[i];
        sn += b.slotsNew; sr += b.slotsRetx; sm += b.slotsMixed;
        o << (i ? "," : "") << "[" << gd.warmup + i * gd.windowS << "," << b.slotsNew << "," << b.slotsRetx << "," << b.slotsMixed << ","
          << b.tbNew << "," << b.tbRetx << "," << b.nack << "," << b.kbNew << "]";
    }
    auto arr = [&o](const char* n, const std::array<uint64_t, 3>& a) {
        o << ",\"" << n << "\":[" << a[0] << "," << a[1] << "," << a[2] << "]";
    };
    o << "],\"diag\":{\"slots_new_only\":" << sn << ",\"slots_retx_only\":" << sr << ",\"slots_mixed\":" << sm;
    arr("tb_new", gd.tbNew); arr("tb_retx", gd.tbRetx); arr("nack_new", gd.nackNew); arr("nack_retx", gd.nackRetx); arr("rb_new", gd.rbNew);
    o << "}";
    return o.str();
}
} // namespace
'''
CONNECT = r'''
    gd.warmup = {w};
    gd.windowS = windowS;
    gd.init = [numUes, &rs]() {{
        for (uint32_t u = 0; u < numUes; ++u) gd.sliceOf[rs.GetUeRnti(u)] = u % 3;
    }};
    Config::ConnectWithoutContextFailSafe("/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUePhy/SpectrumPhy/RxPacketTraceUe",
                                          MakeCallback(&OnUeRx));
'''
QUEUE = r'''
    if (slots > 0 && g.policy == "queueprop")
    {
        // Queue-proportional weights (the QueueAdaptive heuristic of Vilchez et al.): above the floors, each slice takes
        // a share of the remainder in proportion to its mean backlog over the last period; PF order inside a slice.
        const double sum = std::accumulate(backlog.begin(), backlog.end(), 0.0);
        if (sum > 0 && backlog.size() >= 3)
        {
            const double free = 1.0 - std::accumulate(g.floor.begin(), g.floor.end(), 0.0);
            for (size_t s = 0; s < 3; ++s)
            {
                q[s] = g.floor[s] + free * backlog[s] / sum;
            }
            g.sched->SetQuotas(q);
        }
    }
'''
def sub(t, a, b, n=1):
    assert t.count(a) >= 1 and (n == 0 or t.count(a) == n), a
    return t.replace(a, b)
# tenants
t = open(f"{H}/orig/ntn-slice-tenants-leo.cc").read()
t = sub(t, 'using namespace ns3;\nusing namespace ns3::ntnslice;', 'using namespace ns3;' + DIAG + 'using namespace ns3::ntnslice;')
t = sub(t, ' *   limiter       as policed,', ' *   queueprop     quotas above the floors in proportion to the slices\' backlogs, every --ctrlMs\n *   limiter       as policed,')
t = sub(t, '    g.sched->TakeBacklog();\n    const double now', '    const std::vector<double> backlog = g.sched->TakeBacklog();\n    const double now')
t = sub(t, '    g.samples.emplace_back(now, q.empty()', QUEUE.lstrip('\n') + '    g.samples.emplace_back(now, q.empty()')
t = sub(t, '    cmd.AddValue("policy", "pf | qos | policed | limiter | static | contract | contract_eph | contract_trim", g.policy);',
        '    bool aLimited = false;\n    cmd.AddValue("aLimited", "limit tenant A to its contract at the source, under any scheduler", aLimited);\n    cmd.AddValue("policy", "pf | qos | policed | limiter | static | contract | contract_eph | contract_trim | queueprop", g.policy);')
t = sub(t, 'const bool limited = g.policy == "policed" || g.policy == "limiter";', 'const bool limited = aLimited || g.policy == "policed" || g.policy == "limiter";')
t = sub(t, 'g.policy == "contract_trim";\n    if (quotaPolicy)', 'g.policy == "contract_trim" || g.policy == "queueprop";\n    if (quotaPolicy)')
t = sub(t, '    std::vector<std::pair<double, double>> elevs;\n', CONNECT.format(w='g.warmup').lstrip('\n') + '    std::vector<std::pair<double, double>> elevs;\n')
t = sub(t, '    js << "]}";\n    std::cout', '    js << "]" << DiagJson() << "}";\n    std::cout')
open(f"{H}/ntn-slice-tenants-leo.cc", "w").write(t)
# pass
t = open(f"{H}/orig/ntn-slice-pass-leo.cc").read()
t = sub(t, 'using namespace ns3;\nusing namespace ns3::ntnslice;', 'using namespace ns3;' + DIAG + 'using namespace ns3::ntnslice;')
t = sub(t, ' * The UE cluster is placed', ' *   queueprop quotas above the floors in proportion to the slices\' backlogs, every --ctrlMs\n * The UE cluster is placed')
t = sub(t, '    g.samples.emplace_back(now, q.size() > kCrit', QUEUE.lstrip('\n') + '    g.samples.emplace_back(now, q.size() > kCrit')
t = sub(t, 'cmd.AddValue("policy", "pf | qos | bwp | static | predict | reactive", g.policy);', 'cmd.AddValue("policy", "pf | qos | bwp | static | predict | reactive | queueprop", g.policy);')
t = sub(t, 'g.policy == "static" || g.policy == "reactive" || g.policy == "predict";\n    if (quotaPolicy)', 'g.policy == "static" || g.policy == "reactive" || g.policy == "predict" || g.policy == "queueprop";\n    if (quotaPolicy)')
t = sub(t, '    // elevation every window\n', CONNECT.format(w='g.warmup').lstrip('\n') + '    // elevation every window\n')
t = sub(t, '    js << "]}";\n    std::cout', '''    js << "]" << DiagJson() << ",\\"q_trace\\":[";
    for (size_t i = 0; i < g.samples.size() && i < 60; ++i)
    {
        js << (i ? "," : "") << "[" << std::get<0>(g.samples[i]) << "," << std::get<1>(g.samples[i]) << "]";
    }
    js << "]}";
    std::cout''')
open(f"{H}/ntn-slice-pass-leo.cc", "w").write(t)
