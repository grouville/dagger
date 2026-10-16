Listing a large collection reads many stored spans in batches. Each row currently allocates a raw frame buffer before the decoder copies its fields into the returned row. The scanner's reader also misses its existing pool on this path.

Reuse one payload buffer within a batch and return the reader when the read finishes. This follows the existing `readIDs` path. Decoded fields keep their own storage, so later reads cannot overwrite returned rows.

Six alternating before/after pairs, fresh processes, Go 1.26.6 and `GOMAXPROCS=8`:

| Rows per read | Time before → after | Allocated bytes before → after |
| --- | ---: | ---: |
| 1 | 10.26 → 1.96 µs | 68,775 → 3,116 |
| 512 | 619 → 424 µs | 1,614,839 → 830,824 |

File creation and fixture writes are outside the timer. These measurements cover the batch reader; complete Rust-command measurements are pending.

The full `engine/clientdb` race suite passes. The new test checks that rows survive buffer growth, later frames and another read, including nil and empty fields. It also rejects a deliberately altered decoder that borrows its input buffer.

The change uses the existing pool and introduces no lock. The payload buffer lives for one read call; a large frame keeps that scratch allocation until the call returns. Stored data and row ownership keep their existing format and behavior.
