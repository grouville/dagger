The table excludes both new connection primers. Each row is one ordered pair; seven different repositories are not pooled into a latency distribution. Values are milliseconds, except bytes.

| Repo | Phase | Order | v0 first byte | v2 first byte | v0 body complete | v2 body complete | Bytes v0 / v2 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| eslint | first_pair | 0→2 | 103.349 | 94.394 | 103.534 | 94.675 | 2472 / 191 |
| go | first_pair | 2→0 | 175.361 | 191.339 | 175.564 | 191.575 | 7806 / 191 |
| go-sdk | first_pair | 0→2 | 100.365 | 90.624 | 100.518 | 90.779 | 6288 / 191 |
| node | first_pair | 2→0 | 179.520 | 199.304 | 179.665 | 199.518 | 962 / 191 |
| playwright | first_pair | 0→2 | 107.462 | 83.929 | 107.516 | 84.065 | 958 / 191 |
| sdk-helpers | first_pair | 2→0 | 90.170 | 99.641 | 90.424 | 99.841 | 2226 / 191 |
| typescript-sdk | first_pair | 0→2 | 105.766 | 88.423 | 106.021 | 88.604 | 9732 / 191 |
| go | reverse_pair | 0→2 | 180.754 | 187.415 | 181.011 | 187.602 | 7806 / 191 |
| go-sdk | reverse_pair | 2→0 | 79.159 | 79.422 | 79.465 | 79.598 | 6288 / 191 |
| typescript-sdk | reverse_pair | 2→0 | 89.939 | 83.023 | 90.215 | 83.210 | 9732 / 191 |
