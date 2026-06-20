package installer

import (
	"errors"
	"fmt"
)

const (
	ChoiceAuto = "auto"
	ChoiceYes  = "yes"
	ChoiceNo   = "no"

	TargetUniversal = "universal"
	TargetHermes    = "hermes"
	TargetBoth      = "both"

	ModeCopy    = "copy"
	ModeSymlink = "symlink"

	DefaultRoot          = "~/aios"
	DefaultMihomoVersion = "v1.19.27"
)

// Options models the stable argument surface of install.sh.
// The Go wizard is intentionally a front-end: install.sh remains the installer backend.
type Options struct {
	Root      string `json:"root"`
	KitDir    string `json:"kit_dir,omitempty"`
	LLLDir    string `json:"lll_dir,omitempty"`
	Vault     string `json:"vault,omitempty"`
	SkillsDir string `json:"skills_dir,omitempty"`
	GlobalBin string `json:"global_bin,omitempty"`
	AddToPath string `json:"add_to_path"`

	GitHubMirror string `json:"github_mirror,omitempty"`

	Proxy                string `json:"proxy"`
	ProxyTun             bool   `json:"proxy_tun"`
	ProxySubscriptionURL string `json:"proxy_subscription_url,omitempty"`
	ProxyProxiesFile     string `json:"proxy_proxies_file,omitempty"`
	ProxyAutoEnv         string `json:"proxy_auto_env"`
	MihomoURL            string `json:"mihomo_url,omitempty"`
	MihomoVersion        string `json:"mihomo_version"`
	ResetSources         bool   `json:"reset_sources"`

	WithDevEnv bool `json:"with_dev_env"`
	WithHermes bool `json:"with_hermes"`
	WithAIOps  bool `json:"with_aiops"`

	Target string `json:"target"`
	Mode   string `json:"mode"`
	Force  bool   `json:"force"`

	DryRun bool `json:"dry_run"`
	Yes    bool `json:"yes"`
}

func DefaultOptions() Options {
	return Options{
		Root:          DefaultRoot,
		AddToPath:     ChoiceYes,
		Proxy:         ChoiceAuto,
		ProxyTun:      true,
		ProxyAutoEnv:  ChoiceAuto,
		MihomoVersion: DefaultMihomoVersion,
		ResetSources:  true,
		WithDevEnv:    true,
		WithHermes:    true,
		WithAIOps:     true,
		Target:        TargetUniversal,
		Mode:          ModeCopy,
	}
}

func (o Options) Validate() error {
	if o.Root == "" {
		return errors.New("root must not be empty")
	}
	if !isOneOf(o.AddToPath, ChoiceYes, ChoiceNo, "ask") {
		return fmt.Errorf("add-to-path must be one of yes, no, ask: %q", o.AddToPath)
	}
	if !isOneOf(o.Proxy, ChoiceAuto, ChoiceYes, ChoiceNo) {
		return fmt.Errorf("proxy must be one of auto, yes, no: %q", o.Proxy)
	}
	if !isOneOf(o.ProxyAutoEnv, ChoiceAuto, ChoiceYes, ChoiceNo) {
		return fmt.Errorf("proxy-auto-env must be one of auto, yes, no: %q", o.ProxyAutoEnv)
	}
	if o.MihomoVersion == "" {
		return errors.New("mihomo-version must not be empty")
	}
	if !isOneOf(o.Target, TargetUniversal, TargetHermes, TargetBoth) {
		return fmt.Errorf("target must be one of universal, hermes, both: %q", o.Target)
	}
	if !isOneOf(o.Mode, ModeCopy, ModeSymlink) {
		return fmt.Errorf("mode must be one of copy, symlink: %q", o.Mode)
	}
	return nil
}

func isOneOf(value string, allowed ...string) bool {
	for _, item := range allowed {
		if value == item {
			return true
		}
	}
	return false
}
