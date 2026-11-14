#!/bin/bash
# Round 2: third standalone program, p10-pass-r2, same flags and libraries as build.sh.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
R=/home/uzair/6g_ntn_ns3/ns-3-dev; B=$R/build; OUT="$HERE/../bin"
FLAGS="-DEIGEN_MPL2_ONLY -DHAVE_BOOST -DHAVE_BOOST_UNITS -DHAVE_EIGEN3 -DHAVE_GSL -DHAVE_LIBXML2 -DHAVE_PACKET_H -DHAVE_SQLITE3 -DHAVE_STDINT_H -DNS3_BUILD_PROFILE_OPTIMIZED -DPROJECT_SOURCE_PATH=\"$R\" -D__LINUX__ -I$B/include -I/usr/include/eigen3 -I/usr/include/libxml2 -O3 -DNDEBUG -std=c++20 -fPIE -fno-semantic-interposition -march=native -mtune=native"
L=""; for m in ntn-slice ntn-constellation ntn-cho ntn-traffic nr mobility network core internet; do L="$L $B/lib/libns3.43-$m-optimized.so"; done
nice -n 19 c++ $FLAGS -c "$HERE/ntn-slice-pass-leo-r2.cc" -o "$OUT/p10-pass-r2.o"
nice -n 19 c++ -o "$OUT/p10-pass-r2" "$OUT/p10-pass-r2.o" $L -lgsl -lgslcblas -Wl,-rpath,$B/lib -Wl,-rpath-link,$B/lib
rm -f "$OUT/p10-pass-r2.o"
sha256sum "$OUT/p10-pass-r2" | cut -c1-12
