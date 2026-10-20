Searching a file created with `Workspace.withNewFile` fails in a host workspace, even though the file exists in Dagger’s view of that workspace. For example:

```graphql
{
  currentWorkspace {
    withNewFile(path: "created/new.txt", contents: "needle\n") {
      search(paths: ["/created/new.txt"], pattern: "needle") {
        filePath
      }
    }
  }
}
```

Search is already meant to include files created through Dagger: [the original change](https://github.com/dagger/dagger/commit/e090829bb536bc83ab980efee4b301bbdf908459) explicitly includes newly created files and applies search paths to those edits. The [existing integration test](https://github.com/dagger/dagger/blob/c5456d9cbf47e432b89aba43e35211425e8e1f03/core/integration/workspace_api_test.go#L2437) checks this inside a directory that already exists on the host. This fix covers a file or parent directory that exists only through Dagger edits.

The search sends that path to the host before combining the host results with changes made through Dagger. The host does not have the new file, so its search fails. The same problem affects a newly created parent directory and a search mixing host files with files created through Dagger.

Keep paths covered by Dagger’s changes out of the host search, then combine the results as usual. Do this even when all requested paths come from those changes. For a parent directory, check whether it exists in the underlying source before asking the host to search it. Unrelated missing paths keep their error.

The new integration test runs the real CLI in the existing workspace container fixture, with ripgrep installed as in the other host-search test. Three cases fail on main and pass with this change: the added file, its new parent directory and mixed sources. A fourth case checks that an unrelated missing file still fails. The existing focused path-filtering and result-merging tests pass under the race detector.

The extra host existence check applies only when a requested directory contains Dagger edits. The fix uses the existing workspace state. It was found while improving Go test collection listing; the package-scoped listing change can be reviewed separately.

[Reproduction, checks and design history](https://github.com/grouville/dagger/tree/83bae06577a91eca3212e62712276b13d2b193b6/hack/rust-cache/experiments/standalone-go-collections/assessment/scoped-search-followup-oct19).

[Draft #14740](https://github.com/dagger/dagger/pull/14740). [CI fixture verification](../experiments/standalone-go-collections/assessment/workspace-search-ci-oct19/).
