package installer

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDiscoverScriptExplicitMustExist(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "missing-install.sh")
	if _, err := DiscoverScript(missing); err == nil {
		t.Fatalf("expected missing explicit script to fail")
	}
}

func TestDiscoverScriptExplicitRejectsDirectory(t *testing.T) {
	if _, err := DiscoverScript(t.TempDir()); err == nil {
		t.Fatalf("expected directory script path to fail")
	}
}

func TestDiscoverScriptExplicitOK(t *testing.T) {
	dir := t.TempDir()
	script := filepath.Join(dir, "install.sh")
	if err := os.WriteFile(script, []byte("#!/usr/bin/env bash\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	got, err := DiscoverScript(script)
	if err != nil {
		t.Fatalf("DiscoverScript returned error: %v", err)
	}
	if got != script {
		t.Fatalf("DiscoverScript = %q, want %q", got, script)
	}
}
