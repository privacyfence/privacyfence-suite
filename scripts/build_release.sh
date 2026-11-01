#!/bin/sh
# Builds the release assets into OUTDIR (default dist/):
#   privacyfence-suite-<config>.tar.gz and .zip for every folder under configs/,
#   install.sh (stamped with the version and the configuration list), and SHA256SUMS.
# Usage: scripts/build_release.sh <version> [outdir]
# The files come from HEAD (git), not the working tree. The archives are reproducible; SOURCE_DATE_EPOCH defaults to the commit time.
set -eu

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "usage: build_release.sh <version> [outdir]" >&2
    exit 2
fi
version=$1
outdir=${2:-dist}

if ! printf '%s\n' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$'; then
    echo "build_release: bad version $version" >&2
    exit 2
fi

case $outdir in
/*) ;;
*) outdir=$PWD/$outdir ;;
esac

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

LC_ALL=C
export LC_ALL
TZ=UTC
export TZ
umask 022

epoch=${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct)}

configs=
for dir in configs/*/; do
    [ -d "$dir" ] || continue
    name=${dir#configs/}
    configs="$configs ${name%/}"
done
configs=${configs# }
if [ -z "$configs" ]; then
    echo "build_release: no configurations under configs/" >&2
    exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

mkdir -p "$outdir"
for config in $configs; do
    rm -f "$outdir/privacyfence-suite-$config.tar.gz" "$outdir/privacyfence-suite-$config.zip"
done
rm -f "$outdir/install.sh" "$outdir/SHA256SUMS"

for config in $configs; do
    top=privacyfence-$config
    stage=$work/$top
    mkdir -p "$stage"
    # Export from the commit, never from the working tree, so a local edit cannot reach an archive.
    entries=$(git ls-tree -r HEAD -- "configs/$config/" | awk '{ m = $1; $1 = $2 = $3 = ""; sub(/^ +/, ""); print m "\t" $0 }')
    if [ -z "$entries" ]; then
        echo "build_release: no tracked files in configs/$config" >&2
        exit 1
    fi
    printf '%s\n' "$entries" | while IFS="$(printf '\t')" read -r mode file; do
        rel=${file#"configs/$config/"}
        mkdir -p "$stage/$(dirname "$rel")"
        git show "HEAD:$file" >"$stage/$rel"
        if [ "$mode" = 100755 ]; then chmod 755 "$stage/$rel"; else chmod 644 "$stage/$rel"; fi
    done
    git show HEAD:README.md >"$stage/README.md"
    git show HEAD:LICENSE >"$stage/LICENSE"
    chmod 644 "$stage/README.md" "$stage/LICENSE"
    printf '%s\n' "$version" >"$stage/VERSION"
    chmod 644 "$stage/VERSION"
    find "$stage" -type d -exec chmod 755 {} +
    find "$stage" -exec touch -h -d "@$epoch" {} +

    (
        cd "$work"
        tar --sort=name --owner=0 --group=0 --numeric-owner --mtime="@$epoch" -cf - "$top" |
            gzip -n >"$outdir/privacyfence-suite-$config.tar.gz"
        find "$top" | sort | zip -X -q "$outdir/privacyfence-suite-$config.zip" -@
    )
done

sed -e "s/@VERSION@/$version/g" -e "s/@CONFIGS@/$configs/g" release/install.sh >"$outdir/install.sh"
chmod 755 "$outdir/install.sh"
if grep -q -e '@VERSION@' -e '@CONFIGS@' "$outdir/install.sh"; then
    echo "build_release: install.sh still has an unreplaced @VERSION@ or @CONFIGS@" >&2
    exit 1
fi

(
    cd "$outdir"
    sums=$work/SHA256SUMS
    : >"$sums"
    for asset in *; do
        sha256sum "$asset" >>"$sums"
    done
    mv "$sums" SHA256SUMS
)
echo "build_release: $version -> $outdir"
