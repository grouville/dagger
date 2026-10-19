package main

import (
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

// Skip the other graph tables without retaining them in memory.
func skip(d *json.Decoder) error {
	t, err := d.Token()
	if err != nil { return err }
	if delim, ok := t.(json.Delim); ok && (delim == '[' || delim == '{') {
		for d.More() {
			if delim == '{' { if _, err := d.Token(); err != nil { return err } }
			if err := skip(d); err != nil { return err }
		}
		_, err = d.Token()
	}
	return err
}

func main() {
	started := time.Now()
	client := &http.Client{Timeout: 180*time.Second}
	resp, err := client.Get(os.Args[1])
	if err != nil { panic(err) }
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK { panic(resp.Status) }
	file, err := os.Create(os.Args[2])
	if err != nil { panic(err) }
	zipped := gzip.NewWriter(file)
	d := json.NewDecoder(io.TeeReader(resp.Body,zipped))
	t, err := d.Token()
	if err != nil || t != json.Delim('{') { panic(fmt.Sprint(t,err)) }
	types, states := map[string]int{}, map[string]int{}
	count := 0
	for d.More() {
		key, err := d.Token()
		if err != nil { panic(err) }
		if key != "results" { if err := skip(d); err != nil { panic(err) }; continue }
		if t, err := d.Token(); err != nil || t != json.Delim('[') { panic(fmt.Sprint(t,err)) }
		for d.More() {
			var row struct { TypeName string `json:"type_name"`; PayloadState string `json:"payload_state"` }
			if err := d.Decode(&row); err != nil { panic(err) }
			count++; types[row.TypeName]++; states[row.PayloadState]++
		}
		if _, err := d.Token(); err != nil { panic(err) }
	}
	if _, err := d.Token(); err != nil { panic(err) }
	if err := zipped.Close(); err != nil { panic(err) }
	if err := file.Close(); err != nil { panic(err) }
	if count == 0 { panic("snapshot contained no results") }
	json.NewEncoder(os.Stdout).Encode(map[string]any{"results":count,"types":types,"payload_states":states,"seconds":time.Since(started).Seconds(),"endpoint":os.Args[1],"scope":"Reported GraphQL type names from the current-main fixture engine after the complete cohort. This is not an exact disk-usage skip-predicate count."})
}
