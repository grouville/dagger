I went back through the measurements. The large-cache experiment was encouraging: cleanup took about 2 seconds less, and the full Go test listing was faster too. But that was on my experimental setup, not main. [Measurements](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_CACHE_USAGE_PROVIDER_SAMPLING.md).

The benchmark in this PR uses 200,000 values. I haven't shown that this is a useful example of the cost users actually hit. I need to check that before treating it as a reason to add this code.
