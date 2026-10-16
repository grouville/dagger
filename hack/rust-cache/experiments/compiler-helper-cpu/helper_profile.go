package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"runtime/pprof"
	"time"
)

// Diagnostic branch only. No profiling code is selected by the normal module.
func startHelperProfile(operation string) func() {
	var cpu bytes.Buffer
	if err := pprof.StartCPUProfile(&cpu); err != nil {
		panic(err)
	}
	runtime.SetBlockProfileRate(1)
	started := time.Now()
	return func() {
		elapsed := time.Since(started)
		pprof.StopCPUProfile()
		var blocked bytes.Buffer
		if err := pprof.Lookup("block").WriteTo(&blocked, 0); err != nil {
			panic(err)
		}
		record, err := json.Marshal(struct {
			Operation string `json:"operation"`
			Nanos     int64  `json:"nanos"`
			CPU       string `json:"cpu"`
			Block     string `json:"block"`
		}{operation, elapsed.Nanoseconds(), base64.StdEncoding.EncodeToString(cpu.Bytes()), base64.StdEncoding.EncodeToString(blocked.Bytes())})
		if err != nil {
			panic(err)
		}
		fmt.Fprintln(os.Stderr, "RUST_COMPILER_PROFILE", string(record))
	}
}
