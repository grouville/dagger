# Interface field-list snapshot experiment

This experiment is unselected: faster components and lower allocation did not produce a consistent full-command speedup. The diagnostic toggle remains off. Read ../../NATIVE_INTERFACE_FIELD_SNAPSHOTS.md for the result and controls.

The standalone candidate is based on dagger/dagger ff0b029a4d270a651b9a8c7286babc79089066e4. Full dagql race checks pass. components-v2 contains the corrected six-pair fresh-process benchmark; components retains the initial fixture failure. paired and paired-go contain four balanced command pairs, with unchanged module source and a same-binary toggle. Retained histories and Rust selection checks verify the graceful engine replacement. Earlier source dependencies are recorded in ../rust-go-test-collections/engine/.

The engine identity is 08a1f13ae88c61f3dadea8d834132d71a52d77ccf3a7d91f91ad760ef4702197, based on 19eda924854e7f22582f3a7430272aa729cbeb5f with 65 overlays. Engine replacement sources and the standalone candidate are stored under testdata, excluded from normal Go discovery. Build manifests preserve every original path and source hash. Executables and toolchains are excluded. The scalar argument-field probe is an unselected component experiment as well.
