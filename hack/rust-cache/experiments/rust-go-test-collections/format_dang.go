package main

import (
	"fmt"
	"os"

	"github.com/vito/dang/v2/pkg/dang"
)

func main() {
	for _, filename := range os.Args[1:] {
		source, err := os.ReadFile(filename)
		if err != nil { panic(err) }
		formatted, err := dang.FormatFile(source)
		if err != nil { panic(err) }
		if err := os.WriteFile(filename, []byte(formatted), 0644); err != nil { panic(err) }
		fmt.Println(filename)
	}
}
