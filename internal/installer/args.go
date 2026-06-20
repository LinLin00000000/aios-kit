package installer

// BuildInstallArgs converts wizard options into install.sh arguments.
// It always adds --non-interactive because the wizard has already collected input.
func BuildInstallArgs(o Options) ([]string, error) {
	if err := o.Validate(); err != nil {
		return nil, err
	}

	args := []string{"--non-interactive"}
	args = appendPair(args, "--root", o.Root)
	args = appendPairIfSet(args, "--kit-dir", o.KitDir)
	args = appendPairIfSet(args, "--lll-dir", o.LLLDir)
	args = appendPairIfSet(args, "--vault", o.Vault)
	args = appendPairIfSet(args, "--skills-dir", o.SkillsDir)
	args = appendPairIfSet(args, "--global-bin", o.GlobalBin)
	args = appendPair(args, "--add-to-path", o.AddToPath)
	args = appendPairIfSet(args, "--github-mirror", o.GitHubMirror)

	args = appendPair(args, "--proxy", o.Proxy)
	if o.ProxyTun {
		args = append(args, "--proxy-tun")
	} else {
		args = append(args, "--no-proxy-tun")
	}
	args = appendPairIfSet(args, "--proxy-subscription-url", o.ProxySubscriptionURL)
	args = appendPairIfSet(args, "--proxy-proxies-file", o.ProxyProxiesFile)
	args = appendPair(args, "--proxy-auto-env", o.ProxyAutoEnv)
	args = appendPairIfSet(args, "--mihomo-url", o.MihomoURL)
	args = appendPair(args, "--mihomo-version", o.MihomoVersion)
	if o.ResetSources {
		args = append(args, "--reset-sources")
	} else {
		args = append(args, "--no-reset-sources")
	}

	if o.WithDevEnv {
		args = append(args, "--with-dev-env")
	} else {
		args = append(args, "--no-dev-env")
	}
	if o.WithHermes {
		args = append(args, "--with-hermes")
	} else {
		args = append(args, "--no-hermes")
	}
	if o.WithAIOps {
		args = append(args, "--with-aiops")
	} else {
		args = append(args, "--no-aiops")
	}

	args = appendPair(args, "--target", o.Target)
	args = appendPair(args, "--mode", o.Mode)
	if o.Force {
		args = append(args, "--force")
	}
	if o.Yes {
		args = append(args, "--yes")
	}
	if o.DryRun {
		args = append(args, "--dry-run")
	}
	return args, nil
}

func appendPair(args []string, flag string, value string) []string {
	return append(args, flag, value)
}

func appendPairIfSet(args []string, flag string, value string) []string {
	if value == "" {
		return args
	}
	return appendPair(args, flag, value)
}
