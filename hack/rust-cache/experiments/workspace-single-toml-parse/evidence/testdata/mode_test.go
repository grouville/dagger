package workspace

import "os"

// Select one complete implementation for each test process.
func init() {
	singleTomlParseEnabled.Store(os.Getenv("DAGGER_TEST_SINGLE_TOML_PARSE") == "on")
}
