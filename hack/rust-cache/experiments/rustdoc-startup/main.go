package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

func main() {
	if len(os.Args) > 1 {
		data, err := os.ReadFile(os.Args[1])
		if err != nil {
			panic(err)
		}
		var captured struct {
			Cwd string
			Env map[string]string
		}
		if err := json.Unmarshal(data, &captured); err != nil {
			panic(err)
		}
		os.Clearenv()
		for k, v := range captured.Env {
			if err := os.Setenv(k, v); err != nil {
				panic(err)
			}
		}
		if err := os.Chdir(captured.Cwd); err != nil {
			panic(err)
		}
	}
	sysroot, err := exec.Command("rustc", "--print", "sysroot").Output()
	if err != nil {
		panic(err)
	}
	type variant struct {
		Tool, Path string
		Samples    []float64
	}
	var variants []*variant
	for _, tool := range []string{"rustc", "rustdoc"} {
		proxy, err := exec.LookPath(tool)
		if err != nil {
			panic(err)
		}
		real := filepath.Join(strings.TrimSpace(string(sysroot)), "bin", tool)
		a, err := exec.Command(proxy, "--version").Output()
		if err != nil {
			panic(err)
		}
		b, err := exec.Command(real, "--version").Output()
		if err != nil {
			panic(err)
		}
		if !bytes.Equal(a, b) {
			panic("toolchain versions differ")
		}
		fmt.Fprintf(os.Stderr, "%s %s / %s: %s", tool, proxy, real, a)
		variants = append(variants, &variant{Tool: tool + "-path", Path: proxy}, &variant{Tool: tool + "-sysroot", Path: real})
	}
	for i := 0; i < 40; i++ {
		for offset := range variants {
			v := variants[(i+offset)%len(variants)]
			started := time.Now()
			if out, err := exec.Command(v.Path, "--version").CombinedOutput(); err != nil {
				panic(string(out))
			}
			v.Samples = append(v.Samples, float64(time.Since(started).Microseconds())/1000)
		}
	}
	for _, v := range variants {
		values := append([]float64(nil), v.Samples...)
		sort.Float64s(values)
		row := struct {
			Tool, Path string
			MedianMS   float64
			SamplesMS  []float64
		}{v.Tool, v.Path, (values[19] + values[20]) / 2, v.Samples}
		if err := json.NewEncoder(os.Stdout).Encode(row); err != nil {
			panic(err)
		}
	}
}
