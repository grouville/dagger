package layercopy

import "testing"

func TestCopyProfileRecordsAggregateWork(t *testing.T) {
	var profile CopyProfile
	done := profile.measure("copy")
	profile.addBytes("copy", 7)
	done()
	profile.measure("copy")()
	work := profile.Operations["copy"]
	if work.Calls != 2 || work.Bytes != 7 || work.Nanoseconds < 0 {
		t.Fatalf("unexpected aggregate: %+v", work)
	}
}

func TestCopyProfileDisabled(t *testing.T) {
	var profile *CopyProfile
	profile.measure("copy")()
	profile.addBytes("copy", 7)
}
