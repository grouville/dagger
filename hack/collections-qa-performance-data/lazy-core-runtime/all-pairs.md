# All ordinary and explicitly separated first-use pairs

Every value below is milliseconds. `Cloud drain` is the engine main-client flush phase, not network RTT or Cloud server processing. `Outside shutdown` also includes CLI work and cleanup. Native generated-byte visibility is sampled every 5 ms.

| Stage / command | Pair | Baseline CLI | Lazy CLI | Delta | Baseline file visible | Lazy file visible | Baseline Cloud drain | Lazy Cloud drain | Delta outside shutdown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fresh-engine-first-cli / workspace-files | 0 | 1118.825 | 744.715 | -374.110 | — | — | 151.806 | 156.068 | -378.746 |
| warm / workspace-files | 0 | 600.620 | 552.452 | -48.168 | — | — | 148.162 | 153.603 | -54.012 |
| warm / workspace-files | 1 | 578.407 | 560.336 | -18.072 | — | — | 146.934 | 162.742 | -34.231 |
| warm / workspace-files | 2 | 557.117 | 587.936 | +30.820 | — | — | 147.992 | 154.098 | +24.637 |
| minimal-core / core-version | 0 | 731.213 | 1031.530 | +300.317 | — | — | 80.292 | 86.027 | +294.590 |
| explicit-local-primer / generate-warm | 0 | 648.336 | 504.066 | -144.270 | 618.241 | 484.949 | 0.001 | 0.001 | -133.448 |
| warm / generate-warm | 0 | 721.185 | 1425.483 | +704.298 | 320.881 | 304.995 | 262.991 | 1015.665 | -48.435 |
| warm / generate-warm | 1 | 725.156 | 819.218 | +94.062 | 339.172 | 337.546 | 284.032 | 302.972 | +74.770 |
| warm / generate-warm | 2 | 833.782 | 831.837 | -1.945 | 332.264 | 326.211 | 355.869 | 317.841 | +38.311 |
| new-input-edit / generate-edit | 0 | 834.913 | 929.918 | +95.005 | 355.864 | 362.228 | 354.050 | 380.379 | +68.684 |
| new-input-edit / generate-edit | 1 | 1908.259 | 926.809 | -981.450 | 1451.958 | 358.393 | 345.568 | 380.930 | -1017.202 |
| new-input-edit / generate-edit | 2 | 830.177 | 919.444 | +89.267 | 350.872 | 362.190 | 364.778 | 385.340 | +68.604 |
| greetings-first-use-warm-engine / artifacts | 0 | 24938.108 | 24712.195 | -225.913 | — | — | 537.703 | 493.795 | -183.873 |
| warm / artifacts | 0 | 2516.201 | 2038.183 | -478.018 | — | — | 625.237 | 425.442 | -280.186 |
| warm / artifacts | 1 | 2428.266 | 2132.746 | -295.520 | — | — | 774.096 | 403.964 | +73.529 |
| warm / artifacts | 2 | 2939.975 | 2125.554 | -814.420 | — | — | 1336.395 | 551.989 | -28.079 |
| warm / generators | 0 | 2034.607 | 1625.431 | -409.177 | — | — | 837.615 | 734.684 | -305.575 |
| warm / generators | 1 | 1740.810 | 1536.331 | -204.479 | — | — | 761.697 | 627.647 | -63.577 |
| local-fourteen-check-correctness / all-checks | 0 | 1482.145 | 1468.179 | -13.966 | — | — | 0.001 | 0.001 | -14.225 |
| selected-check-first-use-local-primer / selected-check | 0 | 47332.292 | 41385.312 | -5946.980 | — | — | 0.001 | 0.002 | -5864.184 |
| warm / selected-check | 0 | 4732.981 | 2429.002 | -2303.980 | — | — | 675.863 | 283.896 | -1912.478 |
| warm / selected-check | 1 | 2428.888 | 2243.227 | -185.661 | — | — | 515.406 | 404.259 | -74.666 |
