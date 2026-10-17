package contenthash

import "testing"

func TestParallelFingerprintDiagnosticModes(t *testing.T) {
	defer parallelFingerprint.Store(false)
	for _, enabled := range []bool{false, true} {
		parallelFingerprint.Store(enabled)
		TestTreeFingerprintParallelCompatibility(t)
		TestTreeFingerprintDiscoveryInputs(t)
		TestTreeFingerprintUnsupportedInputs(t)
		TestTreeFingerprintCanonicalOrder(t)
	}
}
