package installer

import "testing"

func TestBuildInstallArgsPreservesWizardBootstrapFlags(t *testing.T) {
	opts := DefaultOptions()
	opts.Root = "/tmp/aios-root"
	opts.GitHubMirror = "https://gh-proxy.example/"
	opts.Proxy = ChoiceNo
	opts.ProxyTun = false
	opts.ResetSources = false
	opts.WithDevEnv = false
	opts.WithHermes = false
	opts.WithAIOps = false
	opts.Target = TargetBoth
	opts.Mode = ModeSymlink
	opts.DryRun = true
	opts.Yes = true

	args, err := BuildInstallArgs(opts)
	if err != nil {
		t.Fatalf("BuildInstallArgs returned error: %v", err)
	}
	assertContainsInOrder(t, args,
		"--non-interactive",
		"--root", "/tmp/aios-root",
		"--github-mirror", "https://gh-proxy.example/",
		"--proxy", ChoiceNo,
		"--no-proxy-tun",
		"--no-reset-sources",
		"--no-dev-env",
		"--no-hermes",
		"--no-aiops",
		"--target", TargetBoth,
		"--mode", ModeSymlink,
		"--yes",
		"--dry-run",
	)
}

func assertContainsInOrder(t *testing.T, got []string, want ...string) {
	t.Helper()
	pos := 0
	for _, needle := range want {
		found := false
		for pos < len(got) {
			if got[pos] == needle {
				found = true
				pos++
				break
			}
			pos++
		}
		if !found {
			t.Fatalf("args %v did not contain %q in expected order %v", got, needle, want)
		}
	}
}
