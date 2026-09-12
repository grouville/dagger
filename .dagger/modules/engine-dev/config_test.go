package main

import (
	"encoding/json"
	"testing"
)

func TestPackagedConfigLeavesRegistryPolicyExplicit(t *testing.T) {
	for _, level := range []string{"", "debug", "trace"} {
		t.Run("log-level="+level, func(t *testing.T) {
			data, err := marshalEngineConfig(level)
			if err != nil {
				t.Fatal(err)
			}
			var cfg map[string]json.RawMessage
			if err := json.Unmarshal(data, &cfg); err != nil {
				t.Fatal(err)
			}
			// Absence, rather than an empty docker.io entry, preserves an
			// explicitly supplied legacy TOML registry configuration as well.
			if _, present := cfg["registries"]; present {
				t.Fatalf("packaged config must not impose registry policy: %s", data)
			}
			if level == "" {
				if len(cfg) != 0 {
					t.Fatalf("unexpected default configuration: %s", data)
				}
				return
			}
			var gotLevel string
			if err := json.Unmarshal(cfg["logLevel"], &gotLevel); err != nil {
				t.Fatal(err)
			}
			if gotLevel != level || len(cfg) != 1 {
				t.Fatalf("logging setting changed: %s", data)
			}
		})
	}
}
