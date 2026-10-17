package dagql

import "os"

func init() { usagePrunePreflightEnabled.Store(os.Getenv("DAGGER_USAGE_PREFLIGHT_TEST_MODE") == "on") }
