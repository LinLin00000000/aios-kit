package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"

	"github.com/LinLin00000000/aios-kit/internal/installer"
	"github.com/LinLin00000000/aios-kit/internal/wizard"
)

const version = "0.1.0"

type jsonOutput struct {
	Version string                `json:"version"`
	Options installer.SafeOptions `json:"options"`
	Plan    installer.SafePlan    `json:"plan"`
	Execute bool                  `json:"execute"`
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintf(os.Stderr, "aios-install: %v\n", err)
		os.Exit(1)
	}
}

func run(argv []string) error {
	opts := installer.DefaultOptions()
	var script string
	var noWizard bool
	var forceWizard bool
	var printCommand bool
	var jsonMode bool
	var execute bool
	var showVersion bool
	var noProxyTun bool
	var noResetSources bool
	var noDevEnv bool
	var noHermes bool
	var noAIOps bool

	fs := flag.NewFlagSet("aios-install", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	fs.StringVar(&script, "script", "", "path to install.sh; defaults to discovering it from the current directory")
	fs.BoolVar(&forceWizard, "wizard", false, "force interactive huh wizard")
	fs.BoolVar(&noWizard, "no-wizard", false, "do not launch the interactive wizard")
	fs.BoolVar(&printCommand, "print-command", false, "print the generated install.sh command instead of executing it")
	fs.BoolVar(&jsonMode, "json", false, "print machine-readable JSON plan")
	fs.BoolVar(&execute, "execute", false, "execute install.sh in non-wizard mode")
	fs.BoolVar(&showVersion, "version", false, "print version and exit")

	fs.StringVar(&opts.Root, "root", opts.Root, "AIOS instance root")
	fs.StringVar(&opts.KitDir, "kit-dir", opts.KitDir, "aios-kit checkout path")
	fs.StringVar(&opts.LLLDir, "lll-dir", opts.LLLDir, "lins-living-loop checkout path")
	fs.StringVar(&opts.Vault, "vault", opts.Vault, "OPS vault path")
	fs.StringVar(&opts.SkillsDir, "skills-dir", opts.SkillsDir, "agent runtime skills directory")
	fs.StringVar(&opts.GlobalBin, "global-bin", opts.GlobalBin, "optional global bin directory for aios/lll links")
	fs.StringVar(&opts.AddToPath, "add-to-path", opts.AddToPath, "yes|no|ask")
	fs.StringVar(&opts.GitHubMirror, "github-mirror", opts.GitHubMirror, "GitHub/raw/release mirror prefix")

	fs.StringVar(&opts.Proxy, "proxy", opts.Proxy, "auto|yes|no")
	fs.BoolVar(&opts.ProxyTun, "proxy-tun", opts.ProxyTun, "enable Mihomo TUN")
	fs.BoolVar(&noProxyTun, "no-proxy-tun", false, "disable Mihomo TUN")
	fs.StringVar(&opts.ProxySubscriptionURL, "proxy-subscription-url", opts.ProxySubscriptionURL, "private proxy provider subscription URL")
	fs.StringVar(&opts.ProxyProxiesFile, "proxy-proxies-file", opts.ProxyProxiesFile, "local proxies YAML snippet path")
	fs.StringVar(&opts.ProxyAutoEnv, "proxy-auto-env", opts.ProxyAutoEnv, "auto|yes|no")
	fs.StringVar(&opts.MihomoURL, "mihomo-url", opts.MihomoURL, "optional Mihomo .gz URL")
	fs.StringVar(&opts.MihomoVersion, "mihomo-version", opts.MihomoVersion, "Mihomo version tag")
	fs.BoolVar(&opts.ResetSources, "reset-sources", opts.ResetSources, "restore apt/npm/pip/Docker source config")
	fs.BoolVar(&noResetSources, "no-reset-sources", false, "do not restore source config")

	fs.BoolVar(&opts.WithDevEnv, "with-dev-env", opts.WithDevEnv, "install/check Python+UV, Node, Docker, Caddy")
	fs.BoolVar(&noDevEnv, "no-dev-env", false, "skip dev environment")
	fs.BoolVar(&opts.WithHermes, "with-hermes", opts.WithHermes, "install/check Hermes Agent")
	fs.BoolVar(&noHermes, "no-hermes", false, "skip Hermes Agent")
	fs.BoolVar(&opts.WithAIOps, "with-aiops", opts.WithAIOps, "install/update OPS vault template")
	fs.BoolVar(&noAIOps, "no-aiops", false, "skip OPS vault template")

	fs.StringVar(&opts.Target, "target", opts.Target, "universal|hermes|both")
	fs.StringVar(&opts.Mode, "mode", opts.Mode, "copy|symlink")
	fs.BoolVar(&opts.Force, "force", opts.Force, "overwrite locally modified managed skill copies")
	fs.BoolVar(&opts.DryRun, "dry-run", opts.DryRun, "print install.sh actions without changing files")
	fs.BoolVar(&opts.Yes, "yes", opts.Yes, "assume yes for optional recommended steps")
	fs.BoolVar(&opts.Yes, "y", opts.Yes, "alias for --yes")

	if err := fs.Parse(argv); err != nil {
		return err
	}
	if showVersion {
		fmt.Println(version)
		return nil
	}

	if noProxyTun {
		opts.ProxyTun = false
	}
	if noResetSources {
		opts.ResetSources = false
	}
	if noDevEnv {
		opts.WithDevEnv = false
	}
	if noHermes {
		opts.WithHermes = false
	}
	if noAIOps {
		opts.WithAIOps = false
	}

	interactive := forceWizard || (!noWizard && isTerminal(os.Stdin) && isTerminal(os.Stdout))
	if interactive {
		var err error
		opts, execute, err = wizard.Run(opts)
		if err != nil {
			return err
		}
		printCommand = !execute
	}

	scriptPath, err := installer.DiscoverScript(script)
	if err != nil {
		return fmt.Errorf("cannot find install.sh; pass --script PATH: %w", err)
	}
	plan, err := installer.NewCommandPlan(scriptPath, opts)
	if err != nil {
		return err
	}

	if jsonMode {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(jsonOutput{Version: version, Options: opts.Safe(), Plan: plan.Safe(), Execute: execute})
	}

	if printCommand || !execute {
		fmt.Println(installer.Summary(opts))
		fmt.Printf("Command:\n  %s\n", plan.RedactedPreview)
		if !execute {
			fmt.Println("\nNot executed. Re-run with --execute or confirm execution in the wizard.")
		}
		return nil
	}

	args, err := installer.BuildInstallArgs(opts)
	if err != nil {
		return err
	}
	return installer.Runner{}.Run(scriptPath, args)
}

func isTerminal(f *os.File) bool {
	info, err := f.Stat()
	if err != nil {
		return false
	}
	return (info.Mode() & os.ModeCharDevice) != 0
}
