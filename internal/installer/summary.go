package installer

import (
	"fmt"
	"strings"
)

func Summary(o Options) string {
	return SummaryForPlatform(o, CurrentPlatform())
}

func SummaryForPlatform(o Options, platform string) string {
	platform = NormalizePlatform(platform)
	var b strings.Builder
	fmt.Fprintf(&b, "AIOS root: %s\n", o.Root)
	fmt.Fprintf(&b, "Capability layer: core features always include local instance, modules, command shims, work/config/vault/skills/state dirs, and on-demand local use.\n")
	fmt.Fprintf(&b, "Core: add-to-path=%s, skillpack target=%s, mode=%s, force=%t\n", o.AddToPath, o.Target, o.Mode, o.Force)
	if platform == PlatformLinux {
		fmt.Fprintf(&b, "Add-ons: dev-env=%t, hermes=%t, aiops=%t, proxy=%s, tun=%t, reset-sources=%t\n", o.WithDevEnv, o.WithHermes, o.WithAIOps, o.Proxy, o.ProxyTun, o.ResetSources)
	} else if platform == PlatformWindows {
		fmt.Fprintf(&b, "Add-ons: Windows native core install hides Linux/server-only add-ons; use WSL/install.sh for systemd/Mihomo/TUN/Docker/Caddy/Hermes bootstrap.\n")
	} else {
		fmt.Fprintf(&b, "Add-ons: platform-specific support is limited; prefer dry-run first.\n")
	}
	if o.GitHubMirror != "" {
		fmt.Fprintf(&b, "GitHub mirror: %s\n", o.GitHubMirror)
	}
	if o.ProxySubscriptionURL != "" {
		fmt.Fprintf(&b, "Proxy subscription URL: %s\n", Redacted)
	}
	if o.ProxyProxiesFile != "" {
		fmt.Fprintf(&b, "Proxy proxies file: %s\n", o.ProxyProxiesFile)
	}
	if o.DryRun {
		fmt.Fprintf(&b, "Mode: dry-run\n")
	}
	return b.String()
}
