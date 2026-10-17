//go:build !production || darwin

package main

// Development builds look for Oi-<plat>.zip or Oi-portable-<plat>-*.zip
// beside the executable. macOS production copies the zip into Resources as
// Oi-<plat>.zip.
var embeddedPortable []byte
