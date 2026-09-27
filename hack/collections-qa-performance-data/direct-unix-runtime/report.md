The56-command local-only comparison completed with all expected outcomes. It used the same original CLI and the same engine process/retained volume; the only selector change was Docker exec versus an existing direct Unix endpoint. Both arms retained Docker image attachables. Private socket permissions and original-container/volume exclusivity were checked; the new container/socket directory were removed and original fixtures/container/binary preserved.

There are three ordinary paired samples per flow, with alternating order rotated across flows. They are exploratory measurements on one Linux host, not stable distributions. Twelve exact primers, four fail/restore sentinel calls and four separate profile-phase calls are excluded from ordinary medians.

| Flow | Docker samples (ms) | Unix samples (ms) | Median change (ms) |
| --- | --- | --- | ---: |
| core | 204.4 / 205.2 / 206.5 | 103.2 / 101.8 / 100.3 | -103.4 |
| ws | 153.6 / 189.2 / 194.9 | 57.5 / 60.1 / 58.1 | -131.1 |
| call | 306.4 / 300.5 / 317.6 | 203.5 / 180.2 / 171.5 | -126.2 |
| check | 235.1 / 242.7 / 246.4 | 133.1 / 134.5 / 133.9 | -108.7 |
| generate | 312.3 / 278.5 / 284.9 | 149.8 / 148.9 / 145.6 | -136.0 |
| artifacts | 1365.4 / 1424.5 / 1344.6 | 1243.2 / 1219.3 / 1292.9 | -122.2 |

Native check is the standard fixture check and its failure sentinel is verified independently on both transports. Warm native generation already has current output; it is not SDK code generation or a fresh edit. Expanded artifacts and the separately profiled14-row check listing retain their output oracles.

This demonstrates the existing local Unix capability only. No automatic production fast path, remote Docker/Desktop support, fresh-volume cold, service-up or Cloud result is measured. CPU values count CLI children and engine cgroup work separately; they must not be summed into a predicted wall saving. The existing fixture sits under a wide /tmp, identically for both arms.

The profiles follow full identical check-list primers and are excluded from ordinary medians. Git HTTP attribution is a separate diagnostic analysis; inclusive spans overlap.

Raw Unix also bypasses the container driver’s Available→docker version admission probe. These measurements combine that admission difference with replacing Docker exec tunnels; they do not identify the tunnel-only saving. The image loader override preserves attachable behavior but does not restore the skipped driver admission probe.
