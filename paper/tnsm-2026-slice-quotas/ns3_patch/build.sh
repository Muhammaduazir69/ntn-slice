#!/bin/bash
# Standalone build of the two simulation programs; touches nothing under ns-3-dev. Same compiler and flags as the shared
# build's compile_commands.json, linked against the optimized libraries in ns-3-dev/build/lib.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
R=/home/uzair/6g_ntn_ns3/ns-3-dev; B=$R/build; OUT="$HERE/../bin"; mkdir -p "$OUT"
FLAGS="-DEIGEN_MPL2_ONLY -DHAVE_BOOST -DHAVE_BOOST_UNITS -DHAVE_EIGEN3 -DHAVE_GSL -DHAVE_LIBXML2 -DHAVE_PACKET_H -DHAVE_SQLITE3 -DHAVE_STDINT_H -DNS3_BUILD_PROFILE_OPTIMIZED -DPROJECT_SOURCE_PATH=\"$R\" -D__LINUX__ -I$B/include -I/usr/include/eigen3 -I/usr/include/libxml2 -O3 -DNDEBUG -std=c++20 -fPIE -fno-semantic-interposition -march=native -mtune=native"
L=""; for m in ntn-slice ntn-constellation ntn-cho ntn-traffic nr mobility network core; do L="$L $B/lib/libns3.43-$m-optimized.so"; done
for p in pass tenants; do
  nice -n 5 c++ $FLAGS -c "$HERE/ntn-slice-$p-leo.cc" -o "$OUT/p10-$p.o"
  nice -n 5 c++ -o "$OUT/p10-$p" "$OUT/p10-$p.o" $L -lgsl -lgslcblas -Wl,-rpath,$B/lib -Wl,-rpath-link,$B/lib
  rm -f "$OUT/p10-$p.o"
done
sha256sum "$OUT/p10-pass" "$OUT/p10-tenants" | cut -c1-12,65-
