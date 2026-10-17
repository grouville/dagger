package server

import "os"

func init() {
	parallelClientAdmissionEnabled.Store(os.Getenv("DAGGER_TEST_PARALLEL_CLIENT_ADMISSION") == "on")
}
