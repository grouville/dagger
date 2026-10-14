# Compiler file-access probe

`file-access.bt` is a bpftrace diagnostic for rustc `openat` and `statx` calls.
It records successful file opens and failed existence checks. It is not a cache
dependency recorder: raw relative paths, a process-name filter and fixed path
buffers are deliberately limited.

Run it in an isolated engine with the required BPF capabilities and tracefs:

```sh
bpftrace file-access.bt > /tmp/compiler-file-access.log
```

Wait for `READY`, then run the fixture from
`../../fixtures/proc-macro-inputs` through a fresh compiler execution. Stop the
probe with SIGINT. Its setup/attachment belongs outside compiler timing when
measuring an engine-persistent recorder. Preserve diagnostics about lost events.

The measured experiment records both `data/value.txt` and a failed check for
`data/override.txt`. See [the study](../../NATIVE_PROC_MACRO_INPUTS.md) for paired
timings and the additional requirements before any output can govern cache hits.
