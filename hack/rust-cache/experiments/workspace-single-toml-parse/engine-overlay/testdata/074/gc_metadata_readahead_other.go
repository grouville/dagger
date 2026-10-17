//go:build !linux

package server

import "context"

func hintGCMetadata(context.Context, string) {}
