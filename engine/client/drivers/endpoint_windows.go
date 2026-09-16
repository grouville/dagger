//go:build windows

package drivers

// privateDir is the gate for creating a local endpoint. Windows file
// permissions are ACLs rather than mode bits, so the ownership check that
// keeps the token private is not available yet; a native Windows client
// keeps the exec tunnel. Linux clients in WSL2 take the endpoint path.
func privateDir(string) bool { return false }
