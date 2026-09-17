#!/usr/bin/env python3
"""Load one engine-dev OCI archive under a new, explicit local tag."""
import argparse
import json
import subprocess
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('tag')
    args = parser.parse_args()
    found = subprocess.run(['docker', 'image', 'inspect', args.tag], capture_output=True)
    if found.returncode == 0 or b'no such' not in found.stderr.lower():
        raise SystemExit('Refusing existing tag or unavailable Docker daemon')
    with tarfile.open(args.archive) as archive:
        index = json.load(archive.extractfile('index.json'))
        if len(index['manifests']) != 1:
            raise SystemExit('Expected a single-platform OCI archive')
        image_id = index['manifests'][0]['digest']
    subprocess.run(['docker', 'load', '-i', args.archive], check=True)
    subprocess.run(['docker', 'image', 'inspect', image_id], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['docker', 'tag', image_id, args.tag], check=True)
    print(args.tag, image_id)


if __name__ == '__main__':
    main()
