package installer

import (
	"fmt"
	"strings"
)

func Summary(o Options) string {
	var b strings.Builder
	fmt.Fprintf(&b, "AIOS root: %s\n", o.Root)
	fmt.Fprintf(&b, "Components: dev-env=%t, hermes=%t, aiops=%t\n", o.WithDevEnv, o.WithHermes, o.WithAIOps)
	fmt.Fprintf(&b, "Network: proxy=%s, tun=%t, reset-sources=%t\n", o.Proxy, o.ProxyTun, o.ResetSources)
	fmt.Fprintf(&b, "PATH: add-to-path=%s\n", o.AddToPath)
	fmt.Fprintf(&b, "Skillpack: target=%s, mode=%s, force=%t\n", o.Target, o.Mode, o.Force)
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
