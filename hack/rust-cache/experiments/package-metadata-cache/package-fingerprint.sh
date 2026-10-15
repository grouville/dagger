
set -eu
# Cargo configuration can include arbitrary files or source-based tools.
# Keep those projects on Cargo's existing discovery path for now.
cargo_config=$(find . -name .cargo -print -quit) || exit 0
if [ -n "$cargo_config" ]; then exit 0; fi
metadata_tmp=$(mktemp -d /tmp/dagger-package-metadata.XXXXXXXX) || exit 0
trap 'rm -rf "$metadata_tmp"' EXIT
if ! find . -printf '%P\0%y\0%m\0%U\0%G\0%l\0' > "$metadata_tmp/layout"; then
  exit 0
fi
if ! find . \( -type f -o -type l \) ! -name '*.rs' -exec sha256sum -b -z -- '{}' + > "$metadata_tmp/contents"; then
  exit 0
fi
layout_sum=$(sha256sum "$metadata_tmp/layout") || exit 0
set -- $layout_sum
layout_digest=$1
contents_sum=$(sha256sum "$metadata_tmp/contents") || exit 0
set -- $contents_sum
contents_digest=$1
fingerprint_sum=$(printf '%s\0%s\0' "$layout_digest" "$contents_digest" | sha256sum) || exit 0
set -- $fingerprint_sum
printf '%s' "$1"
