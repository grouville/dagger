package dagql

import "os"

func init() { usageSamplingEnabled.Store(os.Getenv("DAGGER_USAGE_SAMPLING_TEST_MODE") == "on") }
