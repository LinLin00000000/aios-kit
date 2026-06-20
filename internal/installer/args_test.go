package installer

import (
	"reflect"
	"testing"
)

func TestBuildInstallArgsDefault(t *testing.T) {
	got, err := BuildInstallArgs(DefaultOptions())
	if err != nil {
		t.Fatalf("BuildInstallArgs returned error: %v", err)
	}
	want := []string{
		"--non-interactive",
		"--root", "~/aios",
		"--add-to-path", "yes",
		"--proxy", "auto",
		"--proxy-tun",
		"--proxy-auto-env", "auto",
		"--mihomo-version", "v1.19.27",
		"--reset-sources",
		"--with-dev-env",
		"--with-hermes",
		"--with-aiops",
		"--target", "universal",
		"--mode", "copy",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("args mismatch\n got: %#v\nwant: %#v", got, want)
	}
}

func TestBuildInstallArgsAdvanced(t *testing.T) {
	opts := DefaultOptions()
	opts.Root = "/tmp/aios test"
	opts.KitDir = "/src/aios-kit"
	opts.LLLDir = "/src/lll"
	opts.Vault = "/vault/ops"
	opts.SkillsDir = "/skills"
	opts.GlobalBin = "/usr/local/bin"
	opts.AddToPath = "no"
	opts.GitHubMirror = "https://gh-proxy.example/"
	opts.Proxy = "yes"
	opts.ProxyTun = false
	opts.ProxySubscriptionURL = "https://example.com/sub?placeholder=not-real&x=1"
	opts.ProxyProxiesFile = "/private/proxies.yaml"
	opts.ProxyAutoEnv = "yes"
	opts.MihomoURL = "https://example.com/mihomo.gz"
	opts.MihomoVersion = "latest"
	opts.ResetSources = false
	opts.WithDevEnv = false
	opts.WithHermes = false
	opts.WithAIOps = false
	opts.Target = "both"
	opts.Mode = "symlink"
	opts.Force = true
	opts.Yes = true
	opts.DryRun = true

	got, err := BuildInstallArgs(opts)
	if err != nil {
		t.Fatalf("BuildInstallArgs returned error: %v", err)
	}
	want := []string{
		"--non-interactive",
		"--root", "/tmp/aios test",
		"--kit-dir", "/src/aios-kit",
		"--lll-dir", "/src/lll",
		"--vault", "/vault/ops",
		"--skills-dir", "/skills",
		"--global-bin", "/usr/local/bin",
		"--add-to-path", "no",
		"--github-mirror", "https://gh-proxy.example/",
		"--proxy", "yes",
		"--no-proxy-tun",
		"--proxy-subscription-url", "https://example.com/sub?placeholder=not-real&x=1",
		"--proxy-proxies-file", "/private/proxies.yaml",
		"--proxy-auto-env", "yes",
		"--mihomo-url", "https://example.com/mihomo.gz",
		"--mihomo-version", "latest",
		"--no-reset-sources",
		"--no-dev-env",
		"--no-hermes",
		"--no-aiops",
		"--target", "both",
		"--mode", "symlink",
		"--force",
		"--yes",
		"--dry-run",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("args mismatch\n got: %#v\nwant: %#v", got, want)
	}
}
