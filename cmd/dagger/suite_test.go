package main

import "go.dagger.io/dagger/internal/testutil"

func init() {
	if err := testutil.SetupDaggerBuildkitd(); err != nil {
		panic(err)
	}
}
