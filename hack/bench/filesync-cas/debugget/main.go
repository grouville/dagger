// debugget reads the engine's loopback-only profiling endpoint from docker exec.
package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

func main() {
	if len(os.Args) != 2 || !strings.HasPrefix(os.Args[1], "/debug/wcprof/dump") {
		fmt.Fprintln(os.Stderr, "usage: debugget /debug/wcprof/dump[?flush=0]")
		os.Exit(2)
	}
	client := &http.Client{Timeout: 20 * time.Second}
	resp, err := client.Get("http://127.0.0.1:6060" + os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		fmt.Fprintln(os.Stderr, resp.Status)
		os.Exit(1)
	}
	if _, err := io.Copy(os.Stdout, resp.Body); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
