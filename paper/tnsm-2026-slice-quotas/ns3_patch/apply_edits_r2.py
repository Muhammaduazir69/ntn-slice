#!/usr/bin/env python3
"""Round 2: ntn-slice-pass-leo-r2.cc from ntn-slice-pass-leo.cc, adding --critFiveQi (79, the default, or 3).
NtnRealStackHelper maps only some 5QIs to dedicated bearers and keeps its NrHelper private, so for 5QI 3 this program
installs the flow without a dedicated bearer and then activates a GBR_GAMING bearer on the flow's port itself, reading
the helper's NrHelper through a private-member access confined to this translation unit. With the default 79 nothing
changes."""
import os
H = os.path.dirname(os.path.abspath(__file__))
t = open(f"{H}/ntn-slice-pass-leo.cc").read()
def sub(a, b):
    global t
    assert t.count(a) == 1, a
    t = t.replace(a, b)
sub('#include "ns3/ntn-real-stack-helper.h"\n', '')
sub('#include <sstream>\n', '''#include <sstream>

// Round 2: read the helper's private NrHelper to activate a bearer for a 5QI that the helper does not map (5QI 3).
#include "ns3/nr-module.h"
#include "ns3/nr-eps-bearer.h"
#include "ns3/nr-epc-tft.h"
#include "ns3/internet-module.h"
#define private public
#include "ns3/ntn-real-stack-helper.h"
#undef private
''')
sub('    cmd.AddValue("critBytes", "delay-critical packet size (bytes)", critBytes);',
    '    uint32_t critFiveQi = 79;\n    cmd.AddValue("critFiveQi", "5QI of the delay-critical flows: 79 (non-GBR V2X) or 3 (GBR, 50 ms)", critFiveQi);\n    cmd.AddValue("critBytes", "delay-critical packet size (bytes)", critBytes);')
sub('''            a = rs.InstallOranFlow(u, 79, 1, 0x000002, NtnOranApplication::URLLC_PERIODIC, Seconds(t0), Seconds(t1));''',
'''            NS_ABORT_MSG_IF(critFiveQi != 79 && critFiveQi != 3, "critFiveQi must be 79 or 3");
            a = rs.InstallOranFlow(u, critFiveQi, 1, 0x000002, NtnOranApplication::URLLC_PERIODIC, Seconds(t0), Seconds(t1));
            if (critFiveQi == 3 && g.policy == "qos")
            {
                AddressValue av;
                a.Get(1)->GetAttribute("Local", av);
                const uint16_t port = InetSocketAddress::ConvertFrom(av.Get()).GetPort();
                NrEpsBearer bearer(NrEpsBearer::GBR_GAMING);
                Ptr<NrEpcTft> tft = Create<NrEpcTft>();
                NrEpcTft::PacketFilter pf;
                pf.localPortStart = port;
                pf.localPortEnd = port;
                tft->Add(pf);
                NS_ABORT_MSG_IF(!rs.m_nr, "no NrHelper");
                rs.m_nr->ActivateDedicatedEpsBearer(rs.GetUeDevices().Get(u), bearer, tft);
            }''')
open(f"{H}/ntn-slice-pass-leo-r2.cc", "w").write(t)
