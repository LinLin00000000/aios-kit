package installer

import (
	"bytes"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestRunnerUsesArgvWithoutShellSplitting(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("fake bash script runner test requires bash")
	}
	dir := t.TempDir()
	script := filepath.Join(dir, "fake-install.sh")
	if err := os.WriteFile(script, []byte("#!/usr/bin/env bash\nprintf '<%s>\\n' \"$@\"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	var out bytes.Buffer
	r := Runner{Stdout: &out, Stderr: &out}
	args := []string{"--root", "/tmp/aios kit", "--proxy-subscription-url", "https://x?a=1&b=2"}
	if err := r.Run(script, args); err != nil {
		t.Fatalf("runner failed: %v\n%s", err, out.String())
	}
	got := out.String()
	for _, want := range []string{"<--root>", "</tmp/aios kit>", "<--proxy-subscription-url>", "<https://x?a=1&b=2>"} {
		if !strings.Contains(got, want) {
			t.Fatalf("runner output missing %s; output follows\n%s", want, got)
		}
	}
}
